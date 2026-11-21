"""SafeGateway.get_json_conditional (release check): api.github.com only, ETag, 304, throttling,
redirects and look-alike hosts. No socket: fake connections."""

import pytest
from app.adapters.http.safe_gateway import ALLOWED_HOSTS, SafeGateway
from app.domain.errors import ExternalFetchError
from test_safe_gateway import FakeResponse, Rig, json_ok, reason_of

URL = "https://api.github.com/repos/Andre-Bueno/biblioteca-pwa/releases/latest"
GH_JSON = {"Content-Type": "application/json; charset=utf-8"}


def test_github_is_the_eighth_allowed_host_and_the_only_conditional_one() -> None:
    assert "api.github.com" in ALLOWED_HOSTS and len(ALLOWED_HOSTS) == 8
    assert SafeGateway.check_url(URL) == (
        "api.github.com",
        "/repos/Andre-Bueno/biblioteca-pwa/releases/latest",
    )
    rig = Rig(json_ok())
    assert (
        reason_of(lambda: rig.gateway.get_json_conditional("https://api.mangadex.org/x", None))
        == "host_not_allowed"
    )
    assert rig.hosts == []  # refused before any connection


@pytest.mark.parametrize(
    "url",
    [
        "https://api.github.com.evil.example/repos/a/b/releases/latest",
        "https://evil.example/api.github.com/repos/a/b/releases/latest",
        "https://apigithub.com/repos/a/b/releases/latest",
        "https://api-github.com/repos/a/b/releases/latest",
        "https://github.com/a/b/releases/latest",
        "https://raw.githubusercontent.com/a/b/main/x",
        "https://uploads.github.com/x",
        "https://xapi.github.com/x",
        "https://api.github.com@evil.example/x",
        "https://api.github.com:8443/x",
        "http://api.github.com/x",
        "https://127.0.0.1/x",
        "https://[::1]/x",
        "https://api.github.com\\@evil.example/x",
        "ftp://api.github.com/x",
    ],
)
def test_lookalike_and_unsafe_urls_never_open_a_connection(url: str) -> None:
    rig = Rig(json_ok())
    assert reason_of(lambda: rig.gateway.get_json_conditional(url, None)) in {
        "invalid_url",
        "host_not_allowed",
    }
    assert rig.hosts == [] and rig.requests == []


def test_request_headers_are_generic_and_carry_the_etag() -> None:
    rig = Rig(FakeResponse(200, GH_JSON | {"ETag": '"abc"'}, b'{"tag_name": "v1.0.0"}'))
    answer = rig.gateway.get_json_conditional(URL, '"prev"')
    assert (answer.status, answer.data, answer.etag) == (200, {"tag_name": "v1.0.0"}, '"abc"')
    sent = rig.requests[0]["headers"]
    assert sent["If-None-Match"] == '"prev"'  # type: ignore[index]
    assert sent["Accept"] == "application/vnd.github+json"  # type: ignore[index]
    assert sent["User-Agent"] == "BibliotecaPWA/1.0"  # type: ignore[index]
    assert sent["Accept-Encoding"] == "identity"  # type: ignore[index]
    assert "Authorization" not in sent and "Cookie" not in sent  # type: ignore[operator]
    assert rig.requests[0]["method"] == "GET" and rig.requests[0]["body"] is None


def test_no_etag_no_header_and_a_hostile_etag_is_not_sent() -> None:
    rig = Rig(json_ok(), json_ok(), json_ok())
    rig.gateway.get_json_conditional(URL, None)
    rig.gateway.get_json_conditional(URL, '"x"\r\nX-Evil: 1')
    rig.gateway.get_json_conditional(URL, "e" * 500)
    assert all("If-None-Match" not in r["headers"] for r in rig.requests)  # type: ignore[operator]


def test_304_is_returned_not_raised() -> None:
    rig = Rig(FakeResponse(304, {"ETag": '"abc"', "X-RateLimit-Remaining": "59"}))
    answer = rig.gateway.get_json_conditional(URL, '"abc"')
    assert (answer.status, answer.data, answer.etag, answer.remaining) == (304, None, '"abc"', 59)


@pytest.mark.parametrize("status", [403, 429])
def test_throttling_statuses_carry_the_rate_limit_headers(status: int) -> None:
    rig = Rig(
        FakeResponse(
            status,
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1800000000", "Retry-After": "30"},
        )
    )
    answer = rig.gateway.get_json_conditional(URL, None)
    assert (answer.status, answer.remaining, answer.reset_at, answer.retry_after) == (
        status,
        0,
        1_800_000_000,
        30.0,
    )
    assert answer.data is None


def test_a_429_also_paces_the_next_request() -> None:
    rig = Rig(FakeResponse(429, {"Retry-After": "5"}), json_ok())
    rig.gateway.get_json_conditional(URL, None)
    rig.gateway.get_json_conditional(URL, None)
    assert rig.sleeps and rig.sleeps[0] >= 5.0


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirects_are_never_followed(status: int) -> None:
    rig = Rig(FakeResponse(status, {"Location": "https://evil.example/x"}), json_ok())
    assert reason_of(lambda: rig.gateway.get_json_conditional(URL, None)) == "redirect"
    assert rig.hosts == ["api.github.com"]  # one connection, to the allowlisted host, no more


@pytest.mark.parametrize("status", [404, 410, 500, 502, 503])
def test_other_statuses_are_generic_errors(status: int) -> None:
    rig = Rig(FakeResponse(status))
    assert reason_of(lambda: rig.gateway.get_json_conditional(URL, None)) == "bad_status"


def test_content_type_encoding_and_size_are_checked() -> None:
    cases = [
        (FakeResponse(200, {"Content-Type": "text/html"}, b"{}"), "bad_content_type"),
        (FakeResponse(200, GH_JSON | {"Content-Encoding": "gzip"}, b"{}"), "bad_content_type"),
        (FakeResponse(200, GH_JSON | {"Content-Length": str(10**7)}, b"{}"), "too_large"),
        (FakeResponse(200, GH_JSON, endless=True), "too_large"),
        (FakeResponse(200, GH_JSON, b"not json"), "invalid_json"),
    ]
    for response, reason in cases:
        rig = Rig(response)
        assert reason_of(lambda rig=rig: rig.gateway.get_json_conditional(URL, None)) == reason


def test_network_errors_are_generic() -> None:
    for error, reason in ((OSError("x"), "network"), (TimeoutError(), "timeout")):
        rig = Rig(error)
        assert reason_of(lambda rig=rig: rig.gateway.get_json_conditional(URL, None)) == reason


def test_the_gateway_is_never_queued_on() -> None:
    rig = Rig(json_ok())
    gateway = rig.gateway
    assert gateway._lock.acquire(timeout=1)  # noqa: SLF001 - someone else is using the gateway
    try:
        gateway_lock_wait = 0.05
        import app.adapters.http.safe_gateway as module

        original = module.LOCK_WAIT
        module.LOCK_WAIT = gateway_lock_wait
        try:
            with pytest.raises(ExternalFetchError) as info:
                gateway.get_json_conditional(URL, None)
        finally:
            module.LOCK_WAIT = original
        assert info.value.reason == "busy" and rig.hosts == []
    finally:
        gateway._lock.release()  # noqa: SLF001


def test_exceptions_carry_only_a_reason_code() -> None:
    rig = Rig(FakeResponse(500))
    with pytest.raises(ExternalFetchError) as info:
        rig.gateway.get_json_conditional(URL, None)
    assert "github" not in str(info.value) and "http" not in str(info.value)
