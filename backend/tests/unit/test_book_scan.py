"""The scan uses the title found inside a book (OPF) and falls back to the file name."""

from app.domain.item import ItemType
from app.domain.library import ItemMetadata, Page
from app.ports.storage import StorageEntry
from app.services.scan import scan_library

from fakes import FakeItemRepository, FakeStorage, FixedClock


class TitledExtractor:
    format = "titled"
    item_type = ItemType.BOOK

    def __init__(self) -> None:
        self.title: str | None = "Inner Title"

    def can_handle(self, entry: StorageEntry) -> bool:
        return not entry.is_dir and entry.rel_path.endswith(".tbook")

    def inspect(self, rel_path: str) -> ItemMetadata:
        return ItemMetadata(page_count=4, title=self.title, authors=("A",))

    def read_page(self, rel_path: str, index: int) -> Page:
        raise NotImplementedError

    def read_cover(self, rel_path: str) -> Page:
        raise NotImplementedError


def test_new_book_takes_the_title_from_its_metadata() -> None:
    repo, extractor = FakeItemRepository(), TitledExtractor()
    storage = FakeStorage({"shelf/file-name.tbook": b"x"})
    scan_library(storage, repo, [extractor], clock=FixedClock())
    item = repo.get_by_rel_path("shelf/file-name.tbook")
    assert item is not None
    assert (item.title, item.type, item.page_count) == ("Inner Title", ItemType.BOOK, 4)


def test_book_without_a_title_uses_the_file_name() -> None:
    repo, extractor = FakeItemRepository(), TitledExtractor()
    extractor.title = None
    scan_library(FakeStorage({"file-name.tbook": b"x"}), repo, [extractor], clock=FixedClock())
    item = repo.get_by_rel_path("file-name.tbook")
    assert item is not None and item.title == "file-name"


def test_changed_book_gets_the_new_title_and_unchanged_one_is_not_reread() -> None:
    repo, extractor = FakeItemRepository(), TitledExtractor()
    storage = FakeStorage({"b.tbook": b"x"}, mtimes={"b.tbook": 1})
    scan_library(storage, repo, [extractor], clock=FixedClock())
    extractor.title = "Renamed Inside"
    report = scan_library(storage, repo, [extractor], clock=FixedClock())
    assert report.unchanged == 1
    assert repo.get_by_rel_path("b.tbook").title == "Inner Title"  # type: ignore[union-attr]
    storage.mtimes["b.tbook"] = 2
    report = scan_library(storage, repo, [extractor], clock=FixedClock())
    assert report.updated == 1
    assert repo.get_by_rel_path("b.tbook").title == "Renamed Inside"  # type: ignore[union-attr]
