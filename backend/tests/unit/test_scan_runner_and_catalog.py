import logging
import threading
from collections.abc import Collection
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from app.domain.errors import DataAccessError, ItemNotFound, ScanAlreadyRunning
from app.domain.item import Item, ItemType
from app.domain.library import ScanError, ScanProgress, ScanReport
from app.services import catalog
from app.services.scan import ProgressCallback, scan_library
from app.services.scan_runner import ScanRunner, ScanState

from auth_fakes import DEFAULT_CONFIG, START, FakeClock, Rig
from fakes import FakeExtractor, FakeItemRepository, FakeStorage, FixedClock

# ---------------------------------------------------------------- scan runner


class BlockingJob:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.report = ScanReport(added=2, errors=[ScanError("secret/path.cbz", "CorruptArchive")])

    def __call__(self, progress: ProgressCallback) -> ScanReport:
        progress(ScanProgress(processed=1, total=4))
        self.started.set()
        assert self.release.wait(5)
        return self.report


def test_second_start_while_running_is_refused_then_allowed_again() -> None:
    job = BlockingJob()
    runner = ScanRunner(job, FakeClock())
    runner.start()
    assert job.started.wait(5)
    running = runner.status()
    assert (running.state, running.processed, running.total) == (ScanState.RUNNING, 1, 4)
    with pytest.raises(ScanAlreadyRunning):
        runner.start()
    with pytest.raises(ScanAlreadyRunning):
        runner.run()
    job.release.set()
    assert runner.wait(5)

    done = runner.status()
    assert done.state is ScanState.FINISHED
    assert (done.added, done.error_count, done.errors_by_reason) == (2, 1, {"CorruptArchive": 1})
    assert "secret" not in repr(done)  # the status never carries a path
    job.started.clear()
    runner.start()  # the lock was released
    assert runner.wait(5)


def test_failing_job_is_reported_generically_and_releases_the_lock() -> None:
    def boom(progress: ProgressCallback) -> ScanReport:
        raise RuntimeError("/etc/passwd leaked detail")

    runner = ScanRunner(boom, FakeClock())
    runner.start()
    assert runner.wait(5)
    status = runner.status()
    assert status.state is ScanState.FAILED
    assert "passwd" not in repr(status)
    runner.start()  # not stuck
    assert runner.wait(5)


def test_run_blocks_and_returns_the_final_status() -> None:
    runner = ScanRunner(lambda p: ScanReport(added=1, skipped=3), FakeClock())
    status = runner.run()
    assert (status.state, status.added, status.skipped) == (ScanState.FINISHED, 1, 3)
    assert status.started_at is not None
    assert status.finished_at is not None


def test_idle_status_before_any_scan() -> None:
    assert ScanRunner(lambda p: ScanReport(), FakeClock()).status().state is ScanState.IDLE


class _FlakyClock(FakeClock):
    """Raises on the n-th call to `now()` (1-based), works otherwise."""

    def __init__(self, fail_on: set[int]) -> None:
        super().__init__()
        self.calls = 0
        self._fail_on = fail_on

    def now(self) -> datetime:
        self.calls += 1
        if self.calls in self._fail_on:
            raise RuntimeError("clock down")
        return super().now()


def test_failure_to_start_the_thread_does_not_leave_the_scan_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = ScanRunner(lambda p: ScanReport(), FakeClock())

    def refuse(self: threading.Thread) -> None:
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, "start", refuse)
    with pytest.raises(RuntimeError):
        runner.start()
    assert runner.status().state is ScanState.FAILED  # not RUNNING forever
    assert runner.wait(0)  # the lock is free
    monkeypatch.undo()
    runner.start()  # and a later scan works
    assert runner.wait(5)
    assert runner.status().state is ScanState.FINISHED


def test_clock_failure_when_starting_releases_the_lock() -> None:
    runner = ScanRunner(lambda p: ScanReport(), _FlakyClock({1}))
    with pytest.raises(RuntimeError):
        runner.start()
    assert runner.status().state is ScanState.IDLE  # nothing started
    runner.start()  # the lock was not leaked
    assert runner.wait(5)
    assert runner.status().state is ScanState.FINISHED


def test_clock_failure_at_the_end_still_publishes_a_final_status_and_frees_the_lock() -> None:
    runner = ScanRunner(lambda p: ScanReport(added=1), _FlakyClock({2}))  # begin ok, end fails
    status = runner.run()
    assert status.state is ScanState.FINISHED
    assert status.finished_at is None
    runner.run()  # lock free


