"""Composition point for the API: the only `app.api` module allowed to touch adapters.

Services are built once per app (lazily) by `app.composition.Container`, which `create_app` puts
in `app.state.container`; tests can therefore build an app with a temporary database, a fast hasher
and a fake clock without monkeypatching.

`get_current_user` / `require_admin` are the reusable guards for every authenticated route.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.api.csrf import CsrfTokenSigner
from app.api.errors import library_error
from app.composition import Container
from app.core.config import Settings
from app.domain.auth import NotAuthenticatedError
from app.domain.errors import LibraryUnavailable
from app.domain.user import Role, User
from app.ports.cover_store import CoverStore
from app.ports.extractor import Extractor
from app.ports.item_repository import ItemRepository
from app.ports.rate_limiter import RateLimiter
from app.ports.series_repository import SeriesRepository
from app.services.auth_service import AuthService
from app.services.enrich_runner import EnrichRunner
from app.services.metadata_service import MetadataService
from app.services.preferences_service import PreferencesService
from app.services.progress_service import ProgressService
from app.services.scan_runner import ScanRunner
from app.services.series_service import SeriesService
from app.services.user_service import UserService

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_csrf_signer(request: Request) -> CsrfTokenSigner:
    signer: CsrfTokenSigner = request.app.state.csrf_signer
    return signer


def get_user_service(container: Annotated[Container, Depends(get_container)]) -> UserService:
    return container.user_service


def get_auth_service(container: Annotated[Container, Depends(get_container)]) -> AuthService:
    return container.auth_service


def get_current_user(
    request: Request, auth: Annotated[AuthService, Depends(get_auth_service)]
) -> User:
    """The authenticated, active user for this request (401 otherwise)."""
    try:
        return auth.current_user(request.cookies.get(ACCESS_COOKIE))
    except NotAuthenticatedError:
        raise HTTPException(status_code=401, detail="Not authenticated") from None


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role is not Role.ADMIN:
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


def get_item_repository(
    container: Annotated[Container, Depends(get_container)],
) -> ItemRepository:
    return container.item_repository


def get_series_repository(
    container: Annotated[Container, Depends(get_container)],
) -> SeriesRepository:
    return container.series_repository


def get_series_service(
    container: Annotated[Container, Depends(get_container)],
) -> SeriesService:
    return container.series_service


def get_metadata_service(
    container: Annotated[Container, Depends(get_container)],
) -> MetadataService:
    return container.metadata_service


def get_cover_store(container: Annotated[Container, Depends(get_container)]) -> CoverStore:
    return container.cover_store


def get_candidates_limiter(container: Annotated[Container, Depends(get_container)]) -> RateLimiter:
    return container.candidates_limiter


def get_enrich_runner(container: Annotated[Container, Depends(get_container)]) -> EnrichRunner:
    return container.enrich_runner


def get_extractors(container: Annotated[Container, Depends(get_container)]) -> Sequence[Extractor]:
    """Format readers. The library folder is resolved here, so a missing folder is a generic 503
    when a page is requested, never an error at import or start-up."""
    try:
        return container.extractors
    except LibraryUnavailable as exc:
        raise library_error(exc) from None


def get_progress_service(
    container: Annotated[Container, Depends(get_container)],
) -> ProgressService:
    return container.progress_service


def get_preferences_service(
    container: Annotated[Container, Depends(get_container)],
) -> PreferencesService:
    return container.preferences_service


def get_scan_runner(container: Annotated[Container, Depends(get_container)]) -> ScanRunner:
    try:
        return container.scan_runner
    except LibraryUnavailable as exc:
        raise library_error(exc) from None
