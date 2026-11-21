"""Book routes (`/api/v1/items/{id}/book...`): metadata and table of contents, one chapter as
sanitized HTML for a sandboxed frame, and the images of the book.

Same rules as the catalog: authenticated user, opaque UUID, a hostile id/number is a generic 404,
nothing about the file path or its internal names in any response, errors by exception CLASS only.
A chapter's theme and font scale are validated against a whitelist before anything is opened and
never reach the CSS as text (the adapter builds the stylesheet from validated values).
"""

import hashlib
import re
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.book_schemas import BookOut
from app.api.deps import get_book_readers, get_current_user, get_item_repository
from app.api.errors import library_error, not_found
from app.api.ids import item_id_or_404
from app.api.items import etag_matches, image_response
from app.api.security_headers import CACHE_MARKER_BOOK_CHAPTER, CACHE_MARKER_HEADER
from app.domain.book import MAX_FONT_SCALE, MIN_FONT_SCALE
from app.domain.errors import DomainError
from app.ports.book_reader import BookReader
from app.ports.item_repository import ItemRepository
from app.services import book as book_service

router = APIRouter(prefix="/api/v1/items", tags=["books"], dependencies=[Depends(get_current_user)])

_INDEX = re.compile(r"[0-9]{1,6}")  # ASCII digits only: no sign, no unicode digits

RepoDep = Annotated[ItemRepository, Depends(get_item_repository)]
ReadersDep = Annotated[Sequence[BookReader], Depends(get_book_readers)]
ThemeQuery = Annotated[str, Query(pattern=r"^(auto|light|dark|sepia)$")]
SizeQuery = Annotated[int, Query(ge=MIN_FONT_SCALE, le=MAX_FONT_SCALE)]


def _number(raw: str) -> int:
    if _INDEX.fullmatch(raw) is None:
        raise not_found()
    return int(raw)


@router.get("/{item_id}/book", response_model=BookOut)
def get_book(item_id: str, repo: RepoDep, readers: ReadersDep) -> BookOut:
    ident = item_id_or_404(item_id)
    try:
        return BookOut.from_domain(book_service.get_book(repo, readers, ident))
    except (DomainError, OSError) as exc:
        raise library_error(exc) from None


@router.get("/{item_id}/book/chapters/{n}")
def get_book_chapter(
    item_id: str,
    n: str,
    request: Request,
    repo: RepoDep,
    readers: ReadersDep,
    theme: ThemeQuery = "auto",
    size: SizeQuery = 100,
) -> Response:
    ident, index = item_id_or_404(item_id), _number(n)
    try:
        document = book_service.get_chapter(repo, readers, ident, index, theme=theme, size=size)
    except (DomainError, OSError) as exc:
        raise library_error(exc) from None
    content = document.encode("utf-8")
    etag = f'"{hashlib.sha256(content).hexdigest()}"'
    headers = {
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
        # The middleware (not this route) decides the CSP and the private cache for this path.
        CACHE_MARKER_HEADER: CACHE_MARKER_BOOK_CHAPTER,
    }
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=content, media_type="text/html; charset=utf-8", headers=headers)


@router.get("/{item_id}/book/res/{rid}")
def get_book_resource(
    item_id: str, rid: str, request: Request, repo: RepoDep, readers: ReadersDep
) -> Response:
    ident, number = item_id_or_404(item_id), _number(rid)
    try:
        page = book_service.get_resource(repo, readers, ident, number)
    except (DomainError, OSError) as exc:
        raise library_error(exc) from None
    return image_response(request, page)
