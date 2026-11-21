"""Use cases: open a book, read one of its (sanitized) chapters, read one of its images."""

from collections.abc import Sequence

from app.domain.book import RESOURCE_URL_TEMPLATE, BookInfo, validate_book_options
from app.domain.errors import ItemNotFound, UnsupportedFormat
from app.domain.item import Item, ItemType
from app.domain.library import Page
from app.ports.book_reader import BookReader
from app.ports.item_repository import ItemRepository


def _load(
    repo: ItemRepository, readers: Sequence[BookReader], item_id: str
) -> tuple[Item, BookReader]:
    item = repo.get(item_id)
    if item is None or item.type is not ItemType.BOOK:
        raise ItemNotFound  # an image-only item has no book routes: same answer as "unknown"
    for reader in readers:
        if reader.format == item.format:
            return item, reader
    raise UnsupportedFormat


def get_book(repo: ItemRepository, readers: Sequence[BookReader], item_id: str) -> BookInfo:
    item, reader = _load(repo, readers, item_id)
    return reader.read_book(item.rel_path)


def get_chapter(
    repo: ItemRepository,
    readers: Sequence[BookReader],
    item_id: str,
    index: int,
    *,
    theme: str,
    size: int,
) -> str:
    """The chapter as a complete sanitized HTML document. Options are validated first."""
    validate_book_options(theme, size)
    item, reader = _load(repo, readers, item_id)

    def resource_url(rid: int) -> str:
        return RESOURCE_URL_TEMPLATE.format(item_id=item.id, rid=rid)

    return reader.read_chapter(
        item.rel_path, index, theme=theme, size=size, resource_url=resource_url
    )


def get_resource(
    repo: ItemRepository, readers: Sequence[BookReader], item_id: str, rid: int
) -> Page:
    item, reader = _load(repo, readers, item_id)
    return reader.read_resource(item.rel_path, rid)
