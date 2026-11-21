"""Book (EPUB) value objects and pure rules. No I/O.

A book is read chapter by chapter: a "chapter" is one item of the EPUB spine. Everything inside an
EPUB is untrusted; the adapter turns it into sanitized HTML and these value objects carry only
already-sanitized text.
"""

from dataclasses import dataclass

from app.domain.errors import DomainError

BOOK_THEMES = ("auto", "light", "dark", "sepia")
MIN_FONT_SCALE = 80
MAX_FONT_SCALE = 200
DEFAULT_FONT_SCALE = 100
DEFAULT_BOOK_THEME = "auto"

# Upper bounds that keep a locator (`chapter * 10_000 + offset`) inside a signed 32-bit integer.
MAX_CHAPTERS = 100_000

# Public URL of an image of a book. The adapter writes it into sanitized chapters; `rid` is an
# opaque integer chosen by the server (never a path).
RESOURCE_URL_TEMPLATE = "/api/v1/items/{item_id}/book/res/{rid}"


class InvalidBookOptions(DomainError):  # noqa: N818
    """Theme or font scale outside the allowed set. Raised before any file is opened."""


def validate_book_options(theme: str, size: int) -> None:
    if theme not in BOOK_THEMES:
        raise InvalidBookOptions("theme")
    if isinstance(size, bool) or not MIN_FONT_SCALE <= size <= MAX_FONT_SCALE:
        raise InvalidBookOptions("size")


@dataclass(frozen=True, slots=True)
class ChapterRef:
    index: int
    title: str


@dataclass(frozen=True, slots=True)
class TocEntry:
    title: str
    index: int
    anchor: str | None


@dataclass(frozen=True, slots=True)
class BookInfo:
    """What the reader UI needs to open a book. All text is sanitized."""

    title: str
    authors: tuple[str, ...]
    language: str | None
    chapters: tuple[ChapterRef, ...]
    toc: tuple[TocEntry, ...]
    has_cover: bool
