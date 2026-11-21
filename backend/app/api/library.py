"""Library administration routes (`/api/v1/library`): admin only. No endpoint takes a path."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_enrich_runner, get_metadata_service, get_scan_runner, require_admin
from app.api.errors import library_error
from app.api.library_schemas import EnrichStatusOut, ScanStatusOut
from app.domain.errors import EnrichAlreadyRunning, MetadataDisabled, ScanAlreadyRunning
from app.services.enrich_runner import EnrichRunner
from app.services.metadata_service import MetadataService
from app.services.scan_runner import ScanRunner

router = APIRouter(
    prefix="/api/v1/library", tags=["library"], dependencies=[Depends(require_admin)]
)

RunnerDep = Annotated[ScanRunner, Depends(get_scan_runner)]
EnrichRunnerDep = Annotated[EnrichRunner, Depends(get_enrich_runner)]
MetadataDep = Annotated[MetadataService, Depends(get_metadata_service)]


@router.post("/scan", status_code=202, response_model=ScanStatusOut)
def start_scan(runner: RunnerDep) -> ScanStatusOut:
    """Start a scan of the configured library in the background (one at a time: 409 otherwise)."""
    try:
        runner.start()
    except ScanAlreadyRunning as exc:
        raise library_error(exc) from None
    return ScanStatusOut.from_domain(runner.status())


@router.get("/scan/status", response_model=ScanStatusOut)
def scan_status(runner: RunnerDep) -> ScanStatusOut:
    return ScanStatusOut.from_domain(runner.status())


@router.post("/enrich", status_code=202, response_model=EnrichStatusOut)
def start_enrich(
    runner: EnrichRunnerDep, service: MetadataDep, force: Annotated[bool, Query()] = False
) -> EnrichStatusOut:
    """Fetch covers/descriptions from the public sources in the background (one run at a time:
    409 otherwise). `force` re-checks matched and not_found series but never a `manual` one."""
    try:
        service.require_enabled()
        runner.start(force=force)
    except (EnrichAlreadyRunning, MetadataDisabled) as exc:
        raise library_error(exc) from None
    return EnrichStatusOut.from_domain(runner.status())


@router.get("/enrich/status", response_model=EnrichStatusOut)
def enrich_status(runner: EnrichRunnerDep) -> EnrichStatusOut:
    return EnrichStatusOut.from_domain(runner.status())
