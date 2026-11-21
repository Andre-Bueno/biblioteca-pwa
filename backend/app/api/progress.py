"""Reading progress routes (`/api/v1/progress`). Thin: authenticate, validate, call the service.

The user id always comes from the authenticated token; the client only sends an opaque item UUID
and a page index. percent/finished are computed by the server. Errors are generic.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.deps import get_current_user, get_progress_service
from app.api.errors import not_found
from app.api.ids import item_id_or_404
from app.api.progress_schemas import (
    ContinueItemOut,
    ContinueListOut,
    ProgressOut,
    SaveProgressRequest,
)
from app.domain.errors import DataAccessError, ItemNotFound
from app.domain.progress import InvalidLocator
from app.domain.user import User
from app.services.progress_service import ProgressService

router = APIRouter(prefix="/api/v1/progress", tags=["progress"])

DEFAULT_CONTINUE_LIMIT = 10

UserDep = Annotated[User, Depends(get_current_user)]
ServiceDep = Annotated[ProgressService, Depends(get_progress_service)]


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Service unavailable")


# Declared before "/{item_id}" so "continue" is never taken as an id.
@router.get("/continue", response_model=ContinueListOut)
def continue_reading(
    user: UserDep,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1)] = DEFAULT_CONTINUE_LIMIT,
) -> ContinueListOut:
    # `limit` above the maximum is capped by the service, not rejected.
    try:
        entries = service.continue_reading(user.id, limit)
    except DataAccessError:
        raise _unavailable() from None
    return ContinueListOut(items=[ContinueItemOut.from_domain(e) for e in entries])


@router.get("/{item_id}", response_model=ProgressOut)
def get_progress(item_id: str, user: UserDep, service: ServiceDep) -> ProgressOut:
    ident = item_id_or_404(item_id)
    try:
        return ProgressOut.from_domain(service.get(user.id, ident))
    except ItemNotFound:
        raise not_found() from None
    except DataAccessError:
        raise _unavailable() from None


@router.put("/{item_id}", response_model=ProgressOut)
def save_progress(
    item_id: str, body: SaveProgressRequest, user: UserDep, service: ServiceDep
) -> ProgressOut:
    ident = item_id_or_404(item_id)
    try:
        saved = service.save(user.id, ident, body.locator, body.device_id)
    except ItemNotFound:
        raise not_found() from None
    except InvalidLocator:
        raise HTTPException(status_code=422, detail="Invalid request") from None
    except DataAccessError:
        raise _unavailable() from None
    return ProgressOut.from_domain(saved)


@router.delete("/{item_id}", status_code=204)
def clear_progress(item_id: str, user: UserDep, service: ServiceDep) -> Response:
    ident = item_id_or_404(item_id)
    try:
        service.clear(user.id, ident)
    except DataAccessError:
        raise _unavailable() from None
    return Response(status_code=204)
