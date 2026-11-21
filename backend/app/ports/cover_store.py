"""Port for the downloaded series covers (interface only)."""

from typing import Protocol

from app.domain.library import Page
from app.domain.metadata import FetchedImage, StagedCover


class CoverStore(Protocol):
    """Covers live in one folder; the file name comes only from the series UUID and a fixed
    extension, never from the network. A write is two steps (`stage` then `commit`) so the caller
    can persist the database change in between and `discard` when it is refused."""

    def stage(self, series_id: str, image: FetchedImage) -> StagedCover:
        """Write the image to a temporary file (size-checked). Nothing is visible yet."""
        ...

    def commit(self, staged: StagedCover) -> None:
        """Atomically move the staged file to its final name."""
        ...

    def discard(self, staged: StagedCover) -> None:
        """Drop a staged file (idempotent)."""
        ...

    def read(self, rel_path: str) -> Page | None:
        """The stored cover, or None when missing, unsafe or not an image."""
        ...

    def delete(self, rel_path: str) -> None:
        """Remove a stored cover (idempotent; an unsafe name is ignored)."""
        ...
