"""Extractor for a folder of images (one directory = one item)."""

import posixpath

from app.adapters.extractors._common import (
    HEADER_BYTES,
    INDEX_CACHE_SIZE,
    IndexKey,
    PageIndexCache,
    default_read_gate,
    has_image_extension,
    sniff_image,
)
from app.adapters.gate import BoundedGate
from app.domain.errors import ArchiveLimitExceeded, PageOutOfRange, UnsupportedFormat
from app.domain.item import ItemType
from app.domain.library import ExtractorLimits, ItemMetadata, Page, natural_key
from app.ports.storage import StorageBackend, StorageEntry


class FolderExtractor:
    format = "folder"
    item_type = ItemType.MANGA

    def __init__(
        self,
        storage: StorageBackend,
        limits: ExtractorLimits,
        *,
        index_cache_size: int = INDEX_CACHE_SIZE,
        gate: BoundedGate | None = None,
    ) -> None:
        self._storage = storage
        self._limits = limits
        # Validated page list per (rel_path, size, mtime_ns) of the folder (see the storage port:
        # size/mtime cover the direct files). Items are (rel_path of the file, media type).
        self._index: PageIndexCache[tuple[str, str]] = PageIndexCache(index_cache_size)
        self._gate = gate or default_read_gate()

    @property
    def cached_folders(self) -> int:
        return len(self._index)

    def can_handle(self, entry: StorageEntry) -> bool:
        if not entry.is_dir:
            return False
        try:
            children = self._storage.list_children(entry.rel_path)
        except OSError:
            return False
        return any(not c.is_dir and has_image_extension(c.rel_path) for c in children)

    def _build_index(self, rel_path: str) -> tuple[tuple[str, str], ...]:
        """Image files whose first bytes really are an image (same rule as the CBZ extractor),
        in natural order. Reads HEADER_BYTES of every candidate: done once per folder version."""
        children = self._storage.list_children(rel_path)
        if len(children) > self._limits.max_entries:
            raise ArchiveLimitExceeded
        candidates = [c for c in children if not c.is_dir and has_image_extension(c.rel_path)]
        candidates.sort(key=lambda c: natural_key(posixpath.basename(c.rel_path)))
        pages: list[tuple[str, str]] = []
        for entry in candidates:
            if entry.size > self._limits.max_page_bytes:
                raise ArchiveLimitExceeded
            with self._storage.open(entry.rel_path) as fh:
                media_type = sniff_image(fh.read(HEADER_BYTES))
            if media_type is not None:  # fake extensions (text named .jpg) are not pages
                pages.append((entry.rel_path, media_type))
        return tuple(pages)

    def _pages(self, rel_path: str) -> tuple[tuple[str, str], ...]:
        stat = self._storage.stat(rel_path)
        key: IndexKey = (rel_path, stat.size, stat.mtime_ns)
        cached = self._index.get(key)
        if cached is not None:
            return cached
        pages = self._build_index(rel_path)
        if pages:
            self._index.put(key, pages)
        return pages

    def _read(self, page_path: str, media_type: str) -> Page:
        limit = self._limits.max_page_bytes
        with self._gate.slot(), self._storage.open(page_path) as fh:
            data = fh.read(limit + 1)
        if len(data) > limit:
            raise ArchiveLimitExceeded
        if sniff_image(data[:HEADER_BYTES]) != media_type:
            raise UnsupportedFormat  # the file changed since it was indexed
        return Page(data=data, media_type=media_type)

    def inspect(self, rel_path: str) -> ItemMetadata:
        pages = self._pages(rel_path)
        if not pages:
            raise UnsupportedFormat
        return ItemMetadata(page_count=len(pages))

    def read_page(self, rel_path: str, index: int) -> Page:
        pages = self._pages(rel_path)
        if not 0 <= index < len(pages):
            raise PageOutOfRange
        page_path, media_type = pages[index]
        return self._read(page_path, media_type)

    def read_cover(self, rel_path: str) -> Page:
        return self.read_page(rel_path, 0)
