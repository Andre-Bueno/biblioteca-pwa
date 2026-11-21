"""Port for a public metadata source (interface only)."""

from collections.abc import Sequence
from typing import Protocol

from app.domain.metadata import MetadataCandidate


class MetadataProvider(Protocol):
    """A public source of series metadata. Only the cleaned series title is ever sent.

    Raises `ExternalFetchError` when the source cannot be used; never anything else.
    """

    name: str  # stable id stored in `series.metadata_source` ("mangadex", "anilist", ...)
    # True for sources that only give a description (no cover, no work identity): they are used
    # with a STRONG match only and never decide the title or the cover.
    description_only: bool

    def search(self, title: str, languages: Sequence[str]) -> list[MetadataCandidate]:
        """Candidates for a title, best first. Descriptions are limited to `languages`."""
        ...

    def get(self, external_id: str, languages: Sequence[str]) -> MetadataCandidate | None:
        """One candidate by the source's id; None when the id is malformed or unknown."""
        ...
