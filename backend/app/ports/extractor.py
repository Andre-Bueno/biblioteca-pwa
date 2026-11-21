"""Extractor port: reads one file format. Pages are served from memory, never to disk."""

from typing import Protocol

from app.domain.item import ItemType
from app.domain.library import ItemMetadata, Page
from app.ports.storage import StorageEntry


class Extractor(Protocol):
    format: str
    item_type: ItemType

    def can_handle(self, entry: StorageEntry) -> bool:
        """Cheap check by entry kind/name; does not validate content."""
        ...

    def inspect(self, rel_path: str) -> ItemMetadata:
        """Validate the file and return its metadata. Raises domain errors."""
        ...

    def read_page(self, rel_path: str, index: int) -> Page:
        """Read page `index` (0-based). Raises PageOutOfRange or domain errors."""
        ...

    def read_cover(self, rel_path: str) -> Page: ...
