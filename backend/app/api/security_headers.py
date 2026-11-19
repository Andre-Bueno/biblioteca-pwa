import json
import logging

from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

SECURITY_HEADERS: dict[bytes, bytes] = {
    b"content-security-policy": (
        b"default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
        b"object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
    b"x-content-type-options": b"nosniff",
    b"referrer-policy": b"no-referrer",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=(), payment=()",
}

_ERROR_BODY = json.dumps({"detail": "Internal Server Error"}).encode()


class SecurityHeadersMiddleware:
    """Pure ASGI middleware adding baseline security headers to every HTTP response.

    It also turns unhandled exceptions into a generic JSON 500 so that error
    responses carry the same headers (Starlette's outermost handler would not).

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

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in SECURITY_HEADERS
                ]
                headers.extend(SECURITY_HEADERS.items())
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
