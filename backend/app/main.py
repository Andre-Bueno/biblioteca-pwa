import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.body_limit import BodySizeLimitMiddleware
from app.api.books import router as books_router
from app.api.csrf import CsrfMiddleware, CsrfTokenSigner
from app.api.errors import validation_error_handler
from app.api.health import router as health_router
from app.api.items import router as items_router
from app.api.library import router as library_router
from app.api.preferences import router as preferences_router
from app.api.progress import router as progress_router
from app.api.rate_limit import RateLimitMiddleware
from app.api.security_headers import SecurityHeadersMiddleware
from app.api.series import router as series_router
from app.api.spa import install_spa
from app.api.system import router as system_router
from app.composition import Container, build_rate_limiters
from app.core.config import Settings, get_settings
from app.core.keys import LABEL_CSRF, derive_key

logger = logging.getLogger(__name__)

PROXY_TRUST_WARNING = (
    "FORWARDED_ALLOW_IPS is empty or '*': the client IP seen by the app may be wrong (every client "
    "looks like the proxy, so one client can lock logins for all) or forgeable. Set it to the "
    "IP/CIDR of the reverse proxy that connects to this container; '*' only if the port is not "
    "reachable directly."
)


def create_app(settings: Settings | None = None, *, container: Container | None = None) -> FastAPI:
    # Fails fast (ValidationError) when SECRET_KEY is missing or weak.
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if cfg.FORWARDED_ALLOW_IPS.strip() in ("", "*"):
            logger.warning(PROXY_TRUST_WARNING)
        yield

    # redirect_slashes=False: the API is consumed by exact URLs; the automatic redirect built its
    # Location from the request Host header (FIND-2026-008).
    app = FastAPI(
        title="Reader API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        lifespan=lifespan,
    )
    app.state.settings = cfg
    app.state.container = container or Container(cfg)  # lazy: nothing is opened until used
    signer = CsrfTokenSigner(derive_key(cfg.SECRET_KEY, LABEL_CSRF))
    app.state.csrf_signer = signer
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(items_router)
    app.include_router(books_router)
    app.include_router(series_router)
    app.include_router(library_router)
    app.include_router(progress_router)
    app.include_router(preferences_router)
    app.include_router(system_router)

    # Middleware order: the LAST one added is the outermost. Request path:
    # SecurityHeaders -> CORS -> RateLimit -> BodyLimit -> CSRF -> routes. Security headers wrap
    # everything (including 403/413/429 and 500), CORS answers preflight and decorates 403/413/429
    # so the browser can read them, and the cheap rate limit runs before the body and CSRF checks.
    api_limiter, auth_limiter = build_rate_limiters(cfg)
    app.add_middleware(CsrfMiddleware, signer=signer, allowed_origins=cfg.ALLOWED_ORIGINS)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=cfg.MAX_BODY_BYTES)
    app.add_middleware(RateLimitMiddleware, api_limiter=api_limiter, auth_limiter=auth_limiter)
    if cfg.ALLOWED_ORIGINS:
        # Explicit origins only (Settings rejects "*"): credentials are always on.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.ALLOWED_ORIGINS,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "Accept", "X-CSRF-Token"],
            max_age=600,
        )
    app.add_middleware(SecurityHeadersMiddleware)
    if cfg.FRONTEND_DIST_DIR is not None:
        install_spa(app, cfg.FRONTEND_DIST_DIR)  # fallback for non-/api paths; keep after routers
    return app


app = create_app()
