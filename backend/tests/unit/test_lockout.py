from datetime import UTC, datetime, timedelta

from app.domain.lockout import LockoutPolicy, locked_until

T0 = datetime(2026, 1, 1, tzinfo=UTC)
POLICY = LockoutPolicy(
    max_failures=3,
    window=timedelta(minutes=15),
    base_lockout=timedelta(minutes=5),
    max_lockout=timedelta(minutes=30),
)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def test_below_threshold_is_not_locked() -> None:
    assert locked_until([at(0), at(1)], POLICY, at(2)) is None


def test_threshold_locks_for_base_duration() -> None:
    assert locked_until([at(0), at(1), at(2)], POLICY, at(3)) == at(2) + timedelta(minutes=5)


def test_lock_expires() -> None:
    assert locked_until([at(0), at(1), at(2)], POLICY, at(2 + 300)) is None


def test_failures_outside_window_do_not_count() -> None:
    assert locked_until([at(0), at(1000), at(1001)], POLICY, at(1002)) is None


def test_lock_doubles_on_each_consecutive_lock_up_to_the_cap() -> None:
    failures = [at(0), at(1), at(2)]  # lock 1: 300 s
    failures += [at(400), at(401), at(402)]  # lock 2: 600 s
    assert locked_until(failures, POLICY, at(403)) == at(402) + timedelta(minutes=10)
    failures += [at(1100), at(1101), at(1102)]  # lock 3: 1200 s
    failures += [at(2400), at(2401), at(2402)]  # lock 4: capped at 1800 s
    assert locked_until(failures, POLICY, at(2403)) == at(2402) + timedelta(minutes=30)


def test_lock_outlives_the_counting_window() -> None:
    """A long lock must not vanish when its failures slide out of the window."""
    policy = LockoutPolicy(3, timedelta(seconds=60), timedelta(hours=1), timedelta(hours=1))
    failures = [at(0), at(1), at(2)]
    assert locked_until(failures, policy, at(2 + 1800)) == at(2) + timedelta(hours=1)


def test_huge_number_of_locks_does_not_overflow() -> None:
    failures = [at(group * 2000 + n) for group in range(300) for n in range(3)]
    last = failures[-1]
    assert locked_until(failures, POLICY, last + timedelta(seconds=1)) == last + timedelta(
        minutes=30
    )


def test_lookback_covers_window_plus_max_lockout() -> None:
    assert POLICY.lookback == timedelta(minutes=45)
