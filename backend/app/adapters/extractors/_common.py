"""Helpers shared by extractors: image validation by magic bytes, bounded page-index cache."""

import posixpath
import threading
from collections import OrderedDict

from app.adapters.gate import BoundedGate

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