def test_clock_failure_while_reporting_a_failed_job_is_still_reported_as_failed() -> None:
    def boom(progress: ProgressCallback) -> ScanReport:
        raise RuntimeError("detail")

    runner = ScanRunner(boom, _FlakyClock({2}))
    status = runner.run()
    assert status.state is ScanState.FAILED
    assert status.finished_at is None
    assert runner.wait(0)


def test_database_error_while_closing_the_scan_is_a_generic_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A DB error after the walk (`remove_missing`) escapes `scan_library`; the runner reports it
    as FAILED without any detail and keeps the progress made so far."""

    class BrokenRepo(FakeItemRepository):
        def remove_missing(self, present_rel_paths: Collection[str]) -> int:
            raise DataAccessError("database error: /srv/library/secret.cbz")

    storage = FakeStorage({"a.fake": b"1", "b.fake": b"2"})
    runner = ScanRunner(
        lambda progress: scan_library(
            storage, BrokenRepo(), [FakeExtractor()], clock=FixedClock(), progress=progress
        ),
        FakeClock(),
    )
    with caplog.at_level(logging.ERROR, logger="app.services.scan_runner"):
        status = runner.run()
    assert (status.state, status.processed, status.total) == (ScanState.FAILED, 2, 2)
    assert "secret" not in repr(status)
    assert runner.wait(0)  # lock released


def test_base_exception_in_the_job_does_not_leave_the_status_running() -> None:
    def interrupted(progress: ProgressCallback) -> ScanReport:
        raise KeyboardInterrupt

    runner = ScanRunner(interrupted, FakeClock())
    with pytest.raises(KeyboardInterrupt):
        runner.run()
    assert runner.status().state is ScanState.FAILED
    assert runner.wait(0)


# ---------------------------------------------------------------- catalog


def _item(i: int, item_type: ItemType = ItemType.MANGA) -> Item:
    return Item(
        id=f"id-{i:04d}",
        type=item_type,
        title=f"Title {i:04d}",
        rel_path=f"p{i}.cbz",
        format="cbz",
        page_count=1,
        size=1,
        mtime_ns=1,
        added_at=START,
    )


def test_list_items_caps_limit_and_reports_has_more() -> None:
    repo = FakeItemRepository()
    for i in range(130):
        repo.add(_item(i))
    page = catalog.list_items(repo, query=None, item_type=None, offset=0, limit=10_000)
    assert len(page.items) == catalog.MAX_PAGE_SIZE == 100
    assert (page.limit, page.offset) == (100, 0)  # the effective values: callers do not recompute
    assert page.has_more
    assert _item(1).has_cover and not replace(_item(1), page_count=0).has_cover
    last = catalog.list_items(repo, query=None, item_type=None, offset=100, limit=100)
    assert (len(last.items), last.has_more) == (30, False)


def test_list_items_blank_query_lists_and_query_searches() -> None:
    repo = FakeItemRepository()
    repo.add(_item(1))
    repo.add(replace(_item(2), title="Needle"))
    assert len(catalog.list_items(repo, query="   ", item_type=None, offset=0, limit=10).items) == 2
    found = catalog.list_items(repo, query=" needle ", item_type=None, offset=0, limit=10)
    assert [i.title for i in found.items] == ["Needle"]


def test_get_item_raises_for_unknown_and_missing() -> None:
    repo = FakeItemRepository()
    repo.add(replace(_item(1), missing=True))
    with pytest.raises(ItemNotFound):
        catalog.get_item(repo, "id-0001")
    with pytest.raises(ItemNotFound):
        catalog.get_item(repo, "nope")


# ---------------------------------------------------------------- audit retention


def test_login_purges_audit_events_older_than_the_retention() -> None:
    rig = Rig()
    rig.service.login("alice", "correct horse battery staple", "10.0.0.1")
    assert rig.audit.purged_before == [rig.clock.now() - timedelta(days=180)]


def test_audit_retention_is_configurable_and_purge_is_throttled() -> None:
    rig = Rig(replace(DEFAULT_CONFIG, audit_retention=timedelta(days=7)))
    rig.service.login("alice", "correct horse battery staple", "10.0.0.1")
    assert rig.audit.purged_before == [rig.clock.now() - timedelta(days=7)]
    rig.service.login("alice", "correct horse battery staple", "10.0.0.1")
    assert len(rig.audit.purged_before) == 1  # opportunistic: at most once per hour
    rig.clock.advance(3601)
    rig.service.login("alice", "correct horse battery staple", "10.0.0.1")
    assert len(rig.audit.purged_before) == 2
