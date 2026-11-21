"""AuthService over in-memory fakes and a fake clock."""

from dataclasses import replace
from datetime import timedelta

import pytest
from app.domain.auth import (
    CurrentPasswordError,
    InvalidCredentialsError,
    InvalidSessionError,
    LoginLockedError,
    NotAuthenticatedError,
)
from app.domain.password_policy import PasswordPolicyError
from app.domain.user import Role
from app.services.auth_service import IssuedSession

from auth_fakes import PASSWORD, Rig, make_user

IP = "1.1.1.1"


def login(
    rig: Rig, password: str = PASSWORD, *, username: str = "alice", ip: str = IP
) -> IssuedSession:
    return rig.service.login(username, password, ip)


# ----------------------------------------------------------------- login


def test_login_success_issues_a_session_and_audits() -> None:
    rig = Rig()
    session = login(rig)
    assert session.user.username == "alice"
    assert session.access_token and session.refresh_token
    assert rig.audit.names() == ["login.success"]
    assert rig.service.current_user(session.access_token).id == "id-alice"


def test_session_repr_hides_tokens() -> None:
    session = login(Rig())
    assert session.access_token not in repr(session)
    assert session.refresh_token not in repr(session)


@pytest.mark.parametrize("username", ["alice", "ALICE", "  Alice  "])
def test_username_is_case_and_space_insensitive(username: str) -> None:
    assert login(Rig(), username=username).user.id == "id-alice"


@pytest.mark.parametrize(
    ("username", "password"),
    [("alice", "wrong password"), ("ghost", PASSWORD), ("a b", PASSWORD), ("x" * 120, PASSWORD)],
)
def test_all_failures_raise_the_same_generic_error(username: str, password: str) -> None:
    rig = Rig()
    with pytest.raises(InvalidCredentialsError) as info:
        rig.service.login(username, password, IP)
    assert str(info.value) == "invalid credentials"


def test_inactive_user_cannot_login_even_with_the_right_password() -> None:
    rig = Rig()
    rig.users.add(make_user("bob", active=False))
    with pytest.raises(InvalidCredentialsError):
        rig.service.login("bob", PASSWORD, IP)


def test_unknown_and_inactive_users_are_verified_against_the_dummy_hash() -> None:
    rig = Rig()
    rig.users.add(make_user("bob", active=False))
    for name in ("ghost", "bob", "alice"):
        with pytest.raises(InvalidCredentialsError):
            rig.service.login(name, "wrong password", IP)
    # One verify per attempt; only the existing active account got a real hash.
    assert rig.hasher.verify_calls == [False, False, True]


def test_failure_is_recorded_in_all_scopes_even_for_unknown_usernames() -> None:
    rig = Rig()
    with pytest.raises(InvalidCredentialsError):
        rig.service.login("ghost", "whatever password", IP)
    assert sorted(r[1] for r in rig.attempts.rows) == ["account", "ip", "ip_account"]
    assert all(not r[4] for r in rig.attempts.rows)


def test_failure_audit_has_only_hashed_keys() -> None:
    rig = Rig()
    with pytest.raises(InvalidCredentialsError):
        rig.service.login("ghost", "my secret attempt", IP)
    text = repr(rig.audit.events)
    for forbidden in ("ghost", "my secret attempt", IP):
        assert forbidden not in text
    assert rig.audit.names() == ["login.failure"]


def test_rehash_on_login_keeps_password_changed_at() -> None:
    rig = Rig()
    original = rig.users.get_by_id("id-alice")
    assert original is not None
    rig.users.update(replace(original, password_hash="old$" + PASSWORD[::-1]))
    rig.clock.advance(60)
    login(rig)
    stored = rig.users.get_by_id("id-alice")
    assert stored is not None
    assert stored.password_hash == "fake$" + PASSWORD[::-1]
    assert stored.password_changed_at == original.password_changed_at


# --------------------------------------------------------------- lockout


def test_pair_lockout_after_n_failures_blocks_even_the_correct_password() -> None:
    rig = Rig()
    rig.fail(5)
    with pytest.raises(LoginLockedError) as info:
        login(rig, ip="9.9.9.9")
    assert info.value.retry_after_seconds == 300
    assert "login.locked" in rig.audit.names()


def test_lock_check_happens_before_password_verification() -> None:
    rig = Rig()
    rig.fail(5)
    calls = len(rig.hasher.verify_calls)
    with pytest.raises(LoginLockedError):
        login(rig, ip="9.9.9.9")
    assert len(rig.hasher.verify_calls) == calls


