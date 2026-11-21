"""Progressive login lockout, computed from failure timestamps (pure function).

Stateless on purpose: the lockout state is derived from the recorded failures, so it survives
restarts and needs no extra storage.
"""

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

_MAX_DOUBLINGS = 32


@dataclass(frozen=True, slots=True)
class LockoutPolicy:
    max_failures: int
    window: timedelta
    base_lockout: timedelta
    max_lockout: timedelta

    @property
    def lookback(self) -> timedelta:
        """How far back failures must be read so that no active lock can be missed."""
        return self.window + self.max_lockout


def locked_until(
    failures: Iterable[datetime], policy: LockoutPolicy, now: datetime
) -> datetime | None:
    """Return when the lock ends, or None if not locked at `now`.

    `failures` are ascending timestamps recorded since the last success. Whenever
    `max_failures` of them fall inside `window`, a lock starts; its duration doubles with each
    consecutive lock (base, 2*base, ...) up to `max_lockout`. Failures recorded while a lock is
    active are ignored (they are not recorded in the first place).
    """
    until: datetime | None = None
    locks = 0
    recent: deque[datetime] = deque()
    for at in failures:
        if until is not None and at < until:
            continue
        while recent and at - recent[0] > policy.window:
            recent.popleft()
        recent.append(at)
        if len(recent) >= policy.max_failures:
            duration = min(
                policy.base_lockout * (2 ** min(locks, _MAX_DOUBLINGS)), policy.max_lockout
            )
            until = at + duration
            locks += 1
            recent.clear()
    if until is not None and until > now:
        return until
    return None
