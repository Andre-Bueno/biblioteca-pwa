"""Bounded concurrency for expensive operations (password hashing, page reads).

Requests that cannot get a slot fail fast with `ResourceBusy` instead of waiting without limit:
at most `slots` threads work and at most `max_waiting` more wait (each for at most `timeout`
seconds), so a flood can hold only a bounded number of worker threads and the rest of the API
stays responsive.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.domain.errors import ResourceBusy


class BoundedGate:
    def __init__(self, *, slots: int, max_waiting: int, timeout: float) -> None:
        if slots < 1 or max_waiting < 0 or timeout < 0:
            raise ValueError("invalid gate configuration")
        self._slots = threading.BoundedSemaphore(slots)
        self._max_waiting = max_waiting
        self._timeout = timeout
        self._lock = threading.Lock()
        self._waiting = 0

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Hold one slot for the duration of the block, or raise `ResourceBusy`."""
        if not self._slots.acquire(blocking=False):
            with self._lock:
                if self._waiting >= self._max_waiting:
                    raise ResourceBusy
                self._waiting += 1
            try:
                acquired = self._slots.acquire(timeout=self._timeout)
            finally:
                with self._lock:
                    self._waiting -= 1
            if not acquired:
                raise ResourceBusy
        try:
            yield
        finally:
            self._slots.release()