def test_lock_is_identical_for_existing_and_unknown_accounts() -> None:
    rig = Rig()
    rig.fail(5, username="alice")
    rig.fail(5, username="ghost")
    outcomes = []
    for name in ("alice", "ghost"):
        with pytest.raises(LoginLockedError) as info:
            rig.service.login(name, PASSWORD, "9.9.9.9")
        outcomes.append((type(info.value), str(info.value), info.value.retry_after_seconds))
    assert outcomes[0] == outcomes[1]


def test_retry_after_counts_down_with_the_clock() -> None:
    rig = Rig()
    rig.fail(5)
    rig.clock.advance(100)
    with pytest.raises(LoginLockedError) as info:
        login(rig, ip="9.9.9.9")
    assert info.value.retry_after_seconds == 200


def test_lock_expires_and_next_lock_is_longer() -> None:
    rig = Rig()
    rig.fail(5)
    rig.clock.advance(301)
    login(rig, ip="9.9.9.9")  # correct password works again
    rig.fail(5)  # the success reset the pair counter, so a fresh lock of the base length
    with pytest.raises(LoginLockedError) as info:
        login(rig, ip="9.9.9.9")
    assert info.value.retry_after_seconds == 300


def test_progressive_lock_without_success_in_between() -> None:
    rig = Rig()
    rig.fail(5)
    rig.clock.advance(301)
    rig.fail(5)
    with pytest.raises(LoginLockedError) as info:
        login(rig, ip="9.9.9.9")
    assert info.value.retry_after_seconds == 600


def test_failures_outside_the_window_are_forgotten() -> None:
    rig = Rig()
    rig.fail(4)
    rig.clock.advance(16 * 60)
    rig.fail(4)
    login(rig, ip="9.9.9.9")  # 4 + 4 failures, never 5 inside one window


def test_success_resets_pair_and_account_counters() -> None:
    rig = Rig()
    rig.fail(4)
    login(rig, ip="9.9.9.9")
    rig.fail(4)
    login(rig, ip="9.9.9.9")  # would be locked if the first 4 still counted


def test_success_does_not_reset_the_ip_counter() -> None:
    """An attacker with one valid account must not wipe the address counter."""
    rig = Rig()
    rig.users.add(make_user("mallory"))
    for i in range(19):
        rig.fail(1, ip="6.6.6.6", username=f"victim-{i}")
        rig.service.login("mallory", PASSWORD, "6.6.6.6")
    rig.fail(1, ip="6.6.6.6", username="victim-y")
    with pytest.raises(LoginLockedError):
        rig.service.login("mallory", PASSWORD, "6.6.6.6")


def test_changing_username_does_not_bypass_the_ip_limit() -> None:
    rig = Rig()
    for i in range(20):
        rig.fail(1, ip="6.6.6.6", username=f"user{i}")
    with pytest.raises(LoginLockedError):
        rig.service.login("brand-new-name", "x" * 14, "6.6.6.6")
    with pytest.raises(LoginLockedError):
        rig.service.login("alice", PASSWORD, "6.6.6.6")
    # Another address is unaffected.
    login(rig, ip="7.7.7.7")


@pytest.mark.parametrize("variant", ["ALICE", " alice ", "Alice"])
def test_lockout_cannot_be_bypassed_with_case_or_spaces(variant: str) -> None:
    rig = Rig()
    rig.fail(5)
    with pytest.raises(LoginLockedError):
        rig.service.login(variant, PASSWORD, "9.9.9.9")


def test_one_address_alone_cannot_lock_the_account_for_others() -> None:
    rig = Rig()
    rig.fail(5, ip="6.6.6.6")  # locks 6.6.6.6 for alice
    with pytest.raises(LoginLockedError):
        login(rig, ip="6.6.6.6")
    login(rig, ip="2.2.2.2")  # the victim is not locked out


def test_distributed_attack_locks_unknown_addresses_but_not_trusted_ones() -> None:
    rig = Rig()
    login(rig, ip="2.2.2.2")  # alice's usual address becomes trusted
    for i in range(15):
        rig.fail(1, ip=f"8.8.8.{i}")
    with pytest.raises(LoginLockedError):
        login(rig, ip="3.3.3.3")  # new address: blocked by the account-wide lock
    login(rig, ip="2.2.2.2")  # trusted address keeps working


