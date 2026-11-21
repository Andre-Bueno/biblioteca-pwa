"""Series repository port (interface only)."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.domain.item import Item
from app.domain.metadata import MetadataUpdate
from app.domain.series import Series, SeriesSummary


class SeriesRepository(Protocol):
    """Persistence of series. A series is visible only while it has at least one active
    (non-missing) chapter; the rows themselves are kept so metadata survives a missing library.

    Every user-specific figure (`read_chapters`, `last_item_id`) is scoped by the `user_id` given.
    """

    def ensure_for_folder(self, folder_rel_path: str, title: str) -> Series:
        """The series of that library folder; created on first use, never duplicated."""
        ...

    def create_standalone(self, title: str) -> Series:
        """A new series without folder (a loose file in the library root)."""
        ...

    def get(self, series_id: str) -> Series | None:
        """The series, or None when unknown or without active chapters."""
        ...

    def list_summaries(
        self, user_id: str, query: str | None, offset: int, limit: int
    ) -> list[SeriesSummary]:
        """Page of visible series ordered by `sort_title` (then id); `query` is a literal."""
        ...

    def list_chapters(self, series_id: str) -> list[Item]:
        """Active chapters of a series, in no particular order (the service orders them)."""
        ...

    def list_for_enrichment(
        self, states: Sequence[str], not_found_before: datetime | None, limit: int
    ) -> list[Series]:
        """Visible series whose state is in `states`, never checked first, at most `limit`.
        A `not_found` series is returned only when never checked or checked before
        `not_found_before` (None = no age filter). The item format never matters; a series needs at
        least one active item."""
        ...

    def update_metadata(
        self, series_id: str, update: MetadataUpdate, allowed_states: Sequence[str]
    ) -> bool:
        """Write the metadata only while the CURRENT state is in `allowed_states` (one atomic
        statement). False when the series is unknown or its state is not allowed (e.g. `manual`
        wins over an automatic run that started earlier)."""
        ...
