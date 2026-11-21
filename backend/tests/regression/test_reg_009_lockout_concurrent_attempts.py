"""REG-009 (FIND-2026-004): concurrent attempts went past the lockout limit.

Bug: the lock was checked, then the password verified (slow), and only then the failure recorded,
so N simultaneous attempts all passed the check before the first failure existed (20 simultaneous
attempts were all evaluated with a limit of 5). Fix: check + reservation of the attempt happen
atomically (under one lock) BEFORE the hash; a success or an aborted attempt releases/clears it.
"""

import contextlib
import threading
import time

from app.adapters.security.argon2_hasher import Argon2Hasher
from app.domain.auth import InvalidCredentialsError, LoginLockedError

from auth_fakes import PASSWORD, FakeHasher, Rig
from auth_fakes import Env as _Env

LIMIT = 5  # DEFAULT_CONFIG.ip_account_policy.max_failures
THREADS = 20


class _SlowFakeHasher(FakeHasher):
    def verify(self, password_hash: str | None, password: str) -> bool:
        time.sleep(0.05)
        return super().verify(password_hash, password)


class _SlowArgon(Argon2Hasher):
    def verify(self, password_hash: str | None, password: str) -> bool:
        time.sleep(0.05)
        return super().verify(password_hash, password)


def _run_concurrently(call, count: int = THREADS) -> list[str]:  # type: ignore[no-untyped-def]
    outcomes: list[str] = []
    barrier = threading.Barrier(count)

    def worker() -> None:
        barrier.wait()
        try:
            call()
            outcomes.append("ok")
        except InvalidCredentialsError:
            outcomes.append("failed")
        except LoginLockedError:
            outcomes.append("locked")

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return outcomes


def test_simultaneous_wrong_attempts_do_not_exceed_the_limit_service_level() -> None:
    rig = Rig()
    rig.service._hasher = _SlowFakeHasher()  # type: ignore[attr-defined]
    outcomes = _run_concurrently(
        lambda: rig.service.login("alice", "wrong password here", "9.9.9.9")
    )
    assert len(outcomes) == THREADS
    assert outcomes.count("failed") <= LIMIT
    assert outcomes.count("locked") >= THREADS - LIMIT


def test_simultaneous_wrong_attempts_do_not_exceed_the_limit_with_the_real_store(
    db_url: str,
) -> None:
    env = _Env(db_url, hasher=_SlowArgon(time_cost=1, memory_cost_kib=8, parallelism=1))
    env.create_user()
    service = env.container.auth_service
    outcomes = _run_concurrently(lambda: service.login("alice", "wrong password here", "9.9.9.9"))
    assert len(outcomes) == THREADS
    assert outcomes.count("failed") <= LIMIT
    assert outcomes.count("locked") >= THREADS - LIMIT


def test_a_successful_login_does_not_leave_a_failure_behind_in_the_ip_counter() -> None:
    """The reservation made before the hash must be undone on success (the ip scope is not
    reset by successes, so a leftover would make good logins count against the address)."""
    rig = Rig()
    for _ in range(30):
        rig.service.login("alice", PASSWORD, "8.8.8.8")
    rig.fail(1, ip="8.8.8.8")  # still far from the address limit (20)
    rig.service.login("alice", PASSWORD, "8.8.8.8")


def test_an_aborted_attempt_is_released() -> None:
    """If the hasher is busy the attempt never happened: it must not count as a failure."""
    from app.domain.errors import ResourceBusy

    rig = Rig()

    class Busy(FakeHasher):
        def verify(self, password_hash: str | None, password: str) -> bool:
            raise ResourceBusy

    rig.service._hasher = Busy()  # type: ignore[attr-defined]
    for _ in range(LIMIT * 3):
        with contextlib.suppress(ResourceBusy):
            rig.service.login("alice", PASSWORD, "7.7.7.7")
    assert [r for r in rig.attempts.rows if not r[4]] == []


def test_concurrent_first_use_builds_a_single_auth_service(db_url: str) -> None:
    """cached_property is not thread-safe: two threads could each build a service (and thus
    each get their own lock), defeating the atomic check+reserve on a cold start."""
    from app.adapters.persistence.migrator import upgrade
    from app.composition import Container

    from auth_fakes import make_settings

    upgrade(db_url)
    container = Container(make_settings(db_url))
    built: list[object] = []
    barrier = threading.Barrier(12)

    def grab() -> None:
        barrier.wait()
        built.append(container.auth_service)

    threads = [threading.Thread(target=grab) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert len(built) == 12
    assert len({id(s) for s in built}) == 1
