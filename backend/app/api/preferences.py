"""User preferences routes (`/api/v1/me/preferences`). Always the authenticated user's own."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_preferences_service
from app.api.progress_schemas import PreferencesIn, PreferencesOut
from app.domain.errors import DataAccessError
from app.domain.user import User, UserNotFoundError
from app.services.preferences_service import PreferencesService

router = APIRouter(prefix="/api/v1/me/preferences", tags=["preferences"])

UserDep = Annotated[User, Depends(get_current_user)]
ServiceDep = Annotated[PreferencesService, Depends(get_preferences_service)]


@router.get("", response_model=PreferencesOut)
def get_preferences(user: UserDep, service: ServiceDep) -> PreferencesOut:
    try:
        return PreferencesOut.from_domain(service.get(user.id))
    except UserNotFoundError:
        raise HTTPException(status_code=401, detail="Not authenticated") from None
    except DataAccessError:
        raise HTTPException(status_code=503, detail="Service unavailable") from None


@router.put("", response_model=PreferencesOut)
def put_preferences(body: PreferencesIn, user: UserDep, service: ServiceDep) -> PreferencesOut:
    try:
        return PreferencesOut.from_domain(service.update(user.id, body.to_domain()))
    except UserNotFoundError:
        raise HTTPException(status_code=401, detail="Not authenticated") from None
    except DataAccessError:
        raise HTTPException(status_code=503, detail="Service unavailable") from None
