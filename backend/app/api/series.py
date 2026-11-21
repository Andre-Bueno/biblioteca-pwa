"""Series routes (`/api/v1/series`). Thin: validate the opaque id, call a service, map errors.

Authenticated only. The user id for progress always comes from the token. Responses never carry a
file path; errors are generic and depend on the exception class only.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.deps import (
    get_candidates_limiter,
    get_cover_store,
    get_current_user,
    get_extractors,
    get_metadata_service,
    get_series_repository,
    get_series_service,
    require_admin,
)
from app.api.errors import library_error
from app.api.ids import item_id_or_404
from app.api.items import image_response
from app.api.rate_limit import RATE_LIMITED_DETAIL
from app.api.series_schemas import (
    CandidateListOut,
    CandidateOut,
    ManualMetadataRequest,
    SelectCandidateRequest,
    SeriesListOut,
    SeriesMetadataOut,
    SeriesOut,
)
from app.domain.user import User
from app.ports.cover_store import CoverStore
from app.ports.extractor import Extractor
from app.ports.rate_limiter import RateLimiter
from app.ports.series_repository import SeriesRepository
from app.services.metadata_service import MetadataService
from app.services.series_service import SeriesService, get_series_cover

router = APIRouter(prefix="/api/v1/series", tags=["series"])

DEFAULT_LIMIT = 50
MAX_QUERY_LENGTH = 100  # same as the metadata search (domain.metadata.MAX_QUERY_LENGTH)
MAX_OFFSET = 1_000_000

UserDep = Annotated[User, Depends(get_current_user)]
ServiceDep = Annotated[SeriesService, Depends(get_series_service)]
RepoDep = Annotated[SeriesRepository, Depends(get_series_repository)]
ExtractorsDep = Annotated[Sequence[Extractor], Depends(get_extractors)]
CoversDep = Annotated[CoverStore, Depends(get_cover_store)]
AdminDep = Annotated[User, Depends(require_admin)]
MetadataDep = Annotated[MetadataService, Depends(get_metadata_service)]
LimiterDep = Annotated[RateLimiter, Depends(get_candidates_limiter)]


@router.get("", response_model=SeriesListOut)
def list_series(
    user: UserDep,
    service: ServiceDep,
    q: Annotated[str | None, Query(max_length=MAX_QUERY_LENGTH)] = None,
    limit: Annotated[int, Query(ge=1)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> SeriesListOut:
    # `limit` above the maximum is capped (not rejected) by the service.
    try:
        page = service.list_series(user.id, query=q, offset=offset, limit=limit)
    except Exception as exc:
        raise library_error(exc) from None
    return SeriesListOut.from_page(page)


@router.get("/{series_id}", response_model=SeriesOut, response_model_by_alias=True)
def get_series(series_id: str, user: UserDep, service: ServiceDep) -> SeriesOut:
    ident = item_id_or_404(series_id)
    try:
        return SeriesOut.from_domain(service.get_series(user.id, ident))
    except HTTPException:
        raise
    except Exception as exc:
        raise library_error(exc) from None


@router.get("/{series_id}/cover")
def get_cover(
    series_id: str,
    request: Request,
    user: UserDep,
    repo: RepoDep,
    extractors: ExtractorsDep,
    covers: CoversDep,
) -> Response:
    del user  # authentication only: the cover is the same for every user
    ident = item_id_or_404(series_id)
    try:
        page = get_series_cover(repo, extractors, ident, covers)
    except Exception as exc:
        raise library_error(exc) from None
    return image_response(request, page)


# -- metadata management: admin only (they reach public sources or change what everyone sees) ----


@router.get("/{series_id}/metadata/candidates", response_model=CandidateListOut)
def metadata_candidates(
    series_id: str,
    admin: AdminDep,
    service: MetadataDep,
    limiter: LimiterDep,
    q: Annotated[str | None, Query(max_length=MAX_QUERY_LENGTH)] = None,
) -> CandidateListOut:
    ident = item_id_or_404(series_id)
    decision = limiter.check(admin.id)  # per user, before any outbound request
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail=RATE_LIMITED_DETAIL,
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    try:
        views = service.candidates(ident, q)
    except Exception as exc:
        raise library_error(exc) from None
    return CandidateListOut(items=[CandidateOut.from_view(v) for v in views])


@router.post("/{series_id}/metadata/select", response_model=SeriesMetadataOut)
def metadata_select(
    series_id: str, body: SelectCandidateRequest, _admin: AdminDep, service: MetadataDep
) -> SeriesMetadataOut:
    ident = item_id_or_404(series_id)
    try:
        series = service.select(ident, body.provider, body.external_id)
    except Exception as exc:
        raise library_error(exc) from None
    return SeriesMetadataOut.from_domain(series)


@router.put("/{series_id}/metadata", response_model=SeriesMetadataOut)
def metadata_edit(
    series_id: str, body: ManualMetadataRequest, _admin: AdminDep, service: MetadataDep
) -> SeriesMetadataOut:
    ident = item_id_or_404(series_id)
    try:
        series = service.set_manual(ident, body.title, body.description)
    except Exception as exc:
        raise library_error(exc) from None
    return SeriesMetadataOut.from_domain(series)


@router.delete("/{series_id}/metadata", response_model=SeriesMetadataOut)
def metadata_clear(series_id: str, _admin: AdminDep, service: MetadataDep) -> SeriesMetadataOut:
    ident = item_id_or_404(series_id)
    try:
        series = service.clear(ident)
    except Exception as exc:
        raise library_error(exc) from None
    return SeriesMetadataOut.from_domain(series)
