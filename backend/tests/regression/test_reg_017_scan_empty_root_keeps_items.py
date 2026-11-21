"""REG-017 (FIND-2026-012): a scan of an empty/unreadable library marked every item as missing.

Bug: with LIBRARY_PATH empty (volume not mounted) the scan ended normally and
`remove_missing(set())` hid the whole catalog; a directory that could not be read during the walk
had the same effect on its items, and a `DataAccessError` on one item aborted the whole scan.
Fix: nothing is marked missing when the walk reported errors, when the walk found nothing but
items exist, or when a database error happened; a per-item `DataAccessError` is recorded like any
other per-file error.
"""

import os
from dataclasses import replace
from pathlib import Path

import pytest
from app.adapters.storage.local import LocalStorage
from app.domain.errors import DataAccessError, DomainError, LibraryUnavailable
from app.domain.item import Item, ItemType
from app.services.scan import scan_library

from fakes import FakeExtractor, FakeItemRepository, FakeStorage, FixedClock


def _item(rel: str) -> Item:
    return Item(
        id=f"id-{rel}",
        type=ItemType.MANGA,
        title=rel,
        rel_path=rel,
        format="fake",
        page_count=3,
        size=1,
        mtime_ns=1,
        added_at=FixedClock().now(),
    )


def _repo(*rels: str) -> FakeItemRepository:
    repo = FakeItemRepository()
    for rel in rels:
        repo.add(_item(rel))
    return repo


def test_empty_root_with_existing_items_does_not_mark_them_missing() -> None:
    repo = _repo("a.fake", "b.fake")
    report = scan_library(FakeStorage({}), repo, [FakeExtractor()], clock=FixedClock())
    assert report.removed == 0
    assert report.removal_skipped == "empty_library"
    assert all(not i.missing for i in repo.items.values())


def test_a_library_with_only_unsupported_files_is_treated_like_an_empty_one() -> None:
    repo = _repo("a.fake")
    storage = FakeStorage({"notes.txt": b"x"})
    report = scan_library(storage, repo, [FakeExtractor()], clock=FixedClock())
    assert report.removed == 0
    assert not repo.items["id-a.fake"].missing


def test_a_vanished_file_is_still_marked_missing_when_the_walk_is_healthy() -> None:
    repo = _repo("a.fake", "gone.fake")
    storage = FakeStorage({"a.fake": b"x"}, mtimes={"a.fake": 1})
    report = scan_library(storage, repo, [FakeExtractor()], clock=FixedClock())
    assert report.removed == 1
    assert repo.items["id-gone.fake"].missing
    assert report.removal_skipped is None


def test_empty_root_with_no_items_is_a_normal_empty_scan() -> None:
    report = scan_library(
        FakeStorage({}), FakeItemRepository(), [FakeExtractor()], clock=FixedClock()
    )
    assert report.removed == 0
    assert report.removal_skipped is None


def test_walk_errors_prevent_marking_anything_missing() -> None:
    class ErroringStorage(FakeStorage):
        walk_errors = 1

    repo = _repo("a.fake", "unreadable-dir/b.fake")
    storage = ErroringStorage({"a.fake": b"x"})
    report = scan_library(storage, repo, [FakeExtractor()], clock=FixedClock())
    assert report.removed == 0
    assert report.removal_skipped == "walk_errors"
    assert not repo.items["id-unreadable-dir/b.fake"].missing


def test_local_storage_reports_a_directory_it_could_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "1.fake").write_bytes(b"x")
    (tmp_path / "locked").mkdir()
    storage = LocalStorage(tmp_path)
    real_scandir = os.scandir

    def scandir(path: object = ".") -> object:
        if Path(str(path)).name == "locked":
            raise PermissionError
        return real_scandir(path)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "scandir", scandir)
    rels = {e.rel_path for e in storage.list_entries()}
    assert "ok/1.fake" in rels
    assert storage.walk_errors >= 1


def test_unreadable_library_root_is_an_error_not_an_empty_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalStorage(tmp_path)

    def scandir(path: object = ".") -> object:
        raise PermissionError

    monkeypatch.setattr(os, "scandir", scandir)
    with pytest.raises(LibraryUnavailable):
        list(storage.list_entries())


def test_database_error_on_one_item_does_not_abort_the_scan() -> None:
    class FlakyRepo(FakeItemRepository):
        def add(self, item: Item) -> None:
            if item.rel_path == "poison.fake":
                raise DataAccessError("database error")
            super().add(item)

    repo = FlakyRepo()
    storage = FakeStorage({"poison.fake": b"x", "good.fake": b"y"})
    report = scan_library(storage, repo, [FakeExtractor()], clock=FixedClock())
    assert report.added == 1
    assert [e.reason for e in report.errors] == ["DataAccessError"]
    assert "id-poison.fake" not in repo.items


def test_database_error_prevents_marking_items_missing() -> None:
    class FlakyRepo(FakeItemRepository):
        def update(self, item: Item) -> None:
            raise DataAccessError("database error")

    repo = FlakyRepo()
    repo.add(replace(_item("a.fake"), size=999))  # stale size => update attempted => error
    repo.add(_item("old.fake"))
    storage = FakeStorage({"a.fake": b"x"})
    report = scan_library(storage, repo, [FakeExtractor()], clock=FixedClock())
    assert report.removed == 0
    assert report.removal_skipped == "data_access_errors"


def test_data_access_error_is_a_domain_error() -> None:
    assert issubclass(DataAccessError, DomainError)
