import json
import logging
import re

from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.http_utils import is_api_path

logger = logging.getLogger(__name__)

SECURITY_HEADERS: dict[bytes, bytes] = {
    b"content-security-policy": (
        b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        b"connect-src 'self'; worker-src 'self'; manifest-src 'self'; font-src 'self'; "
        b"object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
    b"x-content-type-options": b"nosniff",
    b"referrer-policy": b"no-referrer",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=(), payment=()",
}

# Every /api response is user-specific or session-related: never stored by browsers or proxies.
NO_STORE_HEADERS: dict[bytes, bytes] = {b"cache-control": b"no-store", b"pragma": b"no-cache"}

# The ONLY /api responses allowed to be cached (by the user's own browser). Two independent
# conditions must both hold: the request path is on this fixed allowlist (page and cover of an
# item, cover of a series) AND the route marked its response with CACHE_MARKER_HEADER (an
# internal header that is always stripped before the response leaves). The middleware then writes
# the canonical value itself, so a route can never choose its own Cache-Control. Only 200/304
# answers to GET qualify; every error stays no-store.
CACHE_MARKER_HEADER = "x-internal-cache-class"
CACHE_MARKER_PRIVATE_IMAGE = "private-image"
PRIVATE_IMAGE_CACHE_CONTROL = b"private, max-age=3600"
_HEX = "[0-9a-fA-F]"
_UUID = rf"{_HEX}{{8}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{12}}"
_CACHEABLE_PATH = re.compile(
    rf"/api/v1/(?:items/{_UUID}/(?:pages/[0-9]{{1,9}}|cover)|series/{_UUID}/cover)"
)
_CACHEABLE_STATUSES = frozenset({200, 304})

_ERROR_BODY = json.dumps({"detail": "Internal Server Error"}).encode()


class SecurityHeadersMiddleware:
    """Pure ASGI middleware adding baseline security headers to every HTTP response.

    It also turns unhandled exceptions into a generic JSON 500 so that error
    responses carry the same headers (Starlette's outermost handler would not).

    Responses under /api also get Cache-Control: no-store and Pragma: no-cache, replacing
    whatever the route set. The single exception is the page/cover image routes (see
    CACHE_MARKER_HEADER): `Cache-Control: private, max-age=3600`, without Pragma.

    Design decision: these headers ALWAYS replace any header of the same name set by a
    route. In particular the strict CSP cannot be relaxed per route; revisit this when the
    EPUB/PDF reader needs a different policy (e.g. an opt-in per-route override).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False
        path = scope.get("path", "")
        is_api = is_api_path(path)
        base = SECURITY_HEADERS | NO_STORE_HEADERS if is_api else SECURITY_HEADERS
        may_cache = (
            is_api and scope.get("method") == "GET" and _CACHEABLE_PATH.fullmatch(path) is not None
        )
        marker_name = CACHE_MARKER_HEADER.encode()

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                marked = False
                kept: list[tuple[bytes, bytes]] = []
                for key, value in message.get("headers", []):
                    if key.lower() == marker_name:
                        marked = value == CACHE_MARKER_PRIVATE_IMAGE.encode()
                    else:
                        kept.append((key, value))
                final = dict(base)
                if may_cache and marked and message["status"] in _CACHEABLE_STATUSES:
                    del final[b"pragma"]
                    final[b"cache-control"] = PRIVATE_IMAGE_CACHE_CONTROL
                drop = set(final) | ({b"pragma"} if is_api else set())
                headers = [(k, v) for k, v in kept if k.lower() not in drop]
                headers.extend(final.items())
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception as exc:
            # BaseException (e.g. asyncio.CancelledError) is deliberately not caught.
            if started and isinstance(exc, ClientDisconnect | OSError):
                # Client went away mid-response: expected noise, not a server bug.
                logger.debug("Client disconnected after response started", exc_info=True)
                raise
            logger.exception("Unhandled error while serving request")
            if started:
                raise
            await send_with_headers(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(_ERROR_BODY)).encode()),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send_with_headers({"type": "http.response.body", "body": _ERROR_BODY})
