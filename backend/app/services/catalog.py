"""Use cases: browse the catalog (list/search items, get one item)."""

from dataclasses import dataclass

from app.domain.errors import ItemNotFound
from app.domain.item import Item, ItemType
from app.ports.item_repository import ItemRepository

MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class ItemPage:
    items: list[Item]
    has_more: bool
    limit: int  # effective (after the cap), so callers never repeat the rule
    offset: int


def list_items(
    repo: ItemRepository,
    *,
    query: str | None,
    item_type: ItemType | None,
    offset: int,
    limit: int,
) -> ItemPage:
    """One page of items. `limit` is capped at MAX_PAGE_SIZE no matter what the caller asks."""
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    needle = (query or "").strip()
    # One extra row tells whether another page exists without a COUNT query.
    if needle:
        rows = repo.search(needle, offset, limit + 1, item_type)
    else:
        rows = repo.list(offset, limit + 1, item_type)
    return ItemPage(items=rows[:limit], has_more=len(rows) > limit, limit=limit, offset=offset)


def get_item(repo: ItemRepository, item_id: str) -> Item:
    item = repo.get(item_id)
    if item is None:
        raise ItemNotFound
    return item
