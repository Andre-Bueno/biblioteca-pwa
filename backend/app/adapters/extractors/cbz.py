"""CBZ extractor. Pages are read in memory; nothing is ever extracted to disk.

ComicInfo.xml is intentionally ignored (no defusedxml available; see report).
"""

import re
import stat as stat_mod
import zipfile
import zlib
from collections.abc import Iterator
from contextlib import contextmanager

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
from app.domain.errors import (
    ArchiveLimitExceeded,
    CorruptArchive,
    PageOutOfRange,
    UnsafePath,
    UnsupportedFormat,
)
from app.domain.item import ItemType
from app.domain.library import ExtractorLimits, ItemMetadata, Page, natural_key
from app.ports.storage import StorageBackend, StorageEntry

# Compression ratio only matters for entries big enough to be a bomb; tiny ones are
# bounded by max_total_uncompressed_bytes anyway.
RATIO_MIN_BYTES = 64 * 1024

_DRIVE = re.compile(r"^[A-Za-z]:")


def _check_member_name(name: str) -> None:
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or name.startswith("/")
        or _DRIVE.match(name)
        or ".." in name.split("/")
    ):
        raise UnsafePath


class CbzExtractor:
    format = "cbz"
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
        # Validated page index per (rel_path, size, mtime_ns): a page request must not reopen
        # every entry of the archive (FIND-2026-003). Items are (position in infolist, media type).
        self._index: PageIndexCache[tuple[int, str]] = PageIndexCache(index_cache_size)
        self._gate = gate or default_read_gate()

    @property
    def cached_archives(self) -> int:
        return len(self._index)

    def can_handle(self, entry: StorageEntry) -> bool:
        return not entry.is_dir and entry.rel_path.lower().endswith(".cbz")

    @contextmanager
    def _open(self, rel_path: str, *, validate: bool = True) -> Iterator[zipfile.ZipFile]:
        fh = self._storage.open(rel_path)
        try:
            try:
                zf = zipfile.ZipFile(fh)
            except (zipfile.BadZipFile, EOFError, OSError, ValueError) as exc:
                raise CorruptArchive from exc
            try:
                if validate:
                    self._validate(zf)
                yield zf
            except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError) as exc:
                raise CorruptArchive from exc
            except RuntimeError as exc:  # zipfile signals encrypted/unsupported with this
                raise UnsupportedFormat from exc
            finally:
                zf.close()
        finally:
            fh.close()

    def _validate(self, zf: zipfile.ZipFile) -> None:
        infos = zf.infolist()
        limits = self._limits
        if len(infos) > limits.max_entries:
            raise ArchiveLimitExceeded
        total = 0
        for info in infos:
            _check_member_name(info.filename)
            if info.flag_bits & 0x1:
                raise UnsupportedFormat  # encrypted
            if info.create_system == 3 and stat_mod.S_ISLNK(info.external_attr >> 16):
                raise UnsafePath  # symlink inside the archive
            if info.is_dir():
                continue
            if info.file_size > limits.max_page_bytes and has_image_extension(info.filename):
                raise ArchiveLimitExceeded
            total += info.file_size
            if total > limits.max_total_uncompressed_bytes:
                raise ArchiveLimitExceeded
            if info.file_size >= RATIO_MIN_BYTES and (
                info.compress_size == 0
                or info.file_size / info.compress_size > limits.max_compression_ratio
            ):
                raise ArchiveLimitExceeded

    def _build_index(self, zf: zipfile.ZipFile) -> tuple[tuple[int, str], ...]:
        """Sorted (position, media type) of every real image. Opens EVERY candidate: done once
        per file version, then served from the cache."""
        infos = zf.infolist()
        candidates = [
            pos for pos, i in enumerate(infos) if not i.is_dir() and has_image_extension(i.filename)
        ]
        candidates.sort(key=lambda pos: natural_key(infos[pos].filename))
        pages: list[tuple[int, str]] = []
        for pos in candidates:
            with zf.open(infos[pos]) as member:
                media_type = sniff_image(member.read(HEADER_BYTES))
            if media_type is not None:  # fake extensions (e.g. text named .jpg) are ignored
                pages.append((pos, media_type))
        return tuple(pages)

    def _key(self, rel_path: str) -> IndexKey:
        entry = self._storage.stat(rel_path)
        return (rel_path, entry.size, entry.mtime_ns)

    def inspect(self, rel_path: str) -> ItemMetadata:
        key = self._key(rel_path)
        with self._open(rel_path) as zf:
            pages = self._build_index(zf)
        if not pages:
            raise UnsupportedFormat
        self._index.put(key, pages)
        return ItemMetadata(page_count=len(pages))

    def read_page(self, rel_path: str, index: int) -> Page:
        key = self._key(rel_path)
        cached = self._index.get(key)
        # A cached index was fully validated for this exact file version (same size and mtime),
        # so the per-entry validation loop is skipped; the chosen entry is re-checked below.
        with self._open(rel_path, validate=cached is None) as zf:
            pages = cached if cached is not None else self._build_index(zf)
            if cached is None and pages:
                self._index.put(key, pages)
            if not 0 <= index < len(pages):
                raise PageOutOfRange
            position, media_type = pages[index]
            infos = zf.infolist()
            if position >= len(infos):
                raise CorruptArchive
            info = infos[position]
            limit = self._limits.max_page_bytes
            if info.file_size > limit:
                raise ArchiveLimitExceeded
            with self._gate.slot(), zf.open(info) as member:
                data = member.read(limit + 1)
        if len(data) > limit:
            raise ArchiveLimitExceeded
        return Page(data=data, media_type=media_type)

    def read_cover(self, rel_path: str) -> Page:
        return self.read_page(rel_path, 0)
