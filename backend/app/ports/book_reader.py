"""Book reader port: reads a book chapter by chapter. Separate from `Extractor` (which serves page
images): a book is structure (metadata, table of contents), sanitized HTML chapters and the images
those chapters use. Everything comes from memory; nothing is extracted to disk."""

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from app.domain.book import BookInfo
from app.domain.library import Page


@runtime_checkable
class BookReader(Protocol):
    format: str

    def read_book(self, rel_path: str) -> BookInfo:
        """Title, authors, chapters, table of contents. Raises domain errors."""
        ...

    def read_chapter(
        self,
        rel_path: str,
        index: int,
        *,
        theme: str,
        size: int,
        resource_url: Callable[[int], str],
    ) -> str:
        """Chapter `index` (0-based) as a complete, SANITIZED HTML document for a sandboxed frame.
        `resource_url(rid)` gives the public URL written for each image. Raises PageOutOfRange or
        domain errors."""
        ...

    def read_resource(self, rel_path: str, rid: int) -> Page:
        """An image of the book by its opaque server-made id. Raises PageOutOfRange or domain
        errors."""
        ...
