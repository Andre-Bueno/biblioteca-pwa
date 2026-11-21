"""SafeGateway: the ONLY outbound HTTP of the app (public metadata sources).

Hard rules, none of them configurable at run time:
- https only, to a FIXED allowlist of hosts, port 443, no userinfo, no IP literals;
- the address the name resolves to must be public (a poisoned DNS cannot reach the LAN), and the
  connection goes to that checked address (no second lookup);
- redirects are never followed (a 3xx is an error), so a response cannot send us elsewhere;
- no cookies, no credentials, a generic User-Agent, `Accept-Encoding: identity`;
- connect timeout 5 s, whole request 15 s, body read in chunks and cut at the size limit
  (JSON 1 MiB, image 5 MiB);
- content type checked; images also by magic bytes and shape (never by name or URL);
- one request at a time, at most 2 per second per host, `Retry-After` and backoff respected.

Every failure is an `ExternalFetchError` carrying a fixed reason code; a message with a URL, host or
body never leaves this module.
"""

import contextlib
import http.client
import ipaddress
import json
import socket
import ssl
import threading
import time
from collections.abc import Callable
from typing import Protocol
from urllib.parse import urlsplit

from app.domain.errors import ExternalFetchError
from app.domain.metadata import FetchedImage, sniff_image

ALLOWED_HOSTS = frozenset(
    {
        "api.mangadex.org",
        "uploads.mangadex.org",
        "graphql.anilist.co",
        "s4.anilist.co",
        "pt.wikipedia.org",
        "www.googleapis.com",
        "api.mymemory.translated.net",
    }
)
POST_HOSTS = frozenset({"graphql.anilist.co"})  # GraphQL is POST-only; nothing else takes a body
USER_AGENT = "BibliotecaPWA/1.0"
CONNECT_TIMEOUT = 5.0
TOTAL_TIMEOUT = 15.0
MAX_JSON_BYTES = 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_POST_BYTES = 16 * 1024
MAX_URL_LENGTH = 2048
MIN_INTERVAL = 0.5  # at most 2 requests per second per host
MAX_WAIT = 10.0  # longer waits (a long Retry-After) fail the request instead of blocking a thread
MAX_BACKOFF = 60.0
CHUNK = 64 * 1024
_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


class _Response(Protocol):
    status: int

    def getheader(self, name: str, default: str | None = None) -> str | None: ...

    def read(self, amt: int) -> bytes: ...


class _Connection(Protocol):
    def request(
        self, method: str, url: str, body: bytes | None, headers: dict[str, str]
    ) -> None: ...

    def getresponse(self) -> _Response: ...

    def close(self) -> None: ...


ConnectionFactory = Callable[[str, float], _Connection]


