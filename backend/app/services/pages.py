"""Use cases: read a page or the cover of an item."""

from collections.abc import Sequence

from app.domain.errors import ItemNotFound, PageOutOfRange, UnsupportedFormat
from app.domain.item import Item
from app.domain.library import Page
from app.ports.extractor import Extractor
from app.ports.item_repository import ItemRepository


def _load(
    repo: ItemRepository, extractors: Sequence[Extractor], item_id: str
) -> tuple[Item, Extractor]:
    item = repo.get(item_id)
    if item is None:
        raise ItemNotFound
    for extractor in extractors:
        if extractor.format == item.format:
            return item, extractor
    raise UnsupportedFormat


def get_page(
    repo: ItemRepository, extractors: Sequence[Extractor], item_id: str, index: int
) -> Page:
    item, extractor = _load(repo, extractors, item_id)
    if isinstance(index, bool) or not 0 <= index < item.page_count:
        raise PageOutOfRange
    return extractor.read_page(item.rel_path, index)


def get_cover(repo: ItemRepository, extractors: Sequence[Extractor], item_id: str) -> Page:
    item, extractor = _load(repo, extractors, item_id)
    if not item.has_cover:
        raise PageOutOfRange
    return extractor.read_cover(item.rel_path)
