"""/api/v1/auth end to end: real app, real SQLite, fake clock."""

from app.domain.user import Role
from sqlalchemy import select

from auth_fakes import PASSWORD, Env

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
CHANGE = "/api/v1/auth/change-password"
NEW_PASSWORD = "a brand new passphrase"


def test_login_ok_returns_user_without_tokens_and_sets_cookies(env: Env) -> None:
    client = env.client()
    response = client.login()
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "username", "role", "theme_pref"}
    assert body["username"] == "alice"
    text = response.text
    assert client.cookie("access_token") not in text
    assert client.cookie("refresh_token") not in text
    assert "hash" not in text and "password" not in text


def test_me_returns_the_logged_in_user(env: Env) -> None:
    client = env.client()
    client.login()
    response = client.get(ME)
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_me_only_returns_the_caller_not_other_users(env: Env) -> None:
    env.create_user("bob")
    alice, bob = env.client("10.0.0.1"), env.client("10.0.0.2")
    alice.login()
    bob.login("bob")
    assert alice.get(ME).json()["username"] == "alice"
    assert bob.get(ME).json()["username"] == "bob"
    assert "bob" not in alice.get(ME).text


def test_me_requires_authentication(env: Env) -> None:
    assert env.client().get(ME).status_code == 401


def test_login_failure_is_401_generic_and_identical_for_unknown_user(env: Env) -> None:
    client = env.client()
    wrong = client.login("alice", "not the password")
    unknown = client.login("ghost", "not the password")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid credentials"}
    assert "set-cookie" not in wrong.headers and "set-cookie" not in unknown.headers
    assert sorted(wrong.headers.keys()) == sorted(unknown.headers.keys())


def test_login_validation_errors_do_not_echo_input(env: Env) -> None:
    client = env.client()
    response = client.post(LOGIN, {"username": "alice", "password": "x", "extra": "forbidden"})
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
    response = client.post(LOGIN, {"username": "alice", "password": 12345})
    assert response.status_code == 422
    assert "12345" not in response.text
    response = client.post(LOGIN, {"username": "alice", "password": "p" * 2000})
    assert response.status_code == 422
    assert "ppp" not in response.text


def test_login_is_case_and_space_insensitive_for_username(env: Env) -> None:
    assert env.client().login("  ALICE ").status_code == 200


def test_refresh_rotates_and_new_access_works(env: Env) -> None:
    client = env.client()
    client.login()
    old_refresh, old_access = client.cookie("refresh_token"), client.cookie("access_token")
    env.clock.advance(60)
    response = client.post(REFRESH)
    assert response.status_code == 204
    assert response.content == b""
    assert client.cookie("refresh_token") != old_refresh
    assert client.cookie("access_token") != old_access
    assert client.get(ME).status_code == 200


def test_refresh_reuse_revokes_the_family_and_the_new_token(env: Env) -> None:
    client = env.client()
    client.login()
    old = client.cookie("refresh_token")
    assert old
    env.clock.advance(60)
    assert client.post(REFRESH).status_code == 204
    newest = client.cookie("refresh_token")
    assert newest
    # A replay INSIDE the short grace window is tolerated (REG-010); this is a late replay.
    env.clock.advance(env.settings.REFRESH_REUSE_GRACE_SECONDS + 1)
    attacker = env.client("66.66.66.66")
    attacker.csrf()
    replay = attacker.post(REFRESH, cookies={"refresh_token": old})
    assert replay.status_code == 401
    # The legitimate (newest) refresh token and its access token are dead too.
    assert client.post(REFRESH).status_code == 401
    assert client.get(ME).status_code == 401


def test_refresh_without_cookie_is_401_and_clears_cookies(env: Env) -> None:
    client = env.client()
    response = client.post(REFRESH)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_expired_refresh_token_is_denied(env: Env) -> None:
    client = env.client()
    client.login()
    env.clock.advance(env.settings.REFRESH_TOKEN_TTL_SECONDS + 1)
    assert client.post(REFRESH).status_code == 401


def test_logout_revokes_session_and_clears_cookies(env: Env) -> None:
    client = env.client()
    client.login()
    refresh = client.cookie("refresh_token")
    assert refresh
    response = client.post(LOGOUT)
    assert response.status_code == 204
    cleared = " ".join(response.headers.get_list("set-cookie")).lower()
    assert "access_token=" in cleared and "refresh_token=" in cleared
    assert "max-age=0" in cleared
    assert client.get(ME).status_code == 401
    other = env.client("10.0.0.9")
    other.csrf()
    assert other.post(REFRESH, cookies={"refresh_token": refresh}).status_code == 401


