"""Forged/stale access tokens over HTTP, and secrets never leaking into logs or responses."""

import base64
import json
import logging

import jwt
import pytest
from app.core.keys import LABEL_ACCESS_JWT, derive_key

from auth_fakes import PASSWORD, TEST_SECRET, Env

# HS512 forgeries intentionally use a 32-byte key; the library warns about key length.
pytestmark = pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")

ME = "/api/v1/auth/me"


def b64(data: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def claims(env: Env, user_id: str, sid: str, **over: object) -> dict[str, object]:
    now = int(env.clock.now().timestamp())
    base: dict[str, object] = {
        "sub": user_id,
        "sid": sid,
        "jti": "j",
        "iat": now,
        "nbf": now,
        "exp": now + 600,
    }
    base.update(over)
    return base


def session_ids(env: Env) -> tuple[str, str]:
    """(user id, live session id) of a fresh login, read from the issued token itself."""
    client = env.client("10.5.5.5")
    client.login()
    token = client.cookie("access_token")
    assert token
    payload = jwt.decode(token, options={"verify_signature": False})
    return payload["sub"], payload["sid"]


def status_with(env: Env, token: str) -> int:
    return env.client("10.7.7.7").get(ME, cookies={"access_token": token}).status_code


def test_forged_tokens_are_401(env: Env) -> None:
    user_id, sid = session_ids(env)
    good_key = derive_key(TEST_SECRET, LABEL_ACCESS_JWT)
    valid = jwt.encode(claims(env, user_id, sid), good_key, algorithm="HS256")
    assert status_with(env, valid) == 200  # control: the helper itself works

    head, body, sig = valid.split(".")
    forged = {
        "alg none": f"{b64({'alg': 'none', 'typ': 'JWT'})}.{body}.",
        "alg none + sig": f"{b64({'alg': 'none'})}.{body}.{sig}",
        "other algorithm": jwt.encode(claims(env, user_id, sid), good_key, algorithm="HS512"),
        "bad signature": f"{head}.{body}.{('A' if sig[0] != 'A' else 'B') + sig[1:]}",
        "wrong key": jwt.encode(claims(env, user_id, sid), b"x" * 32, algorithm="HS256"),
        "raw secret as key": jwt.encode(
            claims(env, user_id, sid), TEST_SECRET.encode(), algorithm="HS256"
        ),
        "tampered sub": f"{head}.{b64(claims(env, 'someone-else', sid))}.{sig}",
        "garbage": "not-a-jwt",
        "empty parts": "..",
    }
    for name, token in forged.items():
        assert status_with(env, token) == 401, name


def test_expired_token_is_401(env: Env) -> None:
    user_id, sid = session_ids(env)
    key = derive_key(TEST_SECRET, LABEL_ACCESS_JWT)
    now = int(env.clock.now().timestamp())
    expired = jwt.encode(claims(env, user_id, sid, exp=now - 1), key, algorithm="HS256")
    assert status_with(env, expired) == 401


def test_real_token_expires_when_the_clock_passes_its_ttl(env: Env) -> None:
    client = env.client()
    client.login()
    env.clock.advance(env.settings.ACCESS_TOKEN_TTL_SECONDS - 1)
    assert client.get(ME).status_code == 200
    env.clock.advance(2)
    assert client.get(ME).status_code == 401


@pytest.mark.parametrize("missing", ["exp", "iat", "nbf", "sub", "sid", "jti"])
def test_token_missing_a_required_claim_is_401(env: Env, missing: str) -> None:
    user_id, sid = session_ids(env)
    payload = claims(env, user_id, sid)
    del payload[missing]
    token = jwt.encode(payload, derive_key(TEST_SECRET, LABEL_ACCESS_JWT), algorithm="HS256")
    assert status_with(env, token) == 401


def test_validly_signed_token_for_an_unknown_or_revoked_session_is_401(env: Env) -> None:
    user_id, sid = session_ids(env)
    key = derive_key(TEST_SECRET, LABEL_ACCESS_JWT)
    unknown_sid = jwt.encode(claims(env, user_id, "no-such-session"), key, algorithm="HS256")
    assert status_with(env, unknown_sid) == 401
    env.container.auth_service.logout(None, jwt.encode(claims(env, user_id, sid), key, "HS256"))
    revoked = jwt.encode(claims(env, user_id, sid), key, algorithm="HS256")
    assert status_with(env, revoked) == 401


def test_session_of_another_user_cannot_be_borrowed(env: Env) -> None:
    """A token whose `sub` is user B but whose `sid` belongs to user A's session is rejected."""
    bob = env.create_user("bob")
    _, alice_sid = session_ids(env)
    key = derive_key(TEST_SECRET, LABEL_ACCESS_JWT)
    token = jwt.encode(claims(env, bob.id, alice_sid), key, algorithm="HS256")
    assert status_with(env, token) == 401


def test_token_issued_before_a_password_change_is_401_even_if_still_signed_and_live(
    env: Env,
) -> None:
    user_id, sid = session_ids(env)
    key = derive_key(TEST_SECRET, LABEL_ACCESS_JWT)
    old = jwt.encode(claims(env, user_id, sid), key, algorithm="HS256")
    assert status_with(env, old) == 200
    env.clock.advance(10)
    env.container.user_service.reset_password("alice", "a brand new passphrase")
    assert status_with(env, old) == 401  # iat < password_changed_at, sid not even revoked


def test_access_token_in_authorization_header_or_query_is_ignored(env: Env) -> None:
    user_id, sid = session_ids(env)
    token = jwt.encode(
        claims(env, user_id, sid), derive_key(TEST_SECRET, LABEL_ACCESS_JWT), algorithm="HS256"
    )
    client = env.client("10.8.8.8")
    assert client.http.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.http.get(f"{ME}?access_token={token}").status_code == 401


# ------------------------------------------------------- no secrets anywhere


def test_secrets_never_reach_logs_or_responses(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    secret_password = "my very secret passphrase 123"
    client = env.client()
    bodies: list[str] = []
    with caplog.at_level(logging.DEBUG):
        bodies.append(client.login("alice", secret_password).text)  # failure
        bodies.append(client.login().text)
        access, refresh = (
            client.cookie("access_token") or "?",
            client.cookie("refresh_token") or "?",
        )
        csrf = client.cookie("csrf_token") or "?"
        bodies.append(client.get(ME).text)
        bodies.append(client.post("/api/v1/auth/refresh").text)
        bodies.append(
            client.post(
                "/api/v1/auth/change-password",
                {"current_password": secret_password, "new_password": "x"},
            ).text
        )
        bodies.append(client.http.post("/api/v1/auth/login", json={"username": "a"}).text)  # 403
        for _ in range(5):
            client.login("alice", secret_password)
        bodies.append(client.login("alice", PASSWORD).text)  # locked
        bodies.append(client.post("/api/v1/auth/logout", {"password": secret_password}).text)
    forbidden = [secret_password, PASSWORD, access, refresh, csrf, TEST_SECRET, "argon2id"]
    haystack = "\n".join([*bodies, caplog.text, *(r.getMessage() for r in caplog.records)])
    for secret in forbidden:
        assert secret not in haystack, secret[:6]


def test_unexpected_errors_are_generic_and_leak_nothing(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    from fastapi.testclient import TestClient

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(f"db exploded with {PASSWORD} and {TEST_SECRET}")

    env.container.auth_service.login = boom  # type: ignore[method-assign,assignment]
    client = env.client()
    client.csrf()
    http = TestClient(env.app, base_url=client.ORIGIN, raise_server_exceptions=False)
    http.cookies.set("csrf_token", client.cookie("csrf_token") or "")
    response = http.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": PASSWORD},
        headers={"Origin": client.ORIGIN, "X-CSRF-Token": client.cookie("csrf_token") or ""},
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert PASSWORD not in response.text and TEST_SECRET not in response.text


def test_repr_of_domain_objects_hides_secrets(env: Env) -> None:
    user = env.container.user_service.list_users()[0]
    client = env.client()
    client.login()
    session = env.container.auth_service.login("alice", PASSWORD, "1.2.3.4")
    assert user.password_hash not in repr(user)
    assert session.access_token not in repr(session)
    assert session.refresh_token not in repr(session)
