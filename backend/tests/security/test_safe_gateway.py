"""SafeGateway: the only outbound HTTP. No test opens a socket: a fake connection answers, and the
factory records every attempt, so "refused" is proven by "the factory was never called"."""

import http.client
import socket
import threading
import time

import pytest
from app.adapters.http import safe_gateway
from app.adapters.http.safe_gateway import (
    ALLOWED_HOSTS,
    CHUNK,
    MAX_IMAGE_BYTES,
    MAX_JSON_BYTES,
    DisabledGateway,
    SafeGateway,
)
from app.domain.errors import ExternalFetchError

from metadata_fakes import good_jpeg, good_png, good_webp

OK_URL = "https://api.mangadex.org/manga?title=x"
IMG_URL = "https://uploads.mangadex.org/covers/a/b.jpg.512.jpg"
GRAPHQL = "https://graphql.anilist.co"


class FakeResponse:
    def __init__(
        self,
        status: int = 200,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        *,
        endless: bool = False,
        on_read: object = None,
    ) -> None:
        self.status = status
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body
        self._endless = endless
        self._pos = 0
        self._on_read = on_read
        self.served = 0

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self._headers.get(name.lower(), default)

    def read(self, amt: int) -> bytes:
        if self._on_read is not None:
            self._on_read()  # type: ignore[operator]
        if self._endless:
            self.served += amt
            return b"a" * amt
        chunk = self._body[self._pos : self._pos + amt]
        self._pos += len(chunk)
        self.served += len(chunk)
        return chunk


class FakeConnection:
    def __init__(self, response: FakeResponse | Exception, log: list[dict[str, object]]) -> None:
        self._response = response
        self._log = log
        self.closed = False

    def request(self, method: str, url: str, body: bytes | None, headers: dict[str, str]) -> None:
        self._log.append({"method": method, "target": url, "body": body, "headers": headers})

    def getresponse(self) -> FakeResponse:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    def close(self) -> None:
        self.closed = True


class Rig:
    """A gateway over fake connections, a fake clock and a sleep that only moves that clock."""

    def __init__(self, *responses: FakeResponse | Exception, total_timeout: float = 15.0) -> None:
        self.queue = list(responses)
        self.requests: list[dict[str, object]] = []
        self.hosts: list[str] = []
        self.conns: list[FakeConnection] = []
        self.now = 1000.0
        self.sleeps: list[float] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.gateway = SafeGateway(
            total_timeout=total_timeout,
            connection_factory=self._factory,
            clock=lambda: self.now,
            sleep=self._sleep,
        )

    def _sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def _factory(self, host: str, timeout: float) -> FakeConnection:
        assert timeout == safe_gateway.CONNECT_TIMEOUT
        self.hosts.append(host)
        item = self.queue.pop(0) if self.queue else FakeResponse(404)
        conn = FakeConnection(item, self.requests)
        self.conns.append(conn)
        return conn


def json_ok(body: bytes = b'{"ok": true}', **extra: str) -> FakeResponse:
    return FakeResponse(200, {"Content-Type": "application/json; charset=utf-8", **extra}, body)


def reason_of(call: object) -> str:
    with pytest.raises(ExternalFetchError) as info:
        call()  # type: ignore[operator]
    return info.value.reason


# ------------------------------------------------------------------ URL policy (SSRF)