def _public_address(host: str) -> str:
    """First address `host` resolves to that is globally routable, else an error."""
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ExternalFetchError("network") from None
    for info in infos:
        address = str(info[4][0])
        try:
            if ipaddress.ip_address(address).is_global:
                return address
        except ValueError:
            continue
    raise ExternalFetchError("host_not_allowed")


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that connects to the address it has just checked, with TLS verification
    (certificate and host name) against the allowlisted name."""

    def __init__(self, host: str, timeout: float) -> None:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(host, 443, timeout=timeout, context=context)
        self._tls_context = context

    def connect(self) -> None:
        address = _public_address(self.host)
        sock = socket.create_connection((address, 443), timeout=CONNECT_TIMEOUT)
        sock.settimeout(self.timeout)
        self.sock = self._tls_context.wrap_socket(sock, server_hostname=self.host)


def _open_connection(host: str, timeout: float) -> _Connection:
    return _PinnedHTTPSConnection(host, timeout)  # type: ignore[return-value]


def _media_type(header: str | None) -> str:
    return (header or "").split(";", 1)[0].strip().lower()


def _retry_after(header: str | None) -> float | None:
    if header is None or not header.strip().isascii() or not header.strip().isdigit():
        return None  # HTTP-date form is ignored: the plain backoff applies
    return min(float(header.strip()), MAX_BACKOFF)


class SafeGateway:
    """See the module docstring. `connection_factory`, `clock` and `sleep` are injected by tests
    (no real socket); the allowlist is deliberately not injectable."""

    def __init__(
        self,
        *,
        total_timeout: float = TOTAL_TIMEOUT,
        connection_factory: ConnectionFactory | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._total_timeout = total_timeout
        self._factory = connection_factory or _open_connection
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()  # concurrency 1: one request at a time, whole process
        self._next_ok: dict[str, float] = {}
        self._blocked_until: dict[str, float] = {}
        self._failures: dict[str, int] = {}

    # -- public API ------------------------------------------------------

    def get_json(self, url: str) -> object:
        data, _ = self._fetch("GET", url, None, MAX_JSON_BYTES, frozenset({"application/json"}))
        return self._parse(data)

    def post_json(self, url: str, payload: dict[str, object]) -> object:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        if len(body) > MAX_POST_BYTES:
            raise ExternalFetchError("invalid_url")
        data, _ = self._fetch("POST", url, body, MAX_JSON_BYTES, frozenset({"application/json"}))
        return self._parse(data)

    def get_image(self, url: str) -> FetchedImage:
        data, declared = self._fetch("GET", url, None, MAX_IMAGE_BYTES, _IMAGE_TYPES)
        sniffed = sniff_image(data)
        if sniffed is None or sniffed[0] != declared:
            raise ExternalFetchError("invalid_image")
        return FetchedImage(data=data, media_type=sniffed[0], ext=sniffed[1])

    # -- internals -------------------------------------------------------

    @staticmethod
    def _parse(data: bytes) -> object:
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise ExternalFetchError("invalid_json") from None

    @staticmethod
    def check_url(url: str) -> tuple[str, str]:
        """(host, request target) of an acceptable URL; raises otherwise. Public for tests."""
        if len(url) > MAX_URL_LENGTH or any(not 32 < ord(ch) < 127 for ch in url) or "\\" in url:
            raise ExternalFetchError("invalid_url")
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            raise ExternalFetchError("invalid_url") from None
        if parts.scheme != "https" or "@" in parts.netloc or port not in (None, 443):
            raise ExternalFetchError("invalid_url")
        host = (parts.hostname or "").lower()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ExternalFetchError("invalid_url")  # IP literal
        if host not in ALLOWED_HOSTS:
            raise ExternalFetchError("host_not_allowed")
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        return host, target

    def _pace(self, host: str) -> None:
        now = self._clock()
        ready = max(self._next_ok.get(host, 0.0), self._blocked_until.get(host, 0.0))
        wait = ready - now
        if wait > MAX_WAIT:
            raise ExternalFetchError("rate_limited")
        if wait > 0:
            self._sleep(wait)
        self._next_ok[host] = max(now, ready) + MIN_INTERVAL

    def _penalize(self, host: str, retry_after: float | None) -> None:
        count = self._failures.get(host, 0) + 1
        self._failures[host] = count
        delay = min(MAX_BACKOFF, max(retry_after or 0.0, float(2 ** min(count, 6))))
        self._blocked_until[host] = self._clock() + delay

    def _fetch(
        self,
        method: str,
        url: str,
        body: bytes | None,
        max_bytes: int,
        allowed_types: frozenset[str],
    ) -> tuple[bytes, str]:
        host, target = self.check_url(url)
        if method == "POST" and host not in POST_HOSTS:
            raise ExternalFetchError("host_not_allowed")
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": ", ".join(sorted(allowed_types)),
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        with self._lock:
            self._pace(host)
            deadline = self._clock() + self._total_timeout
            conn: _Connection | None = None
            try:
                conn = self._factory(host, CONNECT_TIMEOUT)
                conn.request(method, target, body, headers)
                response = conn.getresponse()
                result = self._read(host, response, max_bytes, allowed_types, deadline)
            except ExternalFetchError:
                raise
            except TimeoutError:
                self._penalize(host, None)
                raise ExternalFetchError("timeout") from None
            except (OSError, http.client.HTTPException, ssl.SSLError, ValueError):
                self._penalize(host, None)
                raise ExternalFetchError("network") from None
            finally:
                if conn is not None:
                    with contextlib.suppress(OSError):
                        conn.close()
            self._failures.pop(host, None)
            return result

    def _read(
        self,
        host: str,
        response: _Response,
        max_bytes: int,
        allowed_types: frozenset[str],
        deadline: float,
    ) -> tuple[bytes, str]:
        status = response.status
        if status == 429:
            self._penalize(host, _retry_after(response.getheader("Retry-After")))
            raise ExternalFetchError("rate_limited")
        if 300 <= status < 400:
            raise ExternalFetchError("redirect")  # never followed
        if status >= 500:
            self._penalize(host, _retry_after(response.getheader("Retry-After")))
            raise ExternalFetchError("bad_status")
        if status != 200:
            raise ExternalFetchError("bad_status")
        declared = _media_type(response.getheader("Content-Type"))
        encoding = (response.getheader("Content-Encoding") or "identity").strip().lower()
        if declared not in allowed_types or encoding != "identity":
            raise ExternalFetchError("bad_content_type")
        length = response.getheader("Content-Length")
        if length is not None and length.strip().isdigit() and int(length.strip()) > max_bytes:
            raise ExternalFetchError("too_large")
        chunks: list[bytes] = []
        total = 0
        while True:
            if self._clock() > deadline:
                raise ExternalFetchError("timeout")
            chunk = response.read(min(CHUNK, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ExternalFetchError("too_large")  # cut: the rest is never read
            chunks.append(chunk)
        return b"".join(chunks), declared


class DisabledGateway:
    """Used when `METADATA_ENABLED=false`: refuses everything, opens no socket."""

    def get_json(self, url: str) -> object:
        raise ExternalFetchError("disabled")

    def post_json(self, url: str, payload: dict[str, object]) -> object:
        raise ExternalFetchError("disabled")

    def get_image(self, url: str) -> FetchedImage:
        raise ExternalFetchError("disabled")
