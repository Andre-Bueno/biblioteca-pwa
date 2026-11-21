"""System routes (`/api/v1/system`): running version, new-release notice and update approval.

Any signed-in user may read the running version; everything about releases and updates is admin
only. The webhook destination is configuration: no route reads, shows or changes it. Errors are
generic (the class decides the answer, never a message).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    get_current_user,
    get_update_check_limiter,
    get_update_service,
    require_admin,
)
from app.domain.errors import (
    UpdateAlreadyRequested,
    UpdateNotAvailable,
    UpdateNotConfigured,
    UpdateNotifyFailed,
)
from app.domain.release import Release
from app.domain.user import Role, User
from app.ports.rate_limiter import RateLimiter
from app.services.update_service import UpdateService, VersionInfo

router = APIRouter(prefix="/api/v1/system", tags=["system"])

TAG_PATTERN = r"^v[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}(-[0-9A-Za-z.]{1,40})?$"

UserDep = Annotated[User, Depends(get_current_user)]
AdminDep = Annotated[User, Depends(require_admin)]
ServiceDep = Annotated[UpdateService, Depends(get_update_service)]
LimiterDep = Annotated[RateLimiter, Depends(get_update_check_limiter)]


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicVersionOut(_Out):
    current: str
    update_available: bool


class LatestOut(_Out):
    tag: str
    version: str
    name: str
    notes: str  # plain text
    published_at: datetime
    url: str | None

    @classmethod
    def from_domain(cls, r: Release) -> "LatestOut":
        return cls(
            tag=r.tag,
            version=r.version.text(),
            name=r.name,
            notes=r.notes,
            published_at=r.published_at,
            url=r.url,
        )


class UpdateStatusOut(_Out):
    state: str  # idle | requested | failed
    tag: str | None
    requested_at: datetime | None


class AdminVersionOut(_Out):
    current: str
    update_available: bool
    latest: LatestOut | None
    checked_at: datetime | None
    webhook_configured: bool
    update: UpdateStatusOut

    @classmethod
    def from_info(cls, info: VersionInfo) -> "AdminVersionOut":
        return cls(
            current=info.current,
            update_available=info.update_available,
            latest=None if info.latest is None else LatestOut.from_domain(info.latest),
            checked_at=info.checked_at,
            webhook_configured=info.webhook_configured,
            update=UpdateStatusOut(
                state=info.update.state, tag=info.update.tag, requested_at=info.update.requested_at
            ),
        )


class UpdateRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    tag: str = Field(min_length=2, max_length=64, pattern=TAG_PATTERN)


class UpdateAcceptedOut(_Out):
    state: str
    tag: str
    requested_at: datetime


@router.get("/version", response_model=None)
def get_version(user: UserDep, service: ServiceDep) -> AdminVersionOut | PublicVersionOut:
    if user.role is not Role.ADMIN:
        # Nothing about releases leaves for a regular user, and no lookup is triggered by one.
        return PublicVersionOut(current=service.current, update_available=False)
    return AdminVersionOut.from_info(service.info())


@router.post("/update/check")
def check_for_update(admin: AdminDep, service: ServiceDep, limiter: LimiterDep) -> AdminVersionOut:
    decision = limiter.check(admin.id)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    service.refresh(force=True)
    return AdminVersionOut.from_info(service.snapshot())


@router.post("/update", status_code=202)
def request_update(
    body: UpdateRequestIn, admin: AdminDep, service: ServiceDep, response: Response
) -> UpdateAcceptedOut:
    try:
        status = service.request_update(admin.id, body.tag)
    except UpdateNotConfigured:
        raise HTTPException(status_code=503, detail="Update is not configured") from None
    except UpdateNotAvailable:
        raise HTTPException(status_code=409, detail="That update is not available") from None
    except UpdateAlreadyRequested:
        raise HTTPException(status_code=409, detail="An update was already requested") from None
    except UpdateNotifyFailed:
        raise HTTPException(status_code=502, detail="Update request failed") from None
    if status.tag is None or status.requested_at is None:  # cannot happen after a success
        raise HTTPException(status_code=502, detail="Update request failed")
    return UpdateAcceptedOut(state=status.state, tag=status.tag, requested_at=status.requested_at)
