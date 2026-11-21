"""Storage port: access to the library files by library-relative path."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class StorageEntry:
    """A file or directory in the library.

    `rel_path` is POSIX-style and relative to the library root. For directories,
    `size` is the sum of direct child file sizes and `mtime_ns` the newest mtime
    among the directory and its direct files (enough to detect changes).
    """

    rel_path: str
    is_dir: bool
    size: int
    mtime_ns: int


class StorageBackend(Protocol):
    @property
    def walk_errors(self) -> int:
        """Directories/entries that could not be read during the most recent `list_entries`
        walk (0 = the listing is complete). Valid once the iterator has been exhausted."""
        ...

    def list_entries(self) -> Iterator[StorageEntry]:
        """Walk the whole library (files and directories); never follows links.

        Raises `LibraryUnavailable` when the root itself cannot be read (it is never reported as
        an empty library); unreadable sub-directories are skipped and counted in `walk_errors`.
        """
        ...

    def list_children(self, rel_path: str) -> list[StorageEntry]:
        """Direct children of a directory."""
        ...

    def stat(self, rel_path: str) -> StorageEntry: ...

    def open(self, rel_path: str) -> BinaryIO:
        """Open a regular file for binary reading. Caller closes it."""
        ...
