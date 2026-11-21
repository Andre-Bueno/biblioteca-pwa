"""CSRF protection: signed double-submit cookie PLUS Origin/Referer/Fetch-Metadata checks.

How the frontend gets the token: `GET /api/v1/auth/csrf` sets the `csrf_token` cookie (readable by
JS, `Secure`, `SameSite=Strict`, Path=/); the frontend copies its value into the `X-CSRF-Token`
header of every POST/PUT/PATCH/DELETE (already done by `shared/api-client`). The first call must be
made before the first state-changing request, including login.

The cookie is "signed": token = base64url(nonce) "." base64url(HMAC-SHA256(csrf_subkey, nonce)).
A plain double-submit cookie can be planted by a sibling subdomain or a network attacker; with the
signature an attacker cannot mint a token the server accepts (only replay one it was issued, which
the Origin check below blocks). Comparison of cookie and header, and of the signature, are
constant-time.

Applies to EVERY non-safe method under /api, with no exception (login included).
Rejections are a generic 403 with no hint about which check failed (the reason goes to the log as
a short code, never with request values).
"""

import base64
import hashlib
import hmac
import logging
import secrets
from collections.abc import Collection
from urllib.parse import urlsplit

from starlette.requests import cookie_parser
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.http_utils import SAFE_METHODS, header, header_count, is_api_path, send_json_error

logger = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
MAX_TOKEN_LENGTH = 256
_NONCE_BYTES = 32
FORBIDDEN_DETAIL = "Forbidden"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class CsrfTokenSigner:
    def __init__(self, key: bytes) -> None:
        self._key = key

    def _sign(self, nonce: str) -> str:
        return _b64(hmac.new(self._key, nonce.encode(), hashlib.sha256).digest())

    def issue(self) -> str:
        nonce = _b64(secrets.token_bytes(_NONCE_BYTES))
        return f"{nonce}.{self._sign(nonce)}"

    def is_valid(self, token: str | None) -> bool:
        if not token or len(token) > MAX_TOKEN_LENGTH or token.count(".") != 1:
            return False
        nonce, signature = token.split(".")
        if not nonce or not signature:
            return False
        return hmac.compare_digest(signature.encode(), self._sign(nonce).encode())


def origin_of(url: str) -> str | None:
    """`scheme://host[:port]` of a URL (lowercase), or None if it is not a plain http(s) URL."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return None
        return f"{parts.scheme}://{parts.netloc}".lower()
    except ValueError:
        return None


class CsrfMiddleware:
    """Pure ASGI middleware. `allowed_origins` is the CORS list (exact origins). When it is empty
    the app runs in same-origin mode: the Origin/Referer host must equal the request `Host`
    (scheme is not compared: behind a TLS-terminating proxy the app may not see `https`, and the
    Secure cookie already keeps these requests off plain http)."""

    def __init__(
        self, app: ASGIApp, *, signer: CsrfTokenSigner, allowed_origins: Collection[str]
    ) -> None:
        self.app = app
        self._signer = signer
        self._allowed = frozenset(o.lower() for o in allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] in SAFE_METHODS
            or not is_api_path(scope["path"])
        ):
            await self.app(scope, receive, send)
            return
        reason = self._check(scope)
        if reason is not None:
            logger.warning("CSRF check rejected a request (%s)", reason)
            await send_json_error(send, 403, FORBIDDEN_DETAIL)
            return
        await self.app(scope, receive, send)

    def _origin_allowed(self, scope: Scope, origin: str) -> bool:
        if self._allowed:
            return origin in self._allowed
        host = header(scope, b"host")
        parts = urlsplit(origin)
        return host is not None and parts.netloc.lower() == host.strip().lower()

    def _check(self, scope: Scope) -> str | None:
        if header_count(scope, b"origin") > 1:
            # Browsers never repeat Origin; a proxy that adds one would make "first wins" a gap.
            return "origin-repeated"
        origin_header = header(scope, b"origin")
        if origin_header is not None:
            origin = origin_of(origin_header)
            if origin is None or not self._origin_allowed(scope, origin):
                return "origin"
        else:
            fetch_site = header(scope, b"sec-fetch-site")
            if fetch_site is not None:
                if fetch_site.strip().lower() not in ("same-origin", "none"):
                    return "fetch-site"
            else:
                referer = header(scope, b"referer")
                referer_origin = origin_of(referer) if referer else None
                if referer_origin is None or not self._origin_allowed(scope, referer_origin):
                    return "no-origin"

        token_header = header(scope, CSRF_HEADER_NAME.encode())
        cookie_header = header(scope, b"cookie")
        cookie = cookie_parser(cookie_header).get(CSRF_COOKIE_NAME) if cookie_header else None
        if not token_header or not cookie:
            return "missing-token"
        if len(token_header) > MAX_TOKEN_LENGTH or len(cookie) > MAX_TOKEN_LENGTH:
            return "bad-token"
        if not hmac.compare_digest(token_header.encode(), cookie.encode()):
            return "mismatch"
        if not self._signer.is_valid(token_header):
            return "bad-signature"
        return None