def test_trust_expires_with_the_window() -> None:
    rig = Rig()
    login(rig, ip="2.2.2.2")
    rig.clock.advance(31 * 24 * 3600)
    for i in range(15):
        rig.fail(1, ip=f"8.8.8.{i}")
    with pytest.raises(LoginLockedError):
        login(rig, ip="2.2.2.2")


def test_distributed_lock_is_the_same_for_unknown_accounts() -> None:
    rig = Rig()
    for i in range(15):
        rig.fail(1, ip=f"8.8.8.{i}", username="ghost")
        rig.fail(1, ip=f"8.8.8.{i}", username="alice")
    results = []
    for name in ("ghost", "alice"):
        with pytest.raises(LoginLockedError) as info:
            rig.service.login(name, PASSWORD, "3.3.3.3")
        results.append(info.value.retry_after_seconds)
    assert results[0] == results[1]


def test_old_attempts_are_purged_eventually() -> None:
    rig = Rig()
    rig.fail(2)
    rig.clock.advance(40 * 24 * 3600)
    login(rig, ip="2.2.2.2")
    assert all(r[3] >= rig.clock.now() - timedelta(days=31) for r in rig.attempts.rows)


# --------------------------------------------------------------- refresh


def test_refresh_rotates_the_token() -> None:
    rig = Rig()
    first = login(rig)
    rig.clock.advance(60)
    second = rig.service.refresh(first.refresh_token)
    assert second.refresh_token != first.refresh_token
    assert rig.service.current_user(second.access_token).id == "id-alice"
    assert "token.refresh" in rig.audit.names()


def test_refresh_token_is_stored_only_as_sha256() -> None:
    rig = Rig()
    session = login(rig)
    stored = next(iter(rig.refresh.rows.values()))
    assert stored.token_hash != session.refresh_token
    assert len(stored.token_hash) == 64
    assert session.refresh_token not in repr(rig.refresh.rows)


def test_reuse_revokes_the_whole_family_including_the_new_token() -> None:
    rig = Rig()
    first = login(rig)
    second = rig.service.refresh(first.refresh_token)
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(first.refresh_token)  # replay of the used token
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(second.refresh_token)  # the legitimate newest token died too
    with pytest.raises(NotAuthenticatedError):
        rig.service.current_user(second.access_token)  # and so did its access token
    assert "token.reuse_detected" in rig.audit.names()


def test_reuse_does_not_touch_other_sessions() -> None:
    rig = Rig()
    first, other = login(rig), login(rig)
    rig.service.refresh(first.refresh_token)
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(first.refresh_token)
    rig.service.refresh(other.refresh_token)


def test_expired_refresh_token_is_denied() -> None:
    rig = Rig()
    session = login(rig)
    rig.clock.advance(30 * 24 * 3600 + 1)
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(session.refresh_token)


def test_session_has_an_absolute_lifetime_despite_rotation() -> None:
    rig = Rig()
    session = login(rig)
    for _ in range(4):  # 4 * 29 days > 90 days
        rig.clock.advance(29 * 24 * 3600)
        try:
            session = rig.service.refresh(session.refresh_token)
        except InvalidSessionError:
            return
    pytest.fail("session outlived the absolute limit")


def test_rotated_token_never_outlives_the_absolute_limit() -> None:
    rig = Rig()
    session = login(rig)
    for _ in range(3):
        rig.clock.advance(29 * 24 * 3600)
        session = rig.service.refresh(session.refresh_token)
    assert session.refresh_expires_at <= rig.clock.now().replace(microsecond=500_000) + timedelta(
        days=90
    )
    started = min(r.created_at for r in rig.refresh.rows.values())
    assert session.refresh_expires_at <= started + timedelta(days=90)


@pytest.mark.parametrize("bad", [None, "", "x", "A" * 1000])
def test_unknown_refresh_tokens_are_denied(bad: str | None) -> None:
    with pytest.raises(InvalidSessionError):
        Rig().service.refresh(bad)


def test_refresh_denied_for_deactivated_user() -> None:
    rig = Rig()
    session = login(rig)
    rig.users.update(replace(make_user(), is_active=False))
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(session.refresh_token)


def test_refresh_denied_after_password_reset_by_admin() -> None:
    rig = Rig()
    session = login(rig)
    rig.clock.advance(5)
    rig.users.update(replace(make_user(), password_changed_at=rig.clock.now()))
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(session.refresh_token)


# ---------------------------------------------------------------- logout


