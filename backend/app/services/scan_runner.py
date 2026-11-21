"""Use case: run the library scan one at a time, in the background, with observable progress.

The runner owns a non-blocking lock: a second `start()` while a scan runs raises
`ScanAlreadyRunning`. The status never contains paths, file names or exception messages, only
counts and error class names.
"""

import logging
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain.errors import ScanAlreadyRunning
from app.domain.library import ScanProgress, ScanReport
from app.ports.clock import Clock
from app.services.scan import ProgressCallback

logger = logging.getLogger(__name__)

ScanJob = Callable[[ProgressCallback], ScanReport]


class ScanState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ScanStatus:
    state: ScanState = ScanState.IDLE
    processed: int = 0
    total: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    skipped: int = 0
    error_count: int = 0
    errors_by_reason: dict[str, int] = field(default_factory=dict)


class ScanRunner:
    """Whatever happens (job error, clock error, thread that cannot start), the lock is released
    and the status ends in FINISHED or FAILED: it is never left RUNNING with nobody running.

    There is no cancellation: the scan is a daemon thread that ends with the process, and nothing
    in the API asks to stop it (YAGNI); add a shutdown event here when something needs it.
    """

    def __init__(self, job: ScanJob, clock: Clock) -> None:
        self._job = job
        self._clock = clock
        self._lock = threading.Lock()  # held for the whole duration of a scan
        self._state_lock = threading.Lock()  # protects `_status`
        self._status = ScanStatus()
        self._thread: threading.Thread | None = None

    def status(self) -> ScanStatus:
        with self._state_lock:
            return self._status

    def start(self) -> None:
        """Run a scan in a background thread. Raises `ScanAlreadyRunning` if one is in progress."""
        self._begin()
        try:
            thread = threading.Thread(target=self._execute, name="library-scan", daemon=True)
            thread.start()
        except BaseException:
            # The thread never ran, so nobody else will release the lock or fix the status.
            self._finish(self._failed_status(self.status().started_at))
            raise
        self._thread = thread

    def run(self) -> ScanStatus:
        """Run a scan in the calling thread (CLI). Same exclusivity as `start()`."""
        self._begin()
        self._execute()
        return self.status()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for the background scan to end (tests). True if no scan is running afterwards."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return not self._lock.locked()

    # -- internals -------------------------------------------------------

    def _begin(self) -> None:
        if not self._lock.acquire(blocking=False):
            raise ScanAlreadyRunning
        try:
            self._set(ScanStatus(state=ScanState.RUNNING, started_at=self._clock.now()))
        except BaseException:
            self._lock.release()  # e.g. the clock failed: nothing started, nothing to report
            raise

    def _set(self, status: ScanStatus) -> None:
        with self._state_lock:
            self._status = status

    def _finish(self, status: ScanStatus) -> None:
        """Publish the final status and release the lock (in this order, always both)."""
        try:
            self._set(status)
        finally:
            self._lock.release()

    def _safe_now(self) -> datetime | None:
        """`finished_at` is informative: a broken clock must not prevent the final status."""
        try:
            return self._clock.now()
        except Exception:
            logger.exception("Clock failed while finishing the library scan")
            return None

    def _on_progress(self, progress: ScanProgress) -> None:
        with self._state_lock:
            self._status = ScanStatus(
                state=ScanState.RUNNING,
                processed=progress.processed,
                total=progress.total,
                started_at=self._status.started_at,
            )

    def _failed_status(self, started: datetime | None) -> ScanStatus:
        last = self.status()
        return ScanStatus(
            state=ScanState.FAILED,
            processed=last.processed,
            total=last.total,
            started_at=started,
            finished_at=self._safe_now(),
        )

    def _finished_status(self, report: ScanReport, started: datetime | None) -> ScanStatus:
        last = self.status()
        return ScanStatus(
            state=ScanState.FINISHED,
            processed=last.processed,
            total=last.total,
            started_at=started,
            finished_at=self._safe_now(),
            added=report.added,
            updated=report.updated,
            unchanged=report.unchanged,
            removed=report.removed,
            skipped=report.skipped,
            error_count=len(report.errors),
            errors_by_reason=dict(Counter(error.reason for error in report.errors)),
        )

    def _execute(self) -> None:
        started = self.status().started_at
        final: ScanStatus | None = None
        try:
            report = self._job(self._on_progress)
            if report.removal_skipped is not None:
                logger.warning(
                    "Library scan did not mark vanished items as missing (%s)",
                    report.removal_skipped,
                )
            final = self._finished_status(report, started)
        except Exception:
            # Detail goes to the server log only; the status carries no message.
            logger.exception("Library scan failed")
        finally:
            # `final is None` also covers BaseException (interpreter shutdown, ...): never leave
            # the status RUNNING once the lock is free.
            self._finish(final if final is not None else self._failed_status(started))
