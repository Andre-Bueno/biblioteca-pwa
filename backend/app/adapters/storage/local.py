"""Local-disk storage. The ONLY place that turns a relative path into a filesystem path.

Guarantees: nothing outside the library root is ever opened; symlinks and junctions are
never followed (real link detection, not the raw Windows ReparsePoint attribute, which
also appears on ordinary OneDrive folders).
"""

import os
import re
import stat as stat_mod
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from app.domain.errors import LibraryUnavailable, UnsafePath
from app.ports.storage import StorageEntry

MAX_PATH_LENGTH = 1024
MAX_DEPTH = 16

_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_BAD_CHARS = re.compile(r'[\x00-\x1f<>:"|?*\\]')


def _is_link(path: Path) -> bool:
    """True for symlinks and (on Windows) directory junctions. Never trusts raw attributes."""
    return path.is_symlink() or path.is_junction()


def _bad_name(name: str) -> bool:
    if name in ("", ".", "..") or _BAD_CHARS.search(name):
        return True
    if name.endswith((".", " ")):
        return True
    return name.split(".", 1)[0].rstrip(" ").upper() in _RESERVED


class LocalStorage:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        resolved = Path(root).resolve(strict=True)
        if not resolved.is_dir():
            raise NotADirectoryError("library root is not a directory")
        self._root = resolved
        self._walk_errors = 0

    # -- path resolution -------------------------------------------------

    def _resolve(self, rel_path: str) -> Path:
        if (
            not isinstance(rel_path, str)
            or not rel_path
            or len(rel_path) > MAX_PATH_LENGTH
            or rel_path.startswith("/")
        ):
            raise UnsafePath
        parts = rel_path.split("/")
        if len(parts) > MAX_DEPTH + 1 or any(_bad_name(p) for p in parts):
            raise UnsafePath

        current = self._root
        for part in parts:
            current = current / part
            if _is_link(current):
                raise UnsafePath
        try:
            resolved = current.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise FileNotFoundError("not found") from exc
        if not resolved.is_relative_to(self._root):
            raise UnsafePath
        return resolved

    def _rel(self, path: Path) -> str:
        return path.relative_to(self._root).as_posix()

    # -- port ------------------------------------------------------------

    def stat(self, rel_path: str) -> StorageEntry:
        path = self._resolve(rel_path)
        return self._entry(path, rel_path)

    def open(self, rel_path: str) -> BinaryIO:
        path = self._resolve(rel_path)
        if not path.is_file():
            raise UnsafePath
        return path.open("rb")

    def list_children(self, rel_path: str) -> list[StorageEntry]:
        path = self._resolve(rel_path)
        if not path.is_dir():
            raise NotADirectoryError("not a directory")
        return [e for e, _ in self._scan_dir(path)]

    @property
    def walk_errors(self) -> int:
        return self._walk_errors

    def list_entries(self) -> Iterator[StorageEntry]:
        self._walk_errors = 0
        stack: list[tuple[Path, int]] = [(self._root, 0)]
        while stack:
            directory, depth = stack.pop()
            try:
                children = self._scan_dir(directory, count_errors=True)
            except OSError:
                if directory == self._root:
                    raise LibraryUnavailable("library folder is not available") from None
                self._walk_errors += 1
                continue
            for entry, child_path in sorted(children, key=lambda c: c[0].rel_path):
                yield entry
                if entry.is_dir and depth + 1 < MAX_DEPTH:
                    stack.append((child_path, depth + 1))

    # -- helpers ---------------------------------------------------------

    def _entry(self, path: Path, rel_path: str) -> StorageEntry:
        st = path.stat()
        if stat_mod.S_ISDIR(st.st_mode):
            size, mtime = 0, st.st_mtime_ns
            with os.scandir(path) as it:
                for child in it:
                    if _bad_name(child.name) or child.is_symlink() or child.is_junction():
                        continue
                    if child.is_file(follow_symlinks=False):
                        cst = child.stat(follow_symlinks=False)
                        size += cst.st_size
                        mtime = max(mtime, cst.st_mtime_ns)
            return StorageEntry(rel_path, True, size, mtime)
        return StorageEntry(rel_path, False, st.st_size, st.st_mtime_ns)

    def _scan_dir(
        self, directory: Path, *, count_errors: bool = False
    ) -> list[tuple[StorageEntry, Path]]:
        """Safe direct children of `directory` (links, hidden and odd names are skipped).

        An entry that cannot be read is skipped; during a library walk it is counted in
        `walk_errors` so the scan knows the listing is incomplete."""
        result: list[tuple[StorageEntry, Path]] = []
        with os.scandir(directory) as it:
            names = [e for e in it]  # noqa: C416 - materialize before closing the iterator
        for child in names:
            if child.name.startswith(".") or _bad_name(child.name):
                continue
            if child.is_symlink() or child.is_junction():
                continue
            path = directory / child.name
            try:
                if child.is_dir(follow_symlinks=False):
                    rel = self._rel(path)
                    result.append((self._entry(path, rel), path))
                elif child.is_file(follow_symlinks=False):
                    st = child.stat(follow_symlinks=False)
                    result.append(
                        (StorageEntry(self._rel(path), False, st.st_size, st.st_mtime_ns), path)
                    )
            except OSError:
                if count_errors:
                    self._walk_errors += 1
                continue
        return result
