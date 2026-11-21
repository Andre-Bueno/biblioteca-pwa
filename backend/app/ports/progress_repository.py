"""Reading progress port (interface only). Every method is scoped by `user_id`."""

from collections.abc import Sequence
from typing import Protocol

from app.domain.progress import ContinueEntry, Progress


class ProgressRepository(Protocol):
    def upsert(self, progress: Progress) -> None:
        """Atomic insert-or-replace by (user_id, item_id): the last write to arrive wins.

        Raise DataAccessError.
        """
        ...

    def get(self, user_id: str, item_id: str) -> Progress | None: ...

    def list_for_items(self, user_id: str, item_ids: Sequence[str]) -> dict[str, Progress]:
        """Progress of this user for the given items, keyed by item id (unread items are absent)."""
        ...

    def delete(self, user_id: str, item_id: str) -> None:
        """Idempotent: nothing to delete is not an error."""
        ...

    def list_continue(self, user_id: str, limit: int) -> list[ContinueEntry]:
        """Unfinished progress of items that are not missing, newest `updated_at` first."""
        ...
