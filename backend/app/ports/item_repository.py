"""Item repository port (interface only)."""

import builtins
from collections.abc import Collection
from typing import Protocol

from app.domain.item import Item, ItemType


class ItemRepository(Protocol):
    """Persistence of library items.

    Items flagged `missing` are hidden from `get`, `list` and `search`; only `get_by_rel_path`
    (used by the scan to revive them) still returns them.
    """

    def add(self, item: Item) -> None: ...

    def update(self, item: Item) -> None: ...

    def get(self, item_id: str) -> Item | None: ...

    def get_by_rel_path(self, rel_path: str) -> Item | None: ...

    def list(
        self, offset: int, limit: int, item_type: ItemType | None = None
    ) -> builtins.list[Item]:
        """Page of items in a stable order (title, then id)."""
        ...

    def search(
        self, query: str, offset: int, limit: int, item_type: ItemType | None = None
    ) -> builtins.list[Item]:
        """Like `list`, restricted to titles containing `query` (a literal, never a pattern)."""
        ...

    def remove_missing(self, present_rel_paths: Collection[str]) -> int:
        """Flag as missing every item whose rel_path is not in `present_rel_paths`.

        Returns how many items were newly flagged.
        """
        ...
