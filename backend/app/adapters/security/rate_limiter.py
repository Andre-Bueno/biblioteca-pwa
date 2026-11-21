import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from app.ports.rate_limiter import RateDecision

DEFAULT_MAX_KEYS = 50_000


class TokenBucketRateLimiter:
    """In-memory token bucket per key (the key is the client IP).

    LIMITATION (multi-replica): state lives in this process only. With N replicas behind a load
    balancer the effective limit is up to N times higher, and a restart resets all buckets. The
    login lockout does NOT have this weakness (it is stored in the database); this limiter is a
    coarse, cheap first line against floods. Use a shared store (e.g. Redis) before scaling out.

    Memory is bounded: at most `max_keys` buckets are kept (least recently used evicted first), so
    an attacker rotating source addresses cannot grow the process without limit.
    """

    def __init__(
        self,
        *,
        capacity: int,
        per_minute: int,
        max_keys: int = DEFAULT_MAX_KEYS,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity < 1 or per_minute < 1 or max_keys < 1:
            raise ValueError("limits must be positive")
        self._capacity = float(capacity)
        self._rate = per_minute / 60.0  # tokens per second
        self._max_keys = max_keys
        self._time = time_fn
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()  # key -> (tokens, at)
        self._lock = threading.Lock()

    def check(self, key: str) -> RateDecision:
        now = self._time()
        with self._lock:
            tokens, at = self._buckets.pop(key, (self._capacity, now))
            tokens = min(self._capacity, tokens + max(0.0, now - at) * self._rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                self._evict()
                return RateDecision(allowed=True)
            self._buckets[key] = (tokens, now)
            self._evict()
            wait = (1.0 - tokens) / self._rate
            return RateDecision(allowed=False, retry_after_seconds=max(1, math.ceil(wait)))

    def _evict(self) -> None:
        while len(self._buckets) > self._max_keys:
            self._buckets.popitem(last=False)
