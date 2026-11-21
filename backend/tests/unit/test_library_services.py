from datetime import UTC, datetime

import pytest
from app.domain.errors import ItemNotFound, PageOutOfRange, UnsupportedFormat
from app.domain.library import ScanProgress, natural_key, sanitize_title
from app.services.hashing import ensure_content_hash
from app.services.pages import get_cover, get_page
from app.services.scan import scan_library

from fakes import FakeExtractor, FakeItemRepository, FakeStorage, FixedClock

CLOCK = FixedClock()


def test_natural_key_orders_numbers_numerically() -> None:
    names = ["p10.png", "p2.png", "P1.png", "p1" + "9" * 5000 + ".png"]
    assert sorted(names, key=natural_key)[:3] == ["P1.png", "p2.png", "p10.png"]


def test_sanitize_title_strips_controls_and_markup() -> None:
    assert sanitize_title("a\x00b‮<script>  x") == "a b script x"
    assert sanitize_title("\x00\x01") == "Untitled"
    assert len(sanitize_title("x" * 1000)) == 200


def _setup(files: dict[str, bytes]) -> tuple[FakeStorage, FakeItemRepository, FakeExtractor]:
    return FakeStorage(files), FakeItemRepository(), FakeExtractor()


def test_scan_adds_items_and_skips_unknown() -> None:
    storage, repo, ext = _setup({"a.fake": b"1", "notes.txt": b"x", "sub/b.fake": b"22"})
    report = scan_library(storage, repo, [ext], clock=CLOCK)
    assert (report.added, report.skipped, report.errors) == (2, 1, [])
    item = repo.get_by_rel_path("sub/b.fake")
    assert item is not None
    assert item.title == "b"
    assert item.page_count == 3
    assert item.id != item.rel_path


def test_scan_is_incremental() -> None:
    storage, repo, ext = _setup({"a.fake": b"1"})
    scan_library(storage, repo, [ext], clock=CLOCK)
    second = scan_library(storage, repo, [ext], clock=CLOCK)
    assert (second.added, second.unchanged) == (0, 1)
    assert ext.inspected == ["a.fake"]  # not re-inspected

    storage.files["a.fake"] = b"changed"
    third = scan_library(storage, repo, [ext], clock=CLOCK)
    assert third.updated == 1
    assert len(repo.items) == 1


def test_scan_update_keeps_id_and_resets_hash() -> None:
    storage, repo, ext = _setup({"a.fake": b"1"})
    scan_library(storage, repo, [ext], clock=CLOCK)
    item = repo.get_by_rel_path("a.fake")
    assert item is not None
    hashed = ensure_content_hash(storage, repo, item.id)
    assert hashed.content_hash is not None
    storage.mtimes["a.fake"] = 99
    scan_library(storage, repo, [ext], clock=CLOCK)
    after = repo.get(item.id)
    assert after is not None
    assert after.content_hash is None


def test_scan_removes_missing_items() -> None:
    storage, repo, ext = _setup({"a.fake": b"1", "b.fake": b"2"})
    scan_library(storage, repo, [ext], clock=CLOCK)
    del storage.files["b.fake"]
    report = scan_library(storage, repo, [ext], clock=CLOCK)
    assert report.removed == 1
    gone = repo.get_by_rel_path("b.fake")
    assert gone is not None
    assert gone.missing
    assert repo.get(gone.id) is None  # hidden from readers
    assert [i.rel_path for i in repo.list(0, 10)] == ["a.fake"]

    # The file comes back: the same item (same id) is revived, not duplicated.
    storage.files["b.fake"] = b"2"
    again = scan_library(storage, repo, [ext], clock=CLOCK)
    assert (again.updated, again.added, again.removed) == (1, 0, 0)
    revived = repo.get(gone.id)
    assert revived is not None
    assert not revived.missing


def test_scan_uses_the_injected_clock_for_added_at() -> None:
    storage, repo, ext = _setup({"a.fake": b"1"})
    moment = datetime(2030, 5, 6, 7, 8, 9, tzinfo=UTC)
    scan_library(storage, repo, [ext], clock=FixedClock(moment))
    item = repo.get_by_rel_path("a.fake")
    assert item is not None
    assert item.added_at == moment


def test_scan_error_in_one_file_does_not_abort_and_keeps_record() -> None:
    storage, repo, ext = _setup({"a.fake": b"1", "bad.fake": b"2", "c.fake": b"3"})
    report = scan_library(storage, repo, [ext], clock=CLOCK)
    assert report.added == 2
    assert [(e.rel_path, e.reason) for e in report.errors] == [("bad.fake", "CorruptArchive")]


def test_scan_failing_file_is_not_removed_from_repo() -> None:
    storage, repo, ext = _setup({"a.fake": b"1"})
    scan_library(storage, repo, [ext], clock=CLOCK)
    storage.files["a.fake"] = b"now-bad-size"
    ext.inspect = lambda rel: (_ for _ in ()).throw(OSError)  # type: ignore[method-assign,assignment]
    report = scan_library(storage, repo, [ext], clock=CLOCK)
    assert report.removed == 0
    assert report.errors[0].reason == "OSError"
    assert repo.get_by_rel_path("a.fake") is not None


def test_scan_reports_progress() -> None:
    storage, repo, ext = _setup({"a.fake": b"1", "b.fake": b"2", "c.fake": b"3"})
    seen: list[ScanProgress] = []
    scan_library(storage, repo, [ext], clock=CLOCK, progress=seen.append)
    assert [p.processed for p in seen] == [1, 2, 3]
    assert seen[-1].total == 3


def test_get_page_and_cover() -> None:
    storage, repo, ext = _setup({"a.fake": b"1"})
    scan_library(storage, repo, [ext], clock=CLOCK)
    item = repo.get_by_rel_path("a.fake")
    assert item is not None
    assert get_page(repo, [ext], item.id, 2).data == b"a.fake#2"
    assert get_cover(repo, [ext], item.id).data == b"a.fake#0"


@pytest.mark.parametrize("index", [-1, 3, 10**9, True])
def test_get_page_validates_index(index: int) -> None:
    storage, repo, ext = _setup({"a.fake": b"1"})
    scan_library(storage, repo, [ext], clock=CLOCK)
    item = repo.get_by_rel_path("a.fake")
    assert item is not None
    with pytest.raises(PageOutOfRange):
        get_page(repo, [ext], item.id, index)


def test_get_page_unknown_item_and_format() -> None:
    storage, repo, ext = _setup({"a.fake": b"1"})
    scan_library(storage, repo, [ext], clock=CLOCK)
    with pytest.raises(ItemNotFound):
        get_page(repo, [ext], "nope", 0)
    item = repo.get_by_rel_path("a.fake")
    assert item is not None
    with pytest.raises(UnsupportedFormat):
        get_page(repo, [], item.id, 0)


def test_content_hash_is_computed_once_and_persisted() -> None:
    storage, repo, ext = _setup({"a.fake": b"hello"})
    scan_library(storage, repo, [ext], clock=CLOCK)
    item = repo.get_by_rel_path("a.fake")
    assert item is not None
    first = ensure_content_hash(storage, repo, item.id)
    assert first.content_hash == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
    assert repo.get(item.id) == first
    with pytest.raises(ItemNotFound):
        ensure_content_hash(storage, repo, "nope")
