"""Helpers shared by extractors: image validation by magic bytes, bounded page-index cache."""

import posixpath
import re
import stat as stat_mod
import threading
import zipfile
import zlib
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from app.adapters.gate import BoundedGate
from app.domain.errors import ArchiveLimitExceeded, CorruptArchive, UnsafePath, UnsupportedFormat
from app.domain.library import ExtractorLimits
from app.ports.storage import StorageBackend

# Compression ratio only matters for entries big enough to be a bomb; tiny ones are
# bounded by max_total_uncompressed_bytes anyway.
RATIO_MIN_BYTES = 64 * 1024

_DRIVE = re.compile(r"^[A-Za-z]:")

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"})
HEADER_BYTES = 32

# Page bodies are read fully into memory (up to `max_page_bytes`): at most this many at once, and
# at most this many more waiting for a short time. Anything beyond fails fast with ResourceBusy.
PAGE_READ_SLOTS = 4
PAGE_READ_MAX_WAITING = 16
PAGE_READ_WAIT_SECONDS = 2.0
# Archives/folders whose page index is kept in memory (least recently used are dropped).
INDEX_CACHE_SIZE = 64

IndexKey = tuple[str, int, int]  # (rel_path, size, mtime_ns): any change to the file misses


def default_read_gate() -> BoundedGate:
    return BoundedGate(
        slots=PAGE_READ_SLOTS, max_waiting=PAGE_READ_MAX_WAITING, timeout=PAGE_READ_WAIT_SECONDS
    )


class PageIndexCache[T]:
    """Thread-safe LRU of validated page indexes keyed by (rel_path, size, mtime_ns).

    Building an index touches every entry of an archive/folder; with the cache a page request
    only touches the page it needs. A changed file has another key, so a stale index is never
    served for it."""

    def __init__(self, max_entries: int = INDEX_CACHE_SIZE) -> None:
        self._max = max(1, max_entries)
        self._items: OrderedDict[IndexKey, tuple[T, ...]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: IndexKey) -> tuple[T, ...] | None:
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def put(self, key: IndexKey, value: tuple[T, ...]) -> None:
        with self._lock:
            # Drop older versions of the same file, then the least recently used overall.
            for stale in [k for k in self._items if k[0] == key[0] and k != key]:
                del self._items[stale]
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


def sniff_image(head: bytes) -> str | None:
    """Return the media type if `head` starts like jpeg/png/webp/gif/avif, else None."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and (
        b"avif" in head[8:HEADER_BYTES] or b"avis" in head[8:HEADER_BYTES]
    ):
        return "image/avif"
    return None


def has_image_extension(name: str) -> bool:
    return posixpath.splitext(name)[1].lower() in IMAGE_EXTENSIONS


@contextmanager
def open_zip(
    storage: StorageBackend, rel_path: str, validate: Callable[[zipfile.ZipFile], None]
) -> Iterator[zipfile.ZipFile]:
    """Open a library file as a validated zip. Library errors are mapped to domain errors; the
    file handle and the zip are always closed."""
    fh = storage.open(rel_path)
    try:
        try:
            zf = zipfile.ZipFile(fh)
        except (zipfile.BadZipFile, EOFError, OSError, ValueError) as exc:
            raise CorruptArchive from exc
        try:
            validate(zf)
            yield zf
        except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError) as exc:
            raise CorruptArchive from exc
        except RuntimeError as exc:  # zipfile signals encrypted/unsupported with this
            raise UnsupportedFormat from exc
        finally:
            zf.close()
    finally:
        fh.close()


def check_member_name(name: str) -> None:
    """Zip-slip guard for an archive member name (raises UnsafePath)."""
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or name.startswith("/")
        or _DRIVE.match(name)
        or ".." in name.split("/")
    ):
        raise UnsafePath


def validate_zip(
    zf: zipfile.ZipFile, limits: ExtractorLimits, *, size_limited: Callable[[str], bool]
) -> None:
    """Shared zip safety checks: entry count, names, encryption, symlinks, total size, ratio.

    A member for which `size_limited(name)` is true may not exceed `limits.max_page_bytes`.
    """
    infos = zf.infolist()
    if len(infos) > limits.max_entries:
        raise ArchiveLimitExceeded
    total = 0
    for info in infos:
        check_member_name(info.filename)
        if info.flag_bits & 0x1:
            raise UnsupportedFormat  # encrypted
        if info.create_system == 3 and stat_mod.S_ISLNK(info.external_attr >> 16):
            raise UnsafePath  # symlink inside the archive
        if info.is_dir():
            continue
        if info.file_size > limits.max_page_bytes and size_limited(info.filename):
            raise ArchiveLimitExceeded
        total += info.file_size
        if total > limits.max_total_uncompressed_bytes:
            raise ArchiveLimitExceeded
        if info.file_size >= RATIO_MIN_BYTES and (
            info.compress_size == 0
            or info.file_size / info.compress_size > limits.max_compression_ratio
        ):
            raise ArchiveLimitExceeded