REFUSED = [
    "http://api.mangadex.org/manga",  # not https
    "ftp://api.mangadex.org/manga",
    "file:///etc/passwd",
    "//api.mangadex.org/manga",
    "api.mangadex.org/manga",
    "https://127.0.0.1/",  # IP literals
    "https://169.254.169.254/latest/meta-data/",
    "https://10.0.0.5/",
    "https://[::1]/",
    "https://[::ffff:127.0.0.1]/",
    "https://2130706433/",  # decimal IP
    "https://0x7f000001/",
    "https://localhost/",
    "https://evil.example/",  # host outside the allowlist
    "https://api.mangadex.org.evil.example/",
    "https://evilapi.mangadex.org/",
    "https://sub.api.mangadex.org/",
    "https://mangadex.org/",  # the site itself is not on the list
    "https://anilist.co/",
    "https://s3.anilist.co/x.jpg",
    "https://en.wikipedia.org/api/rest_v1/page/summary/X",  # only the Portuguese Wikipedia
    "https://wikipedia.org/",
    "https://upload.wikimedia.org/x.png",
    "https://pt.wikipedia.org.evil.example/",
    "https://books.google.com/books?id=x",  # only the API host, not the book site
    "https://googleapis.com/books/v1/volumes",
    "https://storage.googleapis.com/x",
    "https://translated.net/",
    "https://mymemory.translated.net/",
    "https://api.mymemory.translated.net.evil.example/",
    "https://translate.google.com/",
    "https://api.mangadex.org@evil.example/",  # userinfo tricks
    "https://user:pw@api.mangadex.org/",
    "https://evil.example@api.mangadex.org/",
    "https://api.mangadex.org:8443/",  # port
    "https://api.mangadex.org:80/",
    "https://api.mangadex.org:0/",
    "https://api.mangadex.org:99999/",
    "https://api.mangadex.org./",  # trailing dot
    "https://api.mangadex.org\\@evil.example/",  # backslash
    "https://api.mangadex.org/ma nga",  # whitespace / control characters
    "https://api.mangadex.org/\r\nHost: evil.example",
    "https://api.mangadex.org/\x00",
    "https://api.mangadex.org/ä",  # non-ASCII
    "https://ａpi.mangadex.org/",
    "https:///manga",
    "https://",
    "",
    "https://api.mangadex.org/" + "a" * 3000,
]


@pytest.mark.parametrize("url", REFUSED)
def test_refused_urls_never_reach_the_network(url: str) -> None:
    rig = Rig(json_ok(), json_ok())
    for call in (
        lambda: rig.gateway.get_json(url),
        lambda: rig.gateway.get_image(url),
        lambda: rig.gateway.post_json(url, {"q": 1}),
    ):
        assert reason_of(call) in {"invalid_url", "host_not_allowed"}
    assert rig.hosts == [] and rig.requests == []


def test_the_allowlist_is_exactly_the_seven_known_hosts() -> None:
    assert {
        "api.mangadex.org",
        "uploads.mangadex.org",
        "graphql.anilist.co",
        "s4.anilist.co",
        "pt.wikipedia.org",
        "www.googleapis.com",
        "api.mymemory.translated.net",
    } == ALLOWED_HOSTS
    for host in sorted(ALLOWED_HOSTS):
        assert SafeGateway.check_url(f"https://{host}/p?q=1") == (host, "/p?q=1")
    assert SafeGateway.check_url("https://API.MangaDex.org:443") == ("api.mangadex.org", "/")
    assert SafeGateway.check_url("https://api.mangadex.org/p#frag") == ("api.mangadex.org", "/p")


def test_post_only_goes_to_the_graphql_host() -> None:
    rig = Rig(json_ok(), json_ok())
    assert reason_of(lambda: rig.gateway.post_json(OK_URL, {"a": 1})) == "host_not_allowed"
    assert rig.hosts == []
    assert rig.gateway.post_json(GRAPHQL, {"a": 1}) == {"ok": True}
    sent = rig.requests[0]
    assert sent["method"] == "POST" and sent["body"] == b'{"a":1}'
    assert sent["headers"]["Content-Type"] == "application/json"  # type: ignore[index]


def test_a_huge_post_body_is_refused_before_any_connection() -> None:
    rig = Rig(json_ok())
    assert reason_of(lambda: rig.gateway.post_json(GRAPHQL, {"q": "x" * 20_000})) == "invalid_url"
    assert rig.hosts == []


def test_request_has_no_cookies_credentials_or_personal_data() -> None:
    rig = Rig(json_ok())
    rig.gateway.get_json(OK_URL)
    headers = rig.requests[0]["headers"]
    assert isinstance(headers, dict)
    assert headers["User-Agent"] == "BibliotecaPWA/1.0"
    assert headers["Accept-Encoding"] == "identity"
    lowered = {k.lower() for k in headers}
    assert lowered == {"user-agent", "accept", "accept-encoding", "connection"}
    assert rig.requests[0]["target"] == "/manga?title=x"  # origin-form: no absolute URL, no host
    assert rig.conns[0].closed


