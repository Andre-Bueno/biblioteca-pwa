"""Reading progress: pure rules. The server (not the client) derives percent and finished."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.errors import DomainError
from app.domain.item import Item


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


def compute_position(locator: int, page_count: int) -> tuple[float, bool]:
    """`(percent, finished)` for a locator; raises `InvalidLocator` when it is not a real page."""
    if locator < 0 or locator >= page_count:
        raise InvalidLocator
    return (locator + 1) / page_count * 100.0, locator == page_count - 1
