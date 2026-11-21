from pathlib import Path

from app.adapters.extractors.registry import build_extractors
from app.adapters.storage.local import LocalStorage
from app.domain.library import ExtractorLimits
from app.services.pages import get_cover, get_page
from app.services.scan import scan_library

from fakes import FakeItemRepository, FixedClock, make_cbz, png

CLOCK = FixedClock()


def test_scan_folder_and_cbz_end_to_end(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    (lib / "Folder Manga").mkdir(parents=True)
    (lib / "Folder Manga" / "2.png").write_bytes(png(2))
    (lib / "Folder Manga" / "1.png").write_bytes(png(1))
    (lib / "Vol 1.cbz").write_bytes(make_cbz({"1.png": png(1), "2.png": png(2), "3.png": png(3)}))
    (lib / "broken.cbz").write_bytes(b"garbage")
    (lib / "notes.txt").write_bytes(b"ignore me")

    storage = LocalStorage(lib)
    extractors = build_extractors(storage, ExtractorLimits())
    repo = FakeItemRepository()

    report = scan_library(storage, repo, extractors, clock=CLOCK)
    assert (report.added, report.unchanged) == (2, 0)
    assert [(e.rel_path, e.reason) for e in report.errors] == [("broken.cbz", "CorruptArchive")]

    cbz = repo.get_by_rel_path("Vol 1.cbz")
    folder = repo.get_by_rel_path("Folder Manga")
    assert cbz is not None
    assert folder is not None
    assert (cbz.title, cbz.page_count, cbz.format) == ("Vol 1", 3, "cbz")
    assert (folder.title, folder.page_count, folder.format) == ("Folder Manga", 2, "folder")
    assert get_page(repo, extractors, cbz.id, 2).data == png(3)
    assert get_cover(repo, extractors, folder.id).data == png(1)

    again = scan_library(storage, repo, extractors, clock=CLOCK)
    assert (again.added, again.unchanged) == (0, 2)

    (lib / "Vol 1.cbz").unlink()
    final = scan_library(storage, repo, extractors, clock=CLOCK)
    assert final.removed == 1
    gone = repo.get_by_rel_path("Vol 1.cbz")
    assert gone is not None
    assert gone.missing