# ------------------------------------------------------------------ redirects


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirects_are_never_followed(status: int) -> None:
    rig = Rig(FakeResponse(status, {"Location": "https://evil.example/x"}), json_ok())
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "redirect"
    assert rig.hosts == ["api.mangadex.org"]  # one connection only: the Location was not used


def test_a_redirect_to_a_host_off_the_list_is_a_generic_error_for_images_too() -> None:
    rig = Rig(FakeResponse(302, {"Location": "http://169.254.169.254/"}))
    assert reason_of(lambda: rig.gateway.get_image(IMG_URL)) == "redirect"
    assert len(rig.requests) == 1


# ------------------------------------------------------------------ size limits


def test_oversized_json_is_refused_from_the_declared_length() -> None:
    big = FakeResponse(
        200, {"Content-Type": "application/json", "Content-Length": str(MAX_JSON_BYTES + 1)}
    )
    rig = Rig(big)
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "too_large"
    assert big.served == 0  # not even started reading


def test_endless_body_is_cut_at_the_limit_without_reading_further() -> None:
    endless = FakeResponse(200, {"Content-Type": "application/json"}, endless=True)
    rig = Rig(endless)
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "too_large"
    assert endless.served == MAX_JSON_BYTES + 1  # one byte past the limit, then stop


def test_a_lying_content_length_does_not_bypass_the_streaming_cut() -> None:
    liar = FakeResponse(
        200, {"Content-Type": "application/json", "Content-Length": "10"}, endless=True
    )
    rig = Rig(liar)
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "too_large"
    assert liar.served == MAX_JSON_BYTES + 1


def test_image_limit_is_5_mib_and_json_limit_is_1_mib() -> None:
    assert MAX_IMAGE_BYTES == 5 * 1024 * 1024 and MAX_JSON_BYTES == 1024 * 1024
    endless = FakeResponse(200, {"Content-Type": "image/jpeg"}, endless=True)
    rig = Rig(endless)
    assert reason_of(lambda: rig.gateway.get_image(IMG_URL)) == "too_large"
    assert endless.served == MAX_IMAGE_BYTES + 1


def test_a_body_exactly_at_the_limit_is_accepted() -> None:
    body = b'"' + b"a" * (MAX_JSON_BYTES - 2) + b'"'
    rig = Rig(json_ok(body))
    assert len(rig.gateway.get_json(OK_URL)) == MAX_JSON_BYTES - 2  # type: ignore[arg-type]


# ------------------------------------------------------------------ content type and JSON


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "text/html"},
        {"Content-Type": "image/jpeg"},
        {"Content-Type": "application/octet-stream"},
        {"Content-Type": "application/json-evil"},
        {},
        {"Content-Type": "application/json", "Content-Encoding": "gzip"},
    ],
)
def test_json_needs_the_json_content_type_and_no_content_encoding(headers: dict[str, str]) -> None:
    rig = Rig(FakeResponse(200, headers, b"{}"))
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "bad_content_type"


@pytest.mark.parametrize("ctype", ["text/html", "image/svg+xml", "image/gif", "application/json"])
def test_image_needs_a_jpeg_png_or_webp_content_type(ctype: str) -> None:
    rig = Rig(FakeResponse(200, {"Content-Type": ctype}, good_jpeg()))
    assert reason_of(lambda: rig.gateway.get_image(IMG_URL)) == "bad_content_type"


@pytest.mark.parametrize(
    "body",
    [
        b'{"a": ',  # truncated
        b"not json at all",
        b"\xff\xfe\x00bad utf8",
        b"[" * 200_000,  # absurd nesting: RecursionError, not a crash
        b'{"a":' * 100_000 + b"1" + b"}" * 100_000,
        b"1" * 10_000,  # integer too long to parse
        b"",
    ],
)
def test_malformed_or_hostile_json_is_a_generic_error(body: bytes) -> None:
    rig = Rig(json_ok(body))
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "invalid_json"


