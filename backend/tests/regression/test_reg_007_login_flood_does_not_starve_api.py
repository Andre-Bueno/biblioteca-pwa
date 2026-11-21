"""REG-007 (FIND-2026-002): a flood of anonymous logins starved the whole API.

Bug: every login waited on a 4-slot semaphore for Argon2 while holding one of the 40 worker
threads, so 120 concurrent logins left no thread for /health or /auth/me. Fix: bounded queue with
a short timeout; excess logins get a generic 503 immediately and no failure is recorded for them.
"""

import threading
import time

import pytest
from app.adapters.security.argon2_hasher import Argon2Hasher
from app.domain.errors import ResourceBusy
from sqlalchemy import func, select

from auth_fakes import PASSWORD, Env


class _SlowArgon:
    """Stand-in for argon2.PasswordHasher: slow `verify`, tracks how many run at once."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.running = 0
        self.peak = 0
        self._lock = threading.Lock()

    def hash(self, password: str) -> str:
        return f"h:{password}"

    def verify(self, target: str, password: str) -> bool:
        with self._lock:
            self.running += 1
            self.peak = max(self.peak, self.running)
        try:
            time.sleep(self.seconds)
        finally:
            with self._lock:
                self.running -= 1
        return False


def test_hasher_bounds_running_and_waiting_threads_and_rejects_the_rest_fast() -> None:
    hasher = Argon2Hasher(
        time_cost=1,
        memory_cost_kib=8,
        parallelism=1,
        max_concurrent=1,
        max_waiting=1,
        wait_seconds=0.2,
    )
    slow = _SlowArgon(0.5)
    hasher._argon = slow  # type: ignore[assignment]
    outcomes: list[str] = []
    busy_elapsed: list[float] = []
    barrier = threading.Barrier(8)

    def attempt() -> None:
        barrier.wait()
        start = time.perf_counter()
        try:
            hasher.verify("stored", "pw")
            outcomes.append("done")
        except ResourceBusy:
            outcomes.append("busy")
            busy_elapsed.append(time.perf_counter() - start)

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert len(outcomes) == 8
    assert outcomes.count("busy") >= 6  # 1 running + at most 1 queued (and it times out)
    assert slow.peak == 1
    # Rejected callers gave up after the short wait; none sat through the slow hashes ahead.
    assert max(busy_elapsed) < 0.45


def test_busy_hasher_gives_a_generic_503_and_records_no_failure(db_url: str) -> None:
    class BusyHasher(Argon2Hasher):
        def verify(self, password_hash: str | None, password: str) -> bool:
            raise ResourceBusy

    env = Env(db_url, hasher=BusyHasher(time_cost=1, memory_cost_kib=8, parallelism=1))
    env.create_user()
    client = env.client()
    known = client.login("alice", PASSWORD)
    unknown = client.login("ghost", PASSWORD)
    assert known.status_code == unknown.status_code == 503
    assert known.content == unknown.content  # no user-existence oracle
    assert known.headers["retry-after"] == "1"
    assert "set-cookie" not in known.headers
    from app.adapters.persistence.models import LoginAttemptRow

    with env.container.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(LoginAttemptRow)) == 0


def test_login_still_works_when_the_hasher_has_room(env: Env) -> None:
    assert env.client().login().status_code == 200


@pytest.mark.parametrize("slots,waiting,timeout", [(0, 1, 1.0), (1, -1, 1.0), (1, 1, -1.0)])
def test_invalid_gate_configuration_is_refused(slots: int, waiting: int, timeout: float) -> None:
    with pytest.raises(ValueError):
        Argon2Hasher(
            time_cost=1,
            memory_cost_kib=8,
            parallelism=1,
            max_concurrent=slots,
            max_waiting=waiting,
            wait_seconds=timeout,
        )
