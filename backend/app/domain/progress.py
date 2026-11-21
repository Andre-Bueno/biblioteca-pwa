"""Reading progress: pure rules. The server (not the client) derives percent and finished."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.book import MAX_CHAPTERS as MAX_BOOK_CHAPTERS
from app.domain.errors import DomainError
from app.domain.item import Item, ItemType


class InvalidLocator(DomainError):  # noqa: N818
    """The locator is outside the item (negative or >= page_count)."""


@dataclass(frozen=True, slots=True)
class Progress:
    """Where one user stopped in one item. `locator` is the 0-based page index."""

    user_id: str
    item_id: str
    locator: int
    percent: float
    finished: bool
    updated_at: datetime
    device_id: str | None = None


@dataclass(frozen=True, slots=True)
class ContinueEntry:
    """An unfinished progress together with its item (for the "continue reading" shelf)."""

    item: Item
    progress: Progress
    series_id: str | None = None
    series_title: str | None = None


BOOK_CHAPTER_STRIDE = 10_000  # locator of a book = chapter_index * STRIDE + offset (basis points)
BOOK_FINISHED_OFFSET = 9_000  # last chapter read up to this point counts as finished


def split_book_locator(locator: int) -> tuple[int, int]:
    """`(chapter_index, offset_bp)` of a book locator."""
    return divmod(locator, BOOK_CHAPTER_STRIDE)


def encode_book_locator(chapter_index: int, offset_bp: int) -> int:
    """Locator for a position inside a chapter; `offset_bp` is 0..9999 (hundredths of a percent)."""
    if not 0 <= offset_bp < BOOK_CHAPTER_STRIDE or chapter_index < 0:
        raise InvalidLocator
    return chapter_index * BOOK_CHAPTER_STRIDE + offset_bp


def compute_book_position(locator: int, page_count: int) -> tuple[float, bool]:
    """`(percent, finished)` for a book locator. `page_count` is the number of chapters.

    percent = (chapter + offset / 10000) / chapters * 100; finished = last chapter and offset
    >= 9000. Raises `InvalidLocator` when the chapter does not exist or the locator is negative
    (the offset is always 0..9999 by construction of the encoding).
    """
    if locator < 0 or page_count > MAX_BOOK_CHAPTERS:
        raise InvalidLocator
    chapter, offset = split_book_locator(locator)
    if chapter >= page_count:
        raise InvalidLocator
    percent = (chapter + offset / BOOK_CHAPTER_STRIDE) / page_count * 100.0
    finished = chapter == page_count - 1 and offset >= BOOK_FINISHED_OFFSET
    return min(percent, 100.0), finished


def compute_position(
    locator: int, page_count: int, item_type: ItemType = ItemType.MANGA
) -> tuple[float, bool]:
    """`(percent, finished)` for a locator; raises `InvalidLocator` when it is not a real page.

    Manga and PDF: the locator is the 0-based page. Books: see `compute_book_position`.
    """
    if item_type is ItemType.BOOK:
        return compute_book_position(locator, page_count)
    if locator < 0 or locator >= page_count:
        raise InvalidLocator
    return (locator + 1) / page_count * 100.0, locator == page_count - 1