def test_logout_revokes_the_family() -> None:
    rig = Rig()
    session = login(rig)
    rig.service.logout(session.refresh_token, session.access_token)
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(session.refresh_token)
    with pytest.raises(NotAuthenticatedError):
        rig.service.current_user(session.access_token)
    assert "logout" in rig.audit.names()


def test_logout_with_only_the_access_token_works() -> None:
    rig = Rig()
    session = login(rig)
    rig.service.logout(None, session.access_token)
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(session.refresh_token)


@pytest.mark.parametrize("junk", [None, "", "junk", "A" * 5000])
def test_logout_is_idempotent_and_quiet_on_bad_input(junk: str | None) -> None:
    rig = Rig()
    rig.service.logout(junk, junk)
    assert rig.audit.events == []


# ------------------------------------------------------- change password


def test_change_password_revokes_sessions_and_old_access_tokens() -> None:
    rig = Rig()
    old = login(rig)
    rig.clock.advance(10)
    new = rig.service.change_password("id-alice", PASSWORD, "a brand new passphrase", IP)
    with pytest.raises(NotAuthenticatedError):
        rig.service.current_user(old.access_token)
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(old.refresh_token)
    assert rig.service.current_user(new.access_token).id == "id-alice"
    rig.service.refresh(new.refresh_token)  # the new session is usable
    assert "password.changed" in rig.audit.names()
    rig.service.login("alice", "a brand new passphrase", IP)
    with pytest.raises(InvalidCredentialsError):
        rig.service.login("alice", PASSWORD, IP)


def test_access_token_issued_before_the_change_is_rejected_by_iat_alone() -> None:
    """Even if the session were not revoked, iat < password_changed_at kills the token."""
    rig = Rig()
    old = login(rig)
    rig.clock.advance(10)
    user = rig.users.get_by_id("id-alice")
    assert user is not None
    rig.users.update(replace(user, password_changed_at=rig.clock.now()))
    with pytest.raises(NotAuthenticatedError):
        rig.service.current_user(old.access_token)


def test_change_password_requires_the_current_password() -> None:
    rig = Rig()
    with pytest.raises(CurrentPasswordError):
        rig.service.change_password("id-alice", "not the password", "a brand new passphrase", IP)
    assert rig.users.get_by_id("id-alice").password_hash == make_user().password_hash  # type: ignore[union-attr]


def test_change_password_applies_policy_and_rejects_reuse() -> None:
    rig = Rig()
    with pytest.raises(PasswordPolicyError):
        rig.service.change_password("id-alice", PASSWORD, "short", IP)
    with pytest.raises(PasswordPolicyError):
        rig.service.change_password("id-alice", PASSWORD, PASSWORD, IP)


def test_change_password_is_protected_by_the_lockout() -> None:
    rig = Rig()
    for _ in range(5):
        with pytest.raises(CurrentPasswordError):
            rig.service.change_password(
                "id-alice", "guess guess guess", "a brand new passphrase", IP
            )
    with pytest.raises(LoginLockedError):
        rig.service.change_password("id-alice", PASSWORD, "a brand new passphrase", IP)


# ---------------------------------------------------------- current user


@pytest.mark.parametrize("token", [None, "", "garbage"])
def test_current_user_rejects_missing_or_invalid_token(token: str | None) -> None:
    with pytest.raises(NotAuthenticatedError):
        Rig().service.current_user(token)


def test_deactivated_user_loses_access_immediately() -> None:
    rig = Rig()
    session = login(rig)
    user = rig.users.get_by_id("id-alice")
    assert user is not None
    rig.users.update(replace(user, is_active=False))
    with pytest.raises(NotAuthenticatedError):
        rig.service.current_user(session.access_token)


def test_access_token_expires() -> None:
    rig = Rig()
    session = login(rig)
    rig.clock.advance(15 * 60)
    with pytest.raises(NotAuthenticatedError):
        rig.service.current_user(session.access_token)


def test_token_of_a_deleted_user_or_unknown_session_is_rejected() -> None:
    rig = Rig()
    session = login(rig)
    rig.refresh.rows.clear()  # sid no longer exists
    with pytest.raises(NotAuthenticatedError):
        rig.service.current_user(session.access_token)


def test_roles_come_from_the_database_not_the_token() -> None:
    rig = Rig()
    session = login(rig)
    user = rig.users.get_by_id("id-alice")
    assert user is not None
    rig.users.update(replace(user, role=Role.ADMIN))
    assert rig.service.current_user(session.access_token).role is Role.ADMIN
