"""Global rate limit middleware, client-IP normalisation, CORS and origin settings."""

import pytest
from app.api.http_utils import normalize_client_ip
from app.core.config import Settings
from fastapi.testclient import TestClient
from pydantic import ValidationError

from auth_fakes import TEST_SECRET, Env

# ------------------------------------------------------------------ rate limit


def test_api_is_rate_limited_per_ip_with_retry_after(db_url: str) -> None:
    env = Env(db_url, RATE_LIMIT_API_BURST=3, RATE_LIMIT_API_PER_MINUTE=60)
    http = TestClient(env.app, client=("5.5.5.5", 1))
    assert [http.get("/api/v1/health").status_code for _ in range(3)] == [200, 200, 200]
    blocked = http.get("/api/v1/health")
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.json() == {"detail": "Too many requests. Try again later."}
    assert blocked.headers["cache-control"] == "no-store"
    assert blocked.headers["x-content-type-options"] == "nosniff"  # security headers wrap it
    other = TestClient(env.app, client=("6.6.6.6", 1))
    assert other.get("/api/v1/health").status_code == 200


def test_auth_routes_have_a_stricter_limit(db_url: str) -> None:
    env = Env(db_url, RATE_LIMIT_AUTH_BURST=2, RATE_LIMIT_AUTH_PER_MINUTE=60)
    http = TestClient(env.app, client=("5.5.5.5", 1))
    # The rate limit runs before CSRF: the first two are refused by CSRF (403), the third is 429.
    codes = [http.post("/api/v1/auth/refresh").status_code for _ in range(3)]
    assert codes == [403, 403, 429]
    assert http.get("/api/v1/health").status_code == 200  # the rest of the API is unaffected


def test_rate_limit_429_is_byte_identical_to_the_login_lock_429(db_url: str) -> None:
    env = Env(
        db_url, RATE_LIMIT_AUTH_BURST=100, RATE_LIMIT_API_BURST=1, RATE_LIMIT_API_PER_MINUTE=1
    )
    env.create_user()
    limited = TestClient(env.app, client=("5.5.5.5", 1))
    limited.get("/api/v1/health")
    flood = limited.get("/api/v1/health")
    env2 = Env(db_url.replace("test.db", "test2.db"))
    env2.create_user()
    client = env2.client("5.5.5.6")
    for _ in range(5):
        client.login("alice", "wrong password!!")
    locked = client.login("alice", "wrong password!!")
    assert flood.status_code == locked.status_code == 429
    assert flood.content == locked.content
    assert flood.headers["content-type"] == locked.headers["content-type"]


def test_non_api_paths_are_not_rate_limited(db_url: str) -> None:
    env = Env(db_url, RATE_LIMIT_API_BURST=1, RATE_LIMIT_API_PER_MINUTE=1)
    http = TestClient(env.app, client=("5.5.5.5", 1))
    assert all(http.get("/elsewhere").status_code == 404 for _ in range(5))


