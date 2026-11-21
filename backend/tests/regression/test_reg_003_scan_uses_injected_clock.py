"""REG-003: the scan read the wall clock directly.

Bug: `services/scan.py` called `datetime.now(UTC)`, so `added_at` could not be controlled in tests
and bypassed the `Clock` port. Cause: no clock was injected into the use case.
"""

from datetime import UTC, datetime

from app.services.scan import scan_library

from fakes import FakeExtractor, FakeItemRepository, FakeStorage, FixedClock


def test_added_at_comes_from_the_clock_port() -> None:
    moment = datetime(2031, 1, 2, 3, 4, 5, tzinfo=UTC)
    repo = FakeItemRepository()
    scan_library(FakeStorage({"a.fake": b"1"}), repo, [FakeExtractor()], clock=FixedClock(moment))
    item = repo.get_by_rel_path("a.fake")
    assert item is not None
    assert item.added_at == moment
