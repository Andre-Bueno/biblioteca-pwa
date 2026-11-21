"""In-memory fakes and fixture builders shared by tests (no real content)."""

import builtins
import io
import zipfile
from collections.abc import Collection, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from app.domain.errors import CorruptArchive, PageOutOfRange
from app.domain.item import Item, ItemType
from app.domain.library import ItemMetadata, Page
from app.ports.storage import StorageEntry

PNG_HEAD = b"\x89PNG\r\n\x1a\n"


def png(seed: int = 0, size: int = 64) -> bytes:
    """Bytes that look like a PNG to magic-byte validation (not a decodable image)."""
    return PNG_HEAD + bytes((seed + i) % 251 for i in range(size))


def make_cbz(members: dict[str, bytes], *, compress: bool = True) -> bytes:
    buf = io.BytesIO()
    method = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(buf, "w", method) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


class FixedClock:
    """A clock that always returns the same instant."""

    def __init__(self, at: datetime = datetime(2026, 1, 1, tzinfo=UTC)) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at


class FakeItemRepository:
    """Mirrors the SQL repository: missing items are hidden from get/list/search."""

    def __init__(self) -> None:
        self.items: dict[str, Item] = {}

    def add(self, item: Item) -> None:
        self.items[item.id] = item

    def update(self, item: Item) -> None:
        self.items[item.id] = item

    def get(self, item_id: str) -> Item | None:
        item = self.items.get(item_id)
        return None if item is None or item.missing else item

    def get_by_rel_path(self, rel_path: str) -> Item | None:
        return next((i for i in self.items.values() if i.rel_path == rel_path), None)

    def _visible(self, item_type: ItemType | None) -> builtins.list[Item]:
        return sorted(
            (i for i in self.items.values() if not i.missing and item_type in (None, i.type)),
            key=lambda i: (i.title.lower(), i.id),
        )

    def list(
        self, offset: int, limit: int, item_type: ItemType | None = None
    ) -> builtins.list[Item]:
        return self._visible(item_type)[offset : offset + limit]

    def search(
        self, query: str, offset: int, limit: int, item_type: ItemType | None = None
    ) -> builtins.list[Item]:
        found = [i for i in self._visible(item_type) if query.lower() in i.title.lower()]
        return found[offset : offset + limit]

    def remove_missing(self, present_rel_paths: Collection[str]) -> int:
        gone = [
            k
            for k, i in self.items.items()
            if not i.missing and i.rel_path not in present_rel_paths
        ]
        for key in gone:
            self.items[key] = replace(self.items[key], missing=True)
        return len(gone)


class FakeStorage:
    """Files: rel_path -> bytes. Directories are implied by file paths."""

    walk_errors = 0  # a complete listing; tests simulate an incomplete walk by overriding it

    def __init__(self, files: dict[str, bytes], mtimes: dict[str, int] | None = None) -> None:
        self.files = files
        self.mtimes = mtimes or {}

    def _file(self, rel: str) -> StorageEntry:
        return StorageEntry(rel, False, len(self.files[rel]), self.mtimes.get(rel, 1))

    def list_entries(self) -> Iterator[StorageEntry]:
        for rel in sorted(self.files):
            yield self._file(rel)

    def list_children(self, rel_path: str) -> list[StorageEntry]:
        prefix = rel_path.rstrip("/") + "/"
        return [self._file(r) for r in sorted(self.files) if r.startswith(prefix)]

    def stat(self, rel_path: str) -> StorageEntry:
        if rel_path in self.files:
            return self._file(rel_path)
        return StorageEntry(rel_path, True, 0, 1)

    def open(self, rel_path: str) -> BinaryIO:
        return io.BytesIO(self.files[rel_path])


class FakeExtractor:
    """Handles '*.fake' files. Files whose name contains 'bad' are corrupt."""

    format = "fake"
    item_type = ItemType.MANGA

    def __init__(self, pages: int = 3) -> None:
        self.pages = pages
        self.inspected: list[str] = []

    def can_handle(self, entry: StorageEntry) -> bool:
        return not entry.is_dir and entry.rel_path.endswith(".fake")

    def inspect(self, rel_path: str) -> ItemMetadata:
        self.inspected.append(rel_path)
        if "bad" in rel_path:
            raise CorruptArchive
        return ItemMetadata(page_count=self.pages)

    def read_page(self, rel_path: str, index: int) -> Page:
        if not 0 <= index < self.pages:
            raise PageOutOfRange
        return Page(data=f"{rel_path}#{index}".encode(), media_type="image/png")

    def read_cover(self, rel_path: str) -> Page:
        return self.read_page(rel_path, 0)


def make_library(root: Path) -> Path:
    """A small real library under `root/lib`: a folder manga, a CBZ, a corrupt CBZ, a stray file."""
    lib = root / "lib"
    (lib / "Folder Manga").mkdir(parents=True)
    (lib / "Folder Manga" / "2.png").write_bytes(png(2))
    (lib / "Folder Manga" / "1.png").write_bytes(png(1))
    (lib / "Vol 1.cbz").write_bytes(make_cbz({"1.png": png(1), "2.png": png(2), "3.png": png(3)}))
    (lib / "broken-secret-name.cbz").write_bytes(b"garbage")
    (lib / "notes.txt").write_bytes(b"ignore me")
    return lib
