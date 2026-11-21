"""Library item entity."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ItemType(StrEnum):
    MANGA = "manga"
    BOOK = "book"
    PDF = "pdf"


@dataclass(frozen=True, slots=True)
class Item:
    """A readable item in the library.

    `id` is an opaque UUID string: the client only ever sees this, never `rel_path`.
    `mtime_ns` is the file modification time in nanoseconds (used for incremental scans).
    `content_hash` is computed on demand (None until requested).
    `missing` marks an item whose file vanished from the library (kept so ids stay stable if it
    comes back); repositories hide missing items from `get`/`list`/`search`.
    `series_id` links the item to its series (None until grouped); `chapter_number` is the number
    parsed from the file/folder name (None when the name has none).
    """

    id: str
    type: ItemType
    title: str
    rel_path: str
    format: str
    page_count: int
    size: int
    mtime_ns: int
    added_at: datetime
    content_hash: str | None = None
    missing: bool = False
    series_id: str | None = None
    chapter_number: float | None = None

    @property
    def has_cover(self) -> bool:
        """An item has a cover (its first page) as soon as it has at least one page."""
        return self.page_count > 0