def test_rate_limit_runs_before_csrf_so_floods_are_cheap(db_url: str) -> None:
    env = Env(db_url, RATE_LIMIT_AUTH_BURST=1, RATE_LIMIT_AUTH_PER_MINUTE=1)
    http = TestClient(env.app, client=("5.5.5.5", 1))
    assert http.post("/api/v1/auth/login", json={}).status_code == 403  # CSRF
    assert http.post("/api/v1/auth/login", json={}).status_code == 429  # limited first


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("203.0.113.7", "203.0.113.7"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:1111:2222:3333:4444", "2001:db8:1:2::/64"),
        ("fe80::1%eth0", "fe80::/64"),
        ("testclient", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_client_ip_normalisation(host: str | None, expected: str) -> None:
    assert normalize_client_ip(host) == expected


def test_ipv6_rotation_inside_a_64_does_not_escape_the_limit(db_url: str) -> None:
    env = Env(db_url, RATE_LIMIT_API_BURST=2, RATE_LIMIT_API_PER_MINUTE=1)
    statuses = [
        TestClient(env.app, client=(f"2001:db8:1:2::{i:x}", 1)).get("/api/v1/health").status_code
        for i in range(1, 5)
    ]
    assert statuses == [200, 200, 429, 429]


def test_forwarded_headers_are_ignored_by_the_app(db_url: str) -> None:
    """The app never reads X-Forwarded-For itself (uvicorn decides, via FORWARDED_ALLOW_IPS)."""
    env = Env(db_url, RATE_LIMIT_API_BURST=1, RATE_LIMIT_API_PER_MINUTE=1)
    http = TestClient(env.app, client=("5.5.5.5", 1))
    assert http.get("/api/v1/health", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    spoofed = http.get("/api/v1/health", headers={"X-Forwarded-For": "2.2.2.2"})
    assert spoofed.status_code == 429


# ------------------------------------------------------------------------ CORS

ALLOWED = "https://reader.example.com"


def cors_env(db_url: str) -> Env:
    return Env(db_url, ALLOWED_ORIGINS=[ALLOWED])


def test_no_cors_headers_when_no_origins_are_configured(env: Env) -> None:
    http = TestClient(env.app)
    response = http.options(
        "/api/v1/auth/login",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers
    assert (
        "access-control-allow-origin"
        not in http.get("/api/v1/health", headers={"Origin": ALLOWED}).headers
    )


def test_preflight_for_an_allowed_origin(db_url: str) -> None:
    http = TestClient(cors_env(db_url).app)
    response = http.options(
        "/api/v1/auth/login",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "x-csrf-token" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-allow-origin"] != "*"
    assert response.headers["cache-control"] == "no-store"


def test_preflight_for_a_foreign_origin_gets_no_allow_origin(db_url: str) -> None:
    http = TestClient(cors_env(db_url).app)
    response = http.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers
    assert response.status_code == 400


def test_actual_response_only_echoes_the_allowed_origin(db_url: str) -> None:
    http = TestClient(cors_env(db_url).app)
    good = http.get("/api/v1/health", headers={"Origin": ALLOWED})
    bad = http.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert good.headers["access-control-allow-origin"] == ALLOWED
    assert "access-control-allow-origin" not in bad.headers


def test_blocked_responses_still_carry_cors_so_the_browser_can_read_them(db_url: str) -> None:
    env = Env(
        db_url, ALLOWED_ORIGINS=[ALLOWED], RATE_LIMIT_API_BURST=1, RATE_LIMIT_API_PER_MINUTE=1
    )
    http = TestClient(env.app, client=("5.5.5.5", 1))
    http.get("/api/v1/health")
    limited = http.get("/api/v1/health", headers={"Origin": ALLOWED})
    assert limited.status_code == 429
    assert limited.headers["access-control-allow-origin"] == ALLOWED


# ---------------------------------------------------------------- settings


def settings(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **{"SECRET_KEY": TEST_SECRET}, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.com",
        "https://example.com/",
        "https://example.com/path",
        "https://example.com?x=1",
        "https://example.com#f",
        "example.com",
        "//example.com",
        "ftp://example.com",
        "javascript:alert(1)",
        "https://user:pw@example.com",
        "https://example.com:0",
        "https://example.com:notaport",
        "https://",
        "",
        "https://" + "a" * 300 + ".com",
    ],
)
def test_allowed_origins_must_be_exact_origins(origin: str) -> None:
    with pytest.raises(ValidationError):
        settings(ALLOWED_ORIGINS=[origin])


def test_valid_origins_are_accepted_and_lowercased() -> None:
    cfg = settings(
        ALLOWED_ORIGINS=[
            "https://Reader.Example.com",
            "http://localhost:5173",
            "https://[::1]:8443",
        ]
    )
    assert cfg.ALLOWED_ORIGINS == [
        "https://reader.example.com",
        "http://localhost:5173",
        "https://[::1]:8443",
    ]


def test_origin_errors_never_echo_the_value() -> None:
    with pytest.raises(ValidationError) as info:
        settings(ALLOWED_ORIGINS=["https://leaky-value.example/path"])
    assert "leaky-value" not in str(info.value)


def test_lockout_max_must_not_be_below_the_base() -> None:
    with pytest.raises(ValidationError):
        settings(LOGIN_LOCKOUT_SECONDS=600, LOGIN_LOCKOUT_MAX_SECONDS=300)


def test_absolute_session_ttl_must_cover_the_refresh_ttl() -> None:
    with pytest.raises(ValidationError):
        settings(REFRESH_TOKEN_TTL_SECONDS=1000, SESSION_ABSOLUTE_TTL_SECONDS=500)


def test_new_limits_have_sane_defaults() -> None:
    cfg = settings()
    assert cfg.RATE_LIMIT_AUTH_PER_MINUTE < cfg.RATE_LIMIT_API_PER_MINUTE
    assert cfg.RATE_LIMIT_AUTH_BURST < cfg.RATE_LIMIT_API_BURST
    assert cfg.LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS > cfg.LOGIN_MAX_FAILURES_ACCOUNT
    assert cfg.ACCESS_TOKEN_TTL_SECONDS <= 900
