"""REG-018: lost update on users (rehash at login / change_password vs. a CLI deactivation).

Bug: `UserRepository.update` wrote the WHOLE user back from an object read before the slow Argon2
step, so a deactivation (or password reset) made by the CLI in the middle was silently reverted
(the account came back active / with the old password).
Fix: only targeted writes exist now. `replace_password_hash` is a compare-and-set that applies
only to an ACTIVE user whose hash is still the one that was verified; `set_password_hash` and
`deactivate` touch only their own columns.
"""

from datetime import UTC, datetime

import pytest
from app.adapters.persistence.user_repository import SqlAlchemyUserRepository
from app.domain.user import Role, User
from sqlalchemy.orm import Session, sessionmaker

from auth_fakes import PASSWORD, START, Rig, make_user

IP = "1.1.1.1"
LEGACY_HASH = "old$" + PASSWORD[::-1]  # FakeHasher.needs_rehash() is True for it


def _rig_with_legacy_hash() -> Rig:
    rig = Rig()
    rig.users.update(_with_hash(make_user(), LEGACY_HASH))
    return rig


def _with_hash(user: User, password_hash: str) -> User:
    from dataclasses import replace

    return replace(user, password_hash=password_hash)


def _during_next_hash(rig: Rig, monkeypatch: pytest.MonkeyPatch, action) -> None:  # type: ignore[no-untyped-def]
    """Run `action` while the (slow) hash is being computed, i.e. between read and write."""
    real_hash = rig.hasher.hash

    def hash_then_race(password: str) -> str:
        action()
        return real_hash(password)

    monkeypatch.setattr(rig.hasher, "hash", hash_then_race)


def test_rehash_at_login_does_not_undo_a_deactivation(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _rig_with_legacy_hash()
    _during_next_hash(rig, monkeypatch, lambda: rig.users.deactivate("id-alice", rig.clock.now()))
    rig.service.login("alice", PASSWORD, IP)
    stored = rig.users.get_by_id("id-alice")
    assert stored is not None
    assert stored.is_active is False
    assert stored.password_hash == LEGACY_HASH  # the rehash was dropped, not applied


def test_rehash_at_login_does_not_undo_a_password_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _rig_with_legacy_hash()
    reset = rig.hasher.hash("password chosen by the admin")
    _during_next_hash(
        rig, monkeypatch, lambda: rig.users.set_password_hash("id-alice", reset, rig.clock.now())
    )
    rig.service.login("alice", PASSWORD, IP)
    stored = rig.users.get_by_id("id-alice")
    assert stored is not None
    assert stored.password_hash == reset  # not the rehash of the OLD password


def test_change_password_does_not_undo_a_deactivation(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domain.auth import NotAuthenticatedError

    rig = Rig()
    before = rig.users.get_by_id("id-alice")
    assert before is not None
    _during_next_hash(rig, monkeypatch, lambda: rig.users.deactivate("id-alice", rig.clock.now()))
    with pytest.raises(NotAuthenticatedError):
        rig.service.change_password("id-alice", PASSWORD, "a brand new passphrase", IP)
    stored = rig.users.get_by_id("id-alice")
    assert stored is not None
    assert stored.is_active is False
    assert stored.password_hash == before.password_hash


# --- the real SQL adapter -----------------------------------------------------------------


def _user() -> User:
    return User("id-1", "alice", "hash-1", Role.USER, True, "system", START, START, START)


def test_sql_compare_and_set_skips_inactive_or_changed_users(
    session_factory: sessionmaker[Session],
) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    repo.add(_user())
    later = datetime(2026, 12, 1, tzinfo=UTC)

    repo.deactivate("id-1", later)
    assert not repo.replace_password_hash(
        "id-1", expected_hash="hash-1", new_hash="hash-2", now=later, password_changed=True
    )
    stored = repo.get_by_id("id-1")
    assert stored is not None
    assert (stored.is_active, stored.password_hash) == (False, "hash-1")


def test_sql_compare_and_set_requires_the_verified_hash(
    session_factory: sessionmaker[Session],
) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    repo.add(_user())
    later = datetime(2026, 12, 1, tzinfo=UTC)
    repo.set_password_hash("id-1", "admin-hash", later)  # reset while we "were hashing"
    assert not repo.replace_password_hash(
        "id-1", expected_hash="hash-1", new_hash="rehash", now=later, password_changed=False
    )
    stored = repo.get_by_id("id-1")
    assert stored is not None
    assert stored.password_hash == "admin-hash"


def test_sql_rehash_keeps_password_changed_at_but_change_updates_it(
    session_factory: sessionmaker[Session],
) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    repo.add(_user())
    t1, t2 = datetime(2026, 12, 1, tzinfo=UTC), datetime(2026, 12, 2, tzinfo=UTC)
    assert repo.replace_password_hash(
        "id-1", expected_hash="hash-1", new_hash="hash-2", now=t1, password_changed=False
    )
    after_rehash = repo.get_by_id("id-1")
    assert after_rehash is not None
    assert (after_rehash.password_hash, after_rehash.password_changed_at) == ("hash-2", START)
    assert after_rehash.updated_at == t1
    assert repo.replace_password_hash(
        "id-1", expected_hash="hash-2", new_hash="hash-3", now=t2, password_changed=True
    )
    after_change = repo.get_by_id("id-1")
    assert after_change is not None
    assert after_change.password_changed_at == t2


def test_sql_deactivate_and_reset_touch_only_their_own_columns(
    session_factory: sessionmaker[Session],
) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    repo.add(_user())
    later = datetime(2026, 12, 1, tzinfo=UTC)
    repo.deactivate("id-1", later)
    repo.set_password_hash("id-1", "admin-hash", later)  # admin reset works on inactive users
    stored = repo.get_by_id("id-1")
    assert stored is not None
    assert (stored.is_active, stored.password_hash, stored.role) == (False, "admin-hash", Role.USER)


def test_sql_missing_user_raises_not_found(session_factory: sessionmaker[Session]) -> None:
    from app.domain.user import UserNotFoundError

    repo = SqlAlchemyUserRepository(session_factory)
    now = datetime(2026, 12, 1, tzinfo=UTC)
    with pytest.raises(UserNotFoundError):
        repo.deactivate("ghost", now)
    with pytest.raises(UserNotFoundError):
        repo.set_password_hash("ghost", "h", now)
    assert not repo.replace_password_hash(
        "ghost", expected_hash="a", new_hash="b", now=now, password_changed=True
    )
