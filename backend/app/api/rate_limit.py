from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.http_utils import client_ip, is_api_path, send_json_error
from app.ports.rate_limiter import RateLimiter

# Only the endpoints that check or change credentials/sessions use the strict bucket. `me` and
# `csrf` are called by the SPA on every load and must stay under the global limit only.
STRICT_AUTH_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/change-password",
    }
)
RATE_LIMITED_DETAIL = "Too many requests. Try again later."


class RateLimitMiddleware:
    """Per-IP rate limit for every /api request, stricter for the credential endpoints.

    Those requests are counted against the auth limiter AND the global one. The 429 is the same
    generic response (plus Retry-After) used by the login lockout, so a client cannot tell which
    control fired. The IP is `request.client` (see `http_utils.client_ip`).
    """

    def __init__(
        self, app: ASGIApp, *, api_limiter: RateLimiter, auth_limiter: RateLimiter
    ) -> None:
        self.app = app
        self._api = api_limiter
        self._auth = auth_limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_api_path(scope["path"]):
            await self.app(scope, receive, send)
            return
        ip = client_ip(scope)
        limiters = [self._api]
        path = scope["path"]
        if path in STRICT_AUTH_PATHS:
            limiters.insert(0, self._auth)
        for limiter in limiters:
            decision = limiter.check(ip)
            if not decision.allowed:
                await send_json_error(
                    send,
                    429,
                    RATE_LIMITED_DETAIL,
                    [(b"retry-after", str(decision.retry_after_seconds).encode())],
                )
                return
        await self.app(scope, receive, send)
