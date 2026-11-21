"""Use cases: browse series (list, detail with the user's progress) and read a series cover.

Progress is always the one of the `user_id` given (from the token), never a client value.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.errors import DomainError, ItemNotFound, PageOutOfRange, ResourceBusy
from app.domain.item import Item
from app.domain.library import Page
from app.domain.progress import Progress
from app.domain.series import (
    ContinuePoint,
    Series,
    SeriesSummary,
    chapter_title,
    pick_continue,
    sort_chapters,
)
from app.ports.cover_store import CoverStore
from app.ports.extractor import Extractor
from app.ports.progress_repository import ProgressRepository
from app.ports.series_repository import SeriesRepository
from app.services.catalog import MAX_PAGE_SIZE

MAX_COVER_ATTEMPTS = 5  # chapters tried when the first ones cannot be read


@dataclass(frozen=True, slots=True)
class SeriesPage:
    items: list[SeriesSummary]
    has_more: bool
    limit: int  # effective (after the cap)
    offset: int


@dataclass(frozen=True, slots=True)
class ChapterView:
    item: Item
    title: str  # displayed title ("Capitulo 100" from the number, else the item title)
    progress: Progress | None


@dataclass(frozen=True, slots=True)
class SeriesDetail:
    series: Series
    chapters: list[ChapterView]
    continue_point: ContinuePoint | None


class SeriesService:
    def __init__(self, series: SeriesRepository, progress: ProgressRepository) -> None:
        self._series = series
        self._progress = progress

    def list_series(
        self, user_id: str, *, query: str | None, offset: int, limit: int
    ) -> SeriesPage:
        """One page of series. `limit` is capped at MAX_PAGE_SIZE no matter what is asked."""
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)
        needle = (query or "").strip() or None
        rows = self._series.list_summaries(user_id, needle, offset, limit + 1)
        return SeriesPage(
            items=rows[:limit], has_more=len(rows) > limit, limit=limit, offset=offset
        )

    def get_series(self, user_id: str, series_id: str) -> SeriesDetail:
        """Raises ItemNotFound for an unknown series or one without active chapters."""
        series = self._series.get(series_id)
        if series is None:
            raise ItemNotFound
        chapters = sort_chapters(self._series.list_chapters(series_id))
        progress = self._progress.list_for_items(user_id, [c.id for c in chapters])
        return SeriesDetail(
            series=series,
            chapters=[
                ChapterView(c, chapter_title(c.chapter_number, c.title), progress.get(c.id))
                for c in chapters
            ],
            continue_point=pick_continue(chapters, progress),
        )


def get_series_cover(
    series_repo: SeriesRepository,
    extractors: Sequence[Extractor],
    series_id: str,
    covers: CoverStore | None = None,
) -> Page:
    """The downloaded cover when there is a readable one, else the cover of the first readable
    active chapter (in reading order).

    Raises ItemNotFound (unknown series) or PageOutOfRange (no chapter has a readable cover).
    A busy reader is not swallowed: it is reported so the client retries.
    """
    series = series_repo.get(series_id)
    if series is None:
        raise ItemNotFound
    if covers is not None and series.cover_path is not None:
        stored = covers.read(series.cover_path)
        if stored is not None:
            return stored
    chapters = sort_chapters(series_repo.list_chapters(series_id))
    tried = 0
    for chapter in chapters:
        if not chapter.has_cover:
            continue
        if tried == MAX_COVER_ATTEMPTS:
            break
        tried += 1
        extractor = next((e for e in extractors if e.format == chapter.format), None)
        if extractor is None:
            continue
        try:
            return extractor.read_cover(chapter.rel_path)
        except ResourceBusy:
            raise
        except (DomainError, OSError):
            continue
    raise PageOutOfRange