def test_logout_without_session_is_still_204(env: Env) -> None:
    assert env.client().post(LOGOUT).status_code == 204


def test_change_password_revokes_sessions_and_old_access_token(env: Env) -> None:
    phone, laptop = env.client("10.0.0.1"), env.client("10.0.0.2")
    phone.login()
    laptop.login()
    old_access = laptop.cookie("access_token")
    assert old_access
    env.clock.advance(30)
    response = phone.post(CHANGE, {"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 204
    assert phone.get(ME).status_code == 200  # the changing session gets a fresh one
    assert laptop.get(ME).status_code == 401  # other sessions are gone
    assert laptop.get(ME, cookies={"access_token": old_access}).status_code == 401
    assert env.client("10.0.0.3").login("alice", PASSWORD).status_code == 401
    assert env.client("10.0.0.3").login("alice", NEW_PASSWORD).status_code == 200


def test_change_password_needs_the_current_password_and_policy(env: Env) -> None:
    client = env.client()
    client.login()
    wrong = client.post(
        CHANGE, {"current_password": "nope nope nope", "new_password": NEW_PASSWORD}
    )
    assert wrong.status_code == 403
    weak = client.post(CHANGE, {"current_password": PASSWORD, "new_password": "short"})
    assert weak.status_code == 422
    assert "short" not in weak.text
    assert client.get(ME).status_code == 200  # nothing changed


def test_change_password_requires_authentication(env: Env) -> None:
    response = env.client().post(
        CHANGE, {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 401


def test_deactivated_user_loses_access_immediately(env: Env) -> None:
    client = env.client()
    client.login()
    assert client.get(ME).status_code == 200
    env.container.user_service.deactivate_user("alice")
    assert client.get(ME).status_code == 401
    assert client.post(REFRESH).status_code == 401
    assert env.client("10.0.0.7").login().status_code == 401


def test_admin_reset_password_invalidates_existing_sessions(env: Env) -> None:
    client = env.client()
    client.login()
    env.clock.advance(5)
    env.container.user_service.reset_password("alice", NEW_PASSWORD)
    assert client.get(ME).status_code == 401
    assert client.post(REFRESH).status_code == 401


def test_audit_trail_has_the_expected_events_and_no_secrets(env: Env) -> None:
    from app.adapters.persistence.models import AuditLogRow

    client = env.client()
    client.login("alice", "wrong password value")
    client.login()
    seen = [client.cookie("access_token"), client.cookie("refresh_token")]
    env.clock.advance(1)
    client.post(REFRESH)
    seen += [client.cookie("access_token"), client.cookie("refresh_token")]
    client.post(CHANGE, {"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    client.post(LOGOUT)
    with env.container.session_factory() as session:
        rows = session.scalars(select(AuditLogRow)).all()
    events = {row.event for row in rows}
    assert {
        "user.created",
        "login.failure",
        "login.success",
        "token.refresh",
        "password.changed",
        "logout",
    } <= events
    dump = repr([(r.event, r.user_id, r.ip, r.detail) for r in rows])
    for secret in (
        "wrong password value",
        PASSWORD,
        NEW_PASSWORD,
        *[v for v in seen if v],
        "10.0.0.1",
        "argon2",
        env.settings.SECRET_KEY,
    ):
        assert secret not in dump


def test_require_admin_dependency_blocks_regular_users(env: Env) -> None:
    from app.api.deps import require_admin
    from fastapi import Depends

    @env.app.get("/api/v1/_admin-only")
    def admin_only(user: object = Depends(require_admin)) -> dict[str, str]:  # noqa: B008
        return {"ok": "yes"}

    env.create_user("boss", role=Role.ADMIN)
    regular, boss, anonymous = (
        env.client("10.0.0.1"),
        env.client("10.0.0.2"),
        env.client("10.0.0.3"),
    )
    regular.login()
    boss.login("boss")
    assert regular.get("/api/v1/_admin-only").status_code == 403
    assert boss.get("/api/v1/_admin-only").status_code == 200
    assert anonymous.get("/api/v1/_admin-only").status_code == 401
