"""Catalog routes (`/api/v1/items`). Thin: validate the opaque id, call a service, map errors.

Every route needs an authenticated user. The client only ever sends an opaque UUID and a page
number; paths come from the database, and the response never carries `rel_path` or file names.
Error bodies are generic: they depend on the exception class only, never on its message.
"""

import hashlib
import re
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.deps import get_current_user, get_extractors, get_item_repository
from app.api.errors import UNREADABLE_DETAIL, library_error, not_found
from app.api.ids import item_id_or_404
from app.api.library_schemas import ItemListOut, ItemOut
from app.api.security_headers import CACHE_MARKER_HEADER, CACHE_MARKER_PRIVATE_IMAGE
from app.domain.errors import DomainError
from app.domain.item import ItemType
from app.domain.library import Page
from app.ports.extractor import Extractor
from app.ports.item_repository import ItemRepository
from app.services import catalog
from app.services.pages import get_cover, get_page

router = APIRouter(prefix="/api/v1/items", tags=["items"], dependencies=[Depends(get_current_user)])

DEFAULT_LIMIT = 50
MAX_QUERY_LENGTH = 100
MAX_OFFSET = 1_000_000
ALLOWED_IMAGE_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
)
_PAGE_NUMBER = re.compile(r"[0-9]{1,9}")  # ASCII digits only: no sign, no unicode digits

RepoDep = Annotated[ItemRepository, Depends(get_item_repository)]
ExtractorsDep = Annotated[Sequence[Extractor], Depends(get_extractors)]


def _page_index(raw: str) -> int:
    if _PAGE_NUMBER.fullmatch(raw) is None:
        raise not_found()
    return int(raw)


def etag_matches(header_value: str | None, etag: str) -> bool:
    """If-None-Match (weak comparison, RFC 9110 13.1.2)."""
    if not header_value or len(header_value) > 2048:
        return False
    candidates = [c.strip() for c in header_value.split(",")]
    return "*" in candidates or any(c.removeprefix("W/") == etag for c in candidates)


def image_response(request: Request, page: Page) -> Response:
    # Defense in depth: the type comes from magic bytes in the extractor; anything else is refused.
    if page.media_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=422, detail=UNREADABLE_DETAIL)
    etag = f'"{hashlib.sha256(page.data).hexdigest()}"'
    headers = {
        "ETag": etag,
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        # Asks the security-headers middleware for the (allowlisted) private cache policy.
        CACHE_MARKER_HEADER: CACHE_MARKER_PRIVATE_IMAGE,
    }
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=page.data, media_type=page.media_type, headers=headers)


@router.get("", response_model=ItemListOut)
def list_items(
    repo: RepoDep,
    type: Annotated[ItemType | None, Query()] = None,  # noqa: A002 - public query parameter name
    q: Annotated[str | None, Query(max_length=MAX_QUERY_LENGTH)] = None,
    limit: Annotated[int, Query(ge=1)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> ItemListOut:
    # `limit` above the maximum is capped (not rejected) by the service, which reports the
    # effective limit/offset in the page.
    try:
        page = catalog.list_items(repo, query=q, item_type=type, offset=offset, limit=limit)
    except Exception as exc:
        raise library_error(exc) from None
    return ItemListOut.from_page(page)


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: str, repo: RepoDep) -> ItemOut:
    try:
        return ItemOut.from_domain(catalog.get_item(repo, item_id_or_404(item_id)))
    except HTTPException:
        raise
    except Exception as exc:
        raise library_error(exc) from None


@router.get("/{item_id}/pages/{n}")
def get_item_page(
    item_id: str, n: str, request: Request, repo: RepoDep, extractors: ExtractorsDep
) -> Response:
    ident, index = item_id_or_404(item_id), _page_index(n)
    try:
        page = get_page(repo, extractors, ident, index)
    except (DomainError, OSError) as exc:
        raise library_error(exc) from None
    return image_response(request, page)


@router.get("/{item_id}/cover")
def get_item_cover(
    item_id: str, request: Request, repo: RepoDep, extractors: ExtractorsDep
) -> Response:
    ident = item_id_or_404(item_id)
    try:
        page = get_cover(repo, extractors, ident)
    except (DomainError, OSError) as exc:
        raise library_error(exc) from None
    return image_response(request, page)
