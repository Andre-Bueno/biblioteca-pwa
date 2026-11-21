"""CSRF: signed double-submit + Origin/Fetch-Metadata/Referer checks on every non-safe /api call."""

import hashlib
import hmac

import pytest
from app.api.csrf import CsrfTokenSigner
from app.core.keys import LABEL_CSRF, derive_key
from fastapi.testclient import TestClient

from auth_fakes import PASSWORD, TEST_SECRET, Env

LOGIN = "/api/v1/auth/login"
ORIGIN = "https://testserver"
BODY = {"username": "alice", "password": PASSWORD}


def raw_post(
    env: Env,
    *,
    path: str = LOGIN,
    cookie: str | None = None,
    header: str | None = None,
    extra: dict[str, str] | None = None,
    origin: str | None = ORIGIN,
    method: str = "POST",
) -> int:
    headers: dict[str, str] = {}
    if origin is not None:
        headers["Origin"] = origin
    if cookie is not None:
        headers["Cookie"] = f"csrf_token={cookie}"
    if header is not None:
        headers["X-CSRF-Token"] = header
    headers.update(extra or {})
    http = TestClient(env.app, base_url=ORIGIN, client=("10.1.1.1", 1))
    return http.request(method, path, json=BODY, headers=headers).status_code


def good_token() -> str:
    return CsrfTokenSigner(derive_key(TEST_SECRET, LABEL_CSRF)).issue()


def test_valid_token_and_origin_is_accepted(env: Env) -> None:
    token = good_token()
    assert raw_post(env, cookie=token, header=token) == 200


def test_post_without_any_token_is_403_even_for_login(env: Env) -> None:
    assert raw_post(env) == 403


def test_post_with_cookie_but_no_header_is_403(env: Env) -> None:
    assert raw_post(env, cookie=good_token()) == 403


def test_post_with_header_but_no_cookie_is_403(env: Env) -> None:
    assert raw_post(env, header=good_token()) == 403


def test_mismatched_cookie_and_header_is_403(env: Env) -> None:
    assert raw_post(env, cookie=good_token(), header=good_token()) == 403


def test_unsigned_token_is_403_even_if_cookie_equals_header(env: Env) -> None:
    """Plain double-submit would pass this; the signature makes planted cookies useless."""
    assert raw_post(env, cookie="attacker-chosen-value", header="attacker-chosen-value") == 403


def test_token_signed_with_another_key_is_403(env: Env) -> None:
    forged = CsrfTokenSigner(b"x" * 32).issue()
    assert raw_post(env, cookie=forged, header=forged) == 403


def test_tampered_nonce_is_403(env: Env) -> None:
    nonce, sig = good_token().split(".")
    tampered = f"{nonce[:-1]}{'A' if nonce[-1] != 'A' else 'B'}.{sig}"
    assert raw_post(env, cookie=tampered, header=tampered) == 403


def test_token_made_with_the_raw_secret_instead_of_the_subkey_is_403(env: Env) -> None:
    nonce = "A" * 43
    sig = hmac.new(TEST_SECRET.encode(), nonce.encode(), hashlib.sha256).hexdigest()
    token = f"{nonce}.{sig}"
    assert raw_post(env, cookie=token, header=token) == 403


@pytest.mark.parametrize("token", ["", ".", "a.", ".b", "a.b.c", "A" * 5000])
def test_malformed_tokens_are_403(env: Env, token: str) -> None:
    assert raw_post(env, cookie=token, header=token) == 403


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "null", "http://testserver.evil.com", "x"]
)
def test_foreign_origin_is_403(env: Env, origin: str) -> None:
    token = good_token()
    assert raw_post(env, cookie=token, header=token, origin=origin) == 403


def test_no_origin_and_no_metadata_and_no_referer_is_403(env: Env) -> None:
    token = good_token()
    assert raw_post(env, cookie=token, header=token, origin=None) == 403


