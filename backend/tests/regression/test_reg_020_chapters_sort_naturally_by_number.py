"""REG-020: chapters of a series must read 2 < 10 < 100, never as plain text order.

Bug (found with the real library, one folder of `Capitulo - N.cbz`, N from 0 to 300): the items
list is ordered by title text, so "Capitulo - 10" and "Capitulo - 100" came before "Capitulo - 2",
which is unusable for reading in order. Cause: no chapter number was ever extracted from the name.
Fix: the scan stores `chapter_number` and the series detail orders by number (no number last, then
natural name).
"""

from pathlib import Path

from app.adapters.extractors.registry import build_extractors
from app.adapters.storage.local import LocalStorage
from app.domain.library import ExtractorLimits
from app.domain.series import Series, chapter_title, sort_chapters
from app.services.scan import scan_library

from fakes import FakeItemRepository, FixedClock, make_cbz, png


class _MemorySeries:
    """Just enough of `SeriesRepository` for the scan."""

    def __init__(self) -> None:
        self.created: list[str] = []

    def ensure_for_folder(self, folder_rel_path: str, title: str) -> Series:
        if folder_rel_path not in self.created:
            self.created.append(folder_rel_path)
        now = FixedClock().now()
        return Series(
            id=f"series-{self.created.index(folder_rel_path)}",
            title=title,
            sort_title=title,
            folder_rel_path=folder_rel_path,
            created_at=now,
            updated_at=now,
        )


def test_reg_020_chapters_without_zero_padding_sort_by_number(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    (lib / "Series").mkdir(parents=True)
    for n in (100, 10, 2, 0, 1, 99, 20):
        (lib / "Series" / f"Capitulo - {n}.cbz").write_bytes(make_cbz({"1.png": png(n)}))
    storage = LocalStorage(lib)
    repo = FakeItemRepository()
    series = _MemorySeries()
    scan_library(
        storage,
        repo,
        build_extractors(storage, ExtractorLimits()),
        clock=FixedClock(),
        series=series,  # type: ignore[arg-type]
    )

    ordered = sort_chapters(list(repo.items.values()))
    assert [c.chapter_number for c in ordered] == [0.0, 1.0, 2.0, 10.0, 20.0, 99.0, 100.0]
    assert [c.title for c in ordered][:3] == ["Capitulo - 0", "Capitulo - 1", "Capitulo - 2"]
    assert chapter_title(ordered[-1].chapter_number, ordered[-1].title) == "Capitulo 100"
    assert {c.series_id for c in ordered} == {"series-0"}
    assert series.created == ["Series"]
