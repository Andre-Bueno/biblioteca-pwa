from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.security_headers import SecurityHeadersMiddleware
from app.core.config import get_settings


def create_app() -> FastAPI:
    # Fails fast (ValidationError) when SECRET_KEY is missing or weak.
    settings = get_settings()
    app = FastAPI(title="Reader API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.add_middleware(SecurityHeadersMiddleware)
    app.include_router(health_router)
    return app


app = create_app()
