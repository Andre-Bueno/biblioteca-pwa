from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import (
    DataAccessError,
    DomainError,
    EnrichAlreadyRunning,
    ExternalFetchError,
    InvalidMetadata,
    ItemNotFound,
    LibraryUnavailable,
    MetadataDisabled,
    PageOutOfRange,
    ResourceBusy,
    ScanAlreadyRunning,
)

ENRICH_RUNNING_DETAIL = "An enrichment is already running"
METADATA_DISABLED_DETAIL = "Metadata lookup is disabled"
SOURCE_UNAVAILABLE_DETAIL = "Metadata source unavailable"
INVALID_DETAIL = "Invalid request"
BUSY_DETAIL = "Service busy. Try again later."
NOT_FOUND_DETAIL = "Not found"
UNREADABLE_DETAIL = "Item cannot be read"
UNAVAILABLE_DETAIL = "Library unavailable"
SCAN_RUNNING_DETAIL = "A scan is already running"


async def validation_error_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    """Generic 422. FastAPI's default body echoes the offending input (`input`), which would
    reflect passwords and tokens into responses and logs."""
    return JSONResponse(status_code=422, content={"detail": "Invalid request"})


def not_found() -> HTTPException:
    return HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)


def library_error(exc: Exception) -> HTTPException:
    """Map a domain/IO failure to a generic response.

    Nothing from the exception (message, path, file name) reaches the client: the mapping depends
    only on the exception CLASS. Unknown exceptions are not mapped (the caller re-raises them and
    the outer middleware answers a generic 500).
    """
    if isinstance(exc, ItemNotFound | PageOutOfRange | FileNotFoundError):
        return not_found()
    if isinstance(exc, ResourceBusy):
        return HTTPException(status_code=503, detail=BUSY_DETAIL, headers={"Retry-After": "1"})
    if isinstance(exc, LibraryUnavailable | DataAccessError | OSError):
        return HTTPException(status_code=503, detail=UNAVAILABLE_DETAIL)
    if isinstance(exc, ScanAlreadyRunning):
        return HTTPException(status_code=409, detail=SCAN_RUNNING_DETAIL)
    if isinstance(exc, EnrichAlreadyRunning):
        return HTTPException(status_code=409, detail=ENRICH_RUNNING_DETAIL)
    if isinstance(exc, MetadataDisabled):
        return HTTPException(status_code=503, detail=METADATA_DISABLED_DETAIL)
    if isinstance(exc, ExternalFetchError):
        # No reason code, host or URL: the client only learns the source is unavailable.
        return HTTPException(status_code=502, detail=SOURCE_UNAVAILABLE_DETAIL)
    if isinstance(exc, InvalidMetadata):
        return HTTPException(status_code=422, detail=INVALID_DETAIL)
    if isinstance(exc, DomainError):
        # Corrupt/unsupported/over-limit/unsafe: the item itself cannot be served.
        return HTTPException(status_code=422, detail=UNREADABLE_DETAIL)
    raise exc