# ------------------------------------------------------------------ images


@pytest.mark.parametrize(
    ("data", "ctype", "expected"),
    [
        (good_jpeg(), "image/jpeg", "image/jpeg"),
        (good_png(), "image/png", "image/png"),
        (good_webp(), "image/webp", "image/webp"),
    ],
)
def test_good_images_are_accepted_and_typed_by_their_bytes(
    data: bytes, ctype: str, expected: str
) -> None:
    rig = Rig(FakeResponse(200, {"Content-Type": ctype}, data))
    image = rig.gateway.get_image(IMG_URL)
    assert image.data == data and image.media_type == expected


@pytest.mark.parametrize(
    ("data", "ctype"),
    [
        (b"<html><script>alert(1)</script></html>", "image/jpeg"),  # not an image at all
        (good_jpeg() + b"<script>alert(1)</script>", "image/jpeg"),  # polyglot tail
        (b"\xff\xd8\xff\xe0<?php system($_GET[0]); ?>", "image/jpeg"),
        (b"GIF89a;<script>", "image/png"),
        (good_jpeg(), "image/png"),  # header lies about the real type
        (good_png(), "image/webp"),
        (b"", "image/png"),
    ],
)
def test_images_that_are_not_what_they_claim_are_refused(data: bytes, ctype: str) -> None:
    rig = Rig(FakeResponse(200, {"Content-Type": ctype}, data))
    assert reason_of(lambda: rig.gateway.get_image(IMG_URL)) == "invalid_image"


def test_the_extension_in_the_url_is_never_trusted() -> None:
    rig = Rig(FakeResponse(200, {"Content-Type": "image/png"}, good_png()))
    image = rig.gateway.get_image("https://uploads.mangadex.org/covers/a/evil.exe.jpg")
    assert image.ext == "png"


# ------------------------------------------------------------------ errors, rate limits, time


@pytest.mark.parametrize("status", [400, 401, 403, 404, 418, 500, 502, 503])
def test_other_statuses_are_a_generic_error(status: int) -> None:
    rig = Rig(FakeResponse(status, {"Content-Type": "application/json"}, b"{}"))
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "bad_status"


@pytest.mark.parametrize(
    "failure",
    [
        OSError("connection refused to api.mangadex.org"),
        ConnectionResetError("reset"),
        http.client.BadStatusLine("garbage"),
        http.client.IncompleteRead(b"x"),
        ValueError("bad"),
    ],
)
def test_network_failures_are_generic_and_carry_no_detail(failure: Exception) -> None:
    rig = Rig(failure)
    with pytest.raises(ExternalFetchError) as info:
        rig.gateway.get_json(OK_URL)
    assert info.value.reason == "network"
    assert "mangadex" not in str(info.value) and info.value.__cause__ is None
    assert rig.conns[0].closed


def test_a_timeout_is_reported_as_such() -> None:
    rig = Rig(TimeoutError("timed out"))
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "timeout"


def test_the_whole_request_has_a_deadline_even_for_a_slow_drip() -> None:
    rig = Rig()
    slow = FakeResponse(
        200,
        {"Content-Type": "application/json"},
        endless=True,
        on_read=lambda: setattr(rig, "now", rig.now + 6.0),
    )
    rig.queue.append(slow)
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "timeout"
    assert slow.served <= 3 * CHUNK  # stopped after a few chunks, not at the size limit


def test_429_sets_a_cooldown_that_is_respected_with_retry_after() -> None:
    rig = Rig(
        FakeResponse(429, {"Retry-After": "3"}),
        json_ok(),
    )
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "rate_limited"
    assert rig.gateway.get_json(OK_URL) == {"ok": True}
    assert rig.sleeps and rig.sleeps[0] >= 3.0  # waited the Retry-After before the next try


def test_a_long_retry_after_fails_fast_instead_of_blocking_a_thread() -> None:
    rig = Rig(FakeResponse(429, {"Retry-After": "86400"}), json_ok())
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "rate_limited"
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "rate_limited"
    assert len(rig.hosts) == 1 and rig.sleeps == []  # the second call never connected nor slept


