"""Cookie attributes and Cache-Control on /api responses."""

from http.cookies import SimpleCookie

import pytest
from app.api.security_headers import SecurityHeadersMiddleware
from app.main import create_app
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import Response

from auth_fakes import PASSWORD, Env, make_settings


def cookies_of(response) -> dict[str, SimpleCookie]:  # type: ignore[no-untyped-def]
    parsed: dict[str, SimpleCookie] = {}
    for raw in response.headers.get_list("set-cookie"):
        jar: SimpleCookie = SimpleCookie()
        jar.load(raw)
        for name in jar:
            parsed[name] = jar
    return parsed


def morsel(response, name: str):  # type: ignore[no-untyped-def]
    return cookies_of(response)[name][name]


def test_session_cookies_have_the_required_attributes(env: Env) -> None:
    client = env.client()
    response = client.login()
    access, refresh = morsel(response, "access_token"), morsel(response, "refresh_token")
    for cookie in (access, refresh):
        assert cookie["httponly"] is True
        assert cookie["secure"] is True
        assert cookie["samesite"].lower() == "strict"
        assert not cookie["domain"]  # host-only
        assert cookie["max-age"]
    assert access["path"] == "/api"
    assert refresh["path"] == "/api/v1/auth"
    assert int(access["max-age"]) == env.settings.ACCESS_TOKEN_TTL_SECONDS
    assert int(refresh["max-age"]) == env.settings.REFRESH_TOKEN_TTL_SECONDS


def test_csrf_cookie_is_readable_by_js_but_secure_and_strict(env: Env) -> None:
    response = env.client().http.get("/api/v1/auth/csrf")
    cookie = morsel(response, "csrf_token")
    assert not cookie["httponly"]  # the frontend must read it
    assert cookie["secure"] is True
    assert cookie["samesite"].lower() == "strict"
    assert cookie["path"] == "/"
    assert not cookie["domain"]
    assert response.status_code == 204


def test_secure_flag_follows_the_setting(db_url: str) -> None:
    env = Env(db_url, COOKIE_SECURE=False)
    response = env.client().http.get("/api/v1/auth/csrf")
    assert not morsel(response, "csrf_token")["secure"]


def test_logout_expires_the_session_cookies_with_matching_attributes(env: Env) -> None:
    client = env.client()
    client.login()
    response = client.post("/api/v1/auth/logout")
    access, refresh = morsel(response, "access_token"), morsel(response, "refresh_token")
    assert access["path"] == "/api" and refresh["path"] == "/api/v1/auth"
    for cookie in (access, refresh):
        assert cookie.value == ""
        assert cookie["max-age"] == "0"
        assert cookie["httponly"] is True and cookie["secure"] is True


def test_refresh_sets_new_cookies_with_the_same_attributes(env: Env) -> None:
    client = env.client()
    client.login()
    response = client.post("/api/v1/auth/refresh")
    assert morsel(response, "refresh_token")["path"] == "/api/v1/auth"
    assert morsel(response, "refresh_token")["httponly"] is True
    assert morsel(response, "access_token")["path"] == "/api"


def test_refresh_cookie_is_not_sent_outside_its_path(env: Env) -> None:
    """Path scoping: the refresh token never travels to ordinary API routes."""

    @env.app.get("/api/v1/_echo")
    def echo(request: Request) -> dict[str, list[str]]:
        return {"cookies": sorted(request.cookies)}

    client = env.client()
    client.login()
    assert client.get("/api/v1/_echo").json() == {"cookies": ["access_token", "csrf_token"]}
    assert "refresh_token" in {c.name for c in client.http.cookies.jar}


@pytest.mark.parametrize(
    "path",
    ["/api/v1/health", "/api/v1/auth/me", "/api/v1/auth/csrf", "/api/v1/does-not-exist"],
)
def test_every_api_response_is_no_store(env: Env, path: str) -> None:
    response = env.client().http.get(path)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers.get_list("cache-control") == ["no-store"]


def test_error_and_limit_responses_are_no_store_too(env: Env) -> None:
    client = env.client()
    forbidden = client.http.post("/api/v1/auth/login", json={})
    assert forbidden.status_code == 403
    assert forbidden.headers["cache-control"] == "no-store"
    for _ in range(5):
        client.login("alice", "wrong password!!")
    locked = client.login()
    assert locked.status_code == 429
    assert locked.headers["cache-control"] == "no-store"
    assert client.post("/api/v1/auth/login", {"bad": 1}).headers["cache-control"] == "no-store"


def test_authenticated_responses_are_no_store(db_url: str) -> None:
    env = Env(db_url)
    env.create_user()
    client = env.client()
    login = client.login("alice", PASSWORD)
    assert login.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/auth/me").headers["cache-control"] == "no-store"


def test_route_cannot_loosen_cache_control_under_api() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/api/v1/cached")
    def cached() -> Response:
        return Response("x", headers={"Cache-Control": "public, max-age=3600", "Pragma": "x"})

    @app.get("/static-thing")
    def static_thing() -> Response:
        return Response("x", headers={"Cache-Control": "public, max-age=3600"})

    client = TestClient(app)
    api = client.get("/api/v1/cached")
    assert api.headers.get_list("cache-control") == ["no-store"]
    assert api.headers.get_list("pragma") == ["no-cache"]
    # Outside /api the route keeps control of caching (e.g. hashed static assets).
    assert client.get("/static-thing").headers["cache-control"] == "public, max-age=3600"


def test_default_app_object_is_wired(db_url: str) -> None:
    app = create_app(make_settings(db_url))
    assert TestClient(app).get("/api/v1/health").headers["cache-control"] == "no-store"