@pytest.mark.parametrize("site", ["cross-site", "same-site", "bogus"])
def test_fetch_metadata_other_than_same_origin_is_403(env: Env, site: str) -> None:
    token = good_token()
    assert (
        raw_post(env, cookie=token, header=token, origin=None, extra={"Sec-Fetch-Site": site})
        == 403
    )


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_fetch_metadata_same_origin_is_accepted_without_origin(env: Env, site: str) -> None:
    token = good_token()
    status = raw_post(env, cookie=token, header=token, origin=None, extra={"Sec-Fetch-Site": site})
    assert status == 200


def test_valid_referer_is_accepted_without_origin(env: Env) -> None:
    token = good_token()
    extra = {"Referer": "https://testserver/login"}
    assert raw_post(env, cookie=token, header=token, origin=None, extra=extra) == 200


def test_foreign_or_junk_referer_is_403(env: Env) -> None:
    token = good_token()
    for referer in ("https://evil.example/x", "not a url", ""):
        extra = {"Referer": referer}
        assert raw_post(env, cookie=token, header=token, origin=None, extra=extra) == 403


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_unsafe_method_is_checked(env: Env, method: str) -> None:
    assert raw_post(env, method=method, path="/api/v1/anything") == 403


def test_safe_methods_do_not_need_a_token(env: Env) -> None:
    http = TestClient(env.app, base_url=ORIGIN)
    assert http.get("/api/v1/health").status_code == 200
    assert http.get("/api/v1/auth/csrf").status_code == 204
    assert http.head("/api/v1/health").status_code in (200, 405)
    assert http.options("/api/v1/health").status_code != 403


def test_non_api_paths_are_not_subject_to_csrf(env: Env) -> None:
    http = TestClient(env.app, base_url=ORIGIN)
    assert http.post("/somewhere-else", json={}).status_code == 404


def test_rejection_is_generic_and_identical_for_every_reason(env: Env) -> None:
    token = good_token()
    http = TestClient(env.app, base_url=ORIGIN)
    bodies = set()
    for headers in (
        {},
        {"Origin": ORIGIN},
        {"Origin": "https://evil.example", "X-CSRF-Token": token, "Cookie": f"csrf_token={token}"},
        {"Origin": ORIGIN, "X-CSRF-Token": "a.b", "Cookie": "csrf_token=a.b"},
    ):
        response = http.post(LOGIN, json=BODY, headers=headers)
        assert response.status_code == 403
        bodies.add(response.text)
    assert bodies == {'{"detail":"Forbidden"}'}


def test_csrf_endpoint_reuses_a_valid_token_and_replaces_an_invalid_one(env: Env) -> None:
    client = env.client()
    first = client.csrf()
    assert client.csrf() == first
    client.http.cookies.set("csrf_token", "garbage", domain="testserver.local", path="/")
    assert client.http.get("/api/v1/auth/csrf").status_code == 204
    assert CsrfTokenSigner(derive_key(TEST_SECRET, LABEL_CSRF)).is_valid(
        client.cookie("csrf_token")
    )


def test_csrf_tokens_are_unique(env: Env) -> None:
    signer = CsrfTokenSigner(b"k" * 32)
    assert len({signer.issue() for _ in range(50)}) == 50


# ------------------------------------------------------------ allowed origins


def test_with_allowed_origins_only_listed_origins_pass(db_url: str) -> None:
    env = Env(db_url, ALLOWED_ORIGINS=["https://reader.example.com"])
    env.create_user()
    token = good_token()
    assert raw_post(env, cookie=token, header=token, origin="https://reader.example.com") == 200
    assert raw_post(env, cookie=token, header=token, origin="https://READER.example.com") == 200
    assert raw_post(env, cookie=token, header=token, origin="https://evil.example") == 403
    # In list mode the app's own Host is NOT implicitly trusted.
    assert raw_post(env, cookie=token, header=token, origin=ORIGIN) == 403
    assert raw_post(env, cookie=token, header=token, origin="http://reader.example.com") == 403