def test_a_garbage_retry_after_falls_back_to_backoff() -> None:
    rig = Rig(FakeResponse(429, {"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}), json_ok())
    assert reason_of(lambda: rig.gateway.get_json(OK_URL)) == "rate_limited"
    assert rig.gateway.get_json(OK_URL) == {"ok": True}
    assert 0 < rig.sleeps[0] <= safe_gateway.MAX_WAIT


def test_failures_back_off_exponentially_and_success_resets() -> None:
    rig = Rig(FakeResponse(503), FakeResponse(503), json_ok(), json_ok())
    reason_of(lambda: rig.gateway.get_json(OK_URL))
    reason_of(lambda: rig.gateway.get_json(OK_URL))
    assert rig.sleeps[0] >= 2.0
    rig.gateway.get_json(OK_URL)
    assert rig.sleeps[1] >= 4.0  # the second failure waited longer
    before = len(rig.sleeps)
    rig.gateway.get_json(OK_URL)
    assert rig.sleeps[before:] == [safe_gateway.MIN_INTERVAL]  # reset: only the 2 req/s pacing


def test_requests_to_one_host_are_paced_to_two_per_second() -> None:
    rig = Rig(json_ok(), json_ok(), json_ok())
    for _ in range(3):
        rig.gateway.get_json(OK_URL)
    assert rig.sleeps == [safe_gateway.MIN_INTERVAL, safe_gateway.MIN_INTERVAL]


def test_other_hosts_are_paced_independently() -> None:
    rig = Rig(json_ok(), FakeResponse(200, {"Content-Type": "image/png"}, good_png()))
    rig.gateway.get_json(OK_URL)
    rig.gateway.get_image("https://uploads.mangadex.org/covers/a/b.png")
    assert rig.sleeps == []


def test_only_one_request_runs_at_a_time() -> None:
    state = {"now": 0, "max": 0}
    lock = threading.Lock()

    def slow_read() -> None:
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.01)
        with lock:
            state["now"] -= 1

    responses = [
        FakeResponse(200, {"Content-Type": "application/json"}, b"{}", on_read=slow_read)
        for _ in range(6)
    ]
    gateway = SafeGateway(
        connection_factory=lambda host, timeout: FakeConnection(responses.pop(0), []),
        sleep=lambda _s: None,
    )
    threads = [threading.Thread(target=gateway.get_json, args=(OK_URL,)) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert state["max"] == 1 and responses == []


# ------------------------------------------------------------------ real connection class


def test_connection_refuses_a_name_that_resolves_to_a_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[object] = []
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: opened.append(a))
    for address, family in (
        ("10.1.2.3", socket.AF_INET),
        ("127.0.0.1", socket.AF_INET),
        ("169.254.169.254", socket.AF_INET),
        ("192.168.0.9", socket.AF_INET),
        ("::1", socket.AF_INET6),
        ("fd00::1", socket.AF_INET6),
    ):
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, _ad=address, _fa=family, **k: [(_fa, socket.SOCK_STREAM, 6, "", (_ad, 443))],
        )
        conn = safe_gateway._PinnedHTTPSConnection("api.mangadex.org", 5.0)
        with pytest.raises(ExternalFetchError) as info:
            conn.connect()
        assert info.value.reason == "host_not_allowed"
    assert opened == []  # no socket was ever created


def test_connection_goes_to_the_checked_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ],
    )
    assert safe_gateway._public_address("api.mangadex.org") == "93.184.216.34"


def test_dns_failure_is_a_generic_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    assert reason_of(lambda: safe_gateway._public_address("api.mangadex.org")) == "network"


def test_the_disabled_gateway_refuses_everything_without_a_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_a: object, **_k: object) -> None:
        raise AssertionError("a socket was touched")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    gateway = DisabledGateway()
    assert reason_of(lambda: gateway.get_json(OK_URL)) == "disabled"
    assert reason_of(lambda: gateway.post_json(GRAPHQL, {})) == "disabled"
    assert reason_of(lambda: gateway.get_image(IMG_URL)) == "disabled"
