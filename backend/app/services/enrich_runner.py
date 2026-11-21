"""Use case: run the metadata enrichment one at a time (background thread or CLI).

Same contract as the scan runner: a non-blocking lock (a second `start()` raises
`EnrichAlreadyRunning`), the lock is always released, and the status only carries counts, never a
URL, host or message.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.errors import EnrichAlreadyRunning
from app.domain.metadata import EnrichReport
from app.ports.clock import Clock

logger = logging.getLogger(__name__)

EnrichJob = Callable[[bool, str | None], EnrichReport]  # (force, only this series id)


class EnrichState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class EnrichStatus:
    state: EnrichState = EnrichState.IDLE
    started_at: datetime | None = None
    finished_at: datetime | None = None
    matched: int = 0
    not_found: int = 0
    skipped: int = 0
    errors: int = 0


class EnrichRunner:
    def __init__(self, job: EnrichJob, clock: Clock) -> None:
        self._job = job
        self._clock = clock
        self._lock = threading.Lock()  # held for the whole run
        self._state_lock = threading.Lock()
        self._status = EnrichStatus()
        self._thread: threading.Thread | None = None

    def status(self) -> EnrichStatus:
        with self._state_lock:
            return self._status

    def start(self, *, force: bool = False) -> None:
        """Run in a background thread. Raises `EnrichAlreadyRunning` if one is in progress."""
        started = self._begin()
        try:
            thread = threading.Thread(
                target=self._execute,
                args=(force, None, started),
                name="metadata-enrich",
                daemon=True,
            )
            thread.start()
        except BaseException:
            self._finish(EnrichStatus(EnrichState.FAILED, started, self._safe_now()))
            raise
        self._thread = thread

    def run(self, *, force: bool = False, series_id: str | None = None) -> EnrichStatus:
        """Run in the calling thread (CLI). Same exclusivity as `start()`."""
        self._execute(force, series_id, self._begin())
        return self.status()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for the background run (tests). True if nothing is running afterwards."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return not self._lock.locked()

    def _begin(self) -> datetime:
        if not self._lock.acquire(blocking=False):
            raise EnrichAlreadyRunning
        try:
            started = self._clock.now()
            with self._state_lock:
                self._status = EnrichStatus(EnrichState.RUNNING, started)
        except BaseException:
            self._lock.release()
            raise
        return started

    def _finish(self, status: EnrichStatus) -> None:
        try:
            with self._state_lock:
                self._status = status
        finally:
            self._lock.release()

    def _safe_now(self) -> datetime | None:
        try:
            return self._clock.now()
        except Exception:
            return None

    def _execute(self, force: bool, series_id: str | None, started: datetime) -> None:
        final: EnrichStatus | None = None
        try:
            report = self._job(force, series_id)
            final = EnrichStatus(
                EnrichState.FINISHED,
                started,
                self._safe_now(),
                report.matched,
                report.not_found,
                report.skipped,
                report.errors,
            )
        except Exception as exc:
            logger.warning("Metadata enrichment run failed (%s)", type(exc).__name__)
        finally:
            self._finish(final or EnrichStatus(EnrichState.FAILED, started, self._safe_now()))
