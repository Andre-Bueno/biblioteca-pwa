"""Use case: scan the library and sync items (incremental)."""

import posixpath
import uuid
from collections.abc import Callable, Sequence
from dataclasses import replace

from app.domain.errors import DataAccessError, DomainError
from app.domain.item import Item
from app.domain.library import ScanError, ScanProgress, ScanReport, sanitize_title
from app.domain.series import Grouping, group_entry
from app.ports.clock import Clock
from app.ports.extractor import Extractor
from app.ports.item_repository import ItemRepository
from app.ports.series_repository import SeriesRepository
from app.ports.storage import StorageBackend, StorageEntry

ProgressCallback = Callable[[ScanProgress], None]


def _find_extractor(extractors: Sequence[Extractor], entry: StorageEntry) -> Extractor | None:
    for extractor in extractors:
        try:
            if extractor.can_handle(entry):
                return extractor
        except DomainError:
            continue
    return None


def _title_from(rel_path: str, is_dir: bool) -> str:
    name = posixpath.basename(rel_path)
    if not is_dir:
        name = posixpath.splitext(name)[0]
    return sanitize_title(name)


class _SeriesLinker:
    """Decides the series and chapter number of each entry (cached per folder for one scan).

    With no series repository (tests of the plain scan) items are left ungrouped.
    """

    def __init__(self, series: SeriesRepository | None) -> None:
        self._series = series
        self._by_folder: dict[str, str] = {}

    def resolve(
        self, entry: StorageEntry, existing: Item | None
    ) -> tuple[str | None, float | None]:
        """`(series_id, chapter_number)` for the entry; creates the series when it is new."""
        if self._series is None:
            return None, None
        group: Grouping = group_entry(entry.rel_path, entry.is_dir)
        if group.folder_rel_path is None:
            if existing is not None and existing.series_id is not None:
                return existing.series_id, group.chapter_number
            return self._series.create_standalone(group.series_title).id, group.chapter_number
        series_id = self._by_folder.get(group.folder_rel_path)
        if series_id is None:
            series_id = self._series.ensure_for_folder(group.folder_rel_path, group.series_title).id
            self._by_folder[group.folder_rel_path] = series_id
        return series_id, group.chapter_number


def scan_library(
    storage: StorageBackend,
    repo: ItemRepository,
    extractors: Sequence[Extractor],
    *,
    clock: Clock,
    progress: ProgressCallback | None = None,
    series: SeriesRepository | None = None,
) -> ScanReport:
    """Walk the storage, add/update items by size+mtime, remove vanished ones.

    With `series`, every item is also (re)grouped into its series and gets its chapter number;
    this is incremental and idempotent: an unchanged file is only rewritten when its series or
    number differ from what the rules say now (`report.regrouped`).

    A failure on one file (including a database error on that item) is recorded in the report and
    never aborts the scan. Nothing is marked missing if the walk
    reported unreadable directories, if a database error happened, or if nothing was found while
    items exist (an unmounted/empty library must not hide the whole catalog); the reason is kept
    in `report.removal_skipped`. An unreadable library root raises `LibraryUnavailable`.
    """
    report = ScanReport()
    entries = list(storage.list_entries())
    walk_errors = storage.walk_errors
    total = len(entries)
    present: set[str] = set()
    linker = _SeriesLinker(series)

    for done, entry in enumerate(entries, start=1):
        extractor = _find_extractor(extractors, entry)
        if extractor is None:
            report.skipped += 1
        else:
            present.add(entry.rel_path)
            try:
                _sync_entry(repo, extractor, entry, report, clock, linker)
            except DomainError as exc:
                report.errors.append(ScanError(entry.rel_path, type(exc).__name__))
            except OSError:
                report.errors.append(ScanError(entry.rel_path, "OSError"))
        if progress is not None:
            progress(ScanProgress(processed=done, total=total))

    report.removal_skipped = _removal_skip_reason(repo, present, report, walk_errors)
    if report.removal_skipped is None:
        report.removed = repo.remove_missing(present)
    return report


def _removal_skip_reason(
    repo: ItemRepository, present: set[str], report: ScanReport, walk_errors: int
) -> str | None:
    if walk_errors > 0:
        return "walk_errors"
    if any(error.reason == DataAccessError.__name__ for error in report.errors):
        return "data_access_errors"
    if not present and repo.list(0, 1):
        return "empty_library"
    return None


def _sync_entry(
    repo: ItemRepository,
    extractor: Extractor,
    entry: StorageEntry,
    report: ScanReport,
    clock: Clock,
    linker: _SeriesLinker,
) -> None:
    existing = repo.get_by_rel_path(entry.rel_path)
    if (
        existing is not None
        and existing.format == extractor.format
        and existing.size == entry.size
        and existing.mtime_ns == entry.mtime_ns
        and not existing.missing
    ):
        report.unchanged += 1
        series_id, number = linker.resolve(entry, existing)
        if series_id is not None and (
            existing.series_id != series_id or existing.chapter_number != number
        ):
            repo.update(replace(existing, series_id=series_id, chapter_number=number))
            report.regrouped += 1
        return

    meta = extractor.inspect(entry.rel_path)
    series_id, number = linker.resolve(entry, existing)
    if existing is None:
        repo.add(
            Item(
                id=str(uuid.uuid4()),
                type=extractor.item_type,
                title=meta.title or _title_from(entry.rel_path, entry.is_dir),
                rel_path=entry.rel_path,
                format=extractor.format,
                page_count=meta.page_count,
                size=entry.size,
                mtime_ns=entry.mtime_ns,
                added_at=clock.now(),
                series_id=series_id,
                chapter_number=number,
            )
        )
        report.added += 1
    else:
        repo.update(
            replace(
                existing,
                type=extractor.item_type,
                title=meta.title or existing.title,  # a book keeps the title from its metadata
                format=extractor.format,
                page_count=meta.page_count,
                size=entry.size,
                mtime_ns=entry.mtime_ns,
                content_hash=None,
                missing=False,
                series_id=series_id,
                chapter_number=number,
            )
        )
        report.updated += 1
