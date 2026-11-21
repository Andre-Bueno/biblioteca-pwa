"""Use cases: save/read/clear reading progress and list "continue reading"."""

from app.domain.errors import ItemNotFound
from app.domain.progress import ContinueEntry, Progress, compute_position
from app.ports.clock import Clock
from app.ports.item_repository import ItemRepository
from app.ports.progress_repository import ProgressRepository

MAX_CONTINUE_LIMIT = 50


class ProgressService:
    def __init__(self, items: ItemRepository, progress: ProgressRepository, clock: Clock) -> None:
        self._items = items
        self._progress = progress
        self._clock = clock

    def save(
        self, user_id: str, item_id: str, locator: int, device_id: str | None = None
    ) -> Progress:
        """Validate against the item, derive percent/finished and stamp with the server clock.

        Raises ItemNotFound (unknown or missing item) or InvalidLocator.
        """
        item = self._items.get(item_id)
        if item is None:
            raise ItemNotFound
        percent, finished = compute_position(locator, item.page_count)
        saved = Progress(
            user_id=user_id,
            item_id=item_id,
            locator=locator,
            percent=percent,
            finished=finished,
            updated_at=self._clock.now(),
            device_id=device_id,
        )
        self._progress.upsert(saved)
        return saved

    def get(self, user_id: str, item_id: str) -> Progress:
        found = self._progress.get(user_id, item_id)
        if found is None:
            raise ItemNotFound
        return found

    def clear(self, user_id: str, item_id: str) -> None:
        self._progress.delete(user_id, item_id)

    def continue_reading(self, user_id: str, limit: int) -> list[ContinueEntry]:
        """`limit` is capped to MAX_CONTINUE_LIMIT no matter what the caller asks."""
        return self._progress.list_continue(user_id, max(1, min(limit, MAX_CONTINUE_LIMIT)))
