import pytest
from app.adapters.security.rate_limiter import TokenBucketRateLimiter


class Time:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_burst_then_blocks_with_retry_after() -> None:
    clock = Time()
    limiter = TokenBucketRateLimiter(capacity=3, per_minute=60, time_fn=clock)
    assert all(limiter.check("ip").allowed for _ in range(3))
    blocked = limiter.check("ip")
    assert not blocked.allowed
    assert blocked.retry_after_seconds == 1


def test_refills_over_time() -> None:
    clock = Time()
    limiter = TokenBucketRateLimiter(capacity=1, per_minute=60, time_fn=clock)
    assert limiter.check("ip").allowed
    assert not limiter.check("ip").allowed
    clock.now += 1.0
    assert limiter.check("ip").allowed


def test_keys_are_independent() -> None:
    limiter = TokenBucketRateLimiter(capacity=1, per_minute=1, time_fn=Time())
    assert limiter.check("a").allowed
    assert limiter.check("b").allowed
    assert not limiter.check("a").allowed


def test_slow_rate_gives_long_retry_after() -> None:
    limiter = TokenBucketRateLimiter(capacity=1, per_minute=6, time_fn=Time())
    limiter.check("ip")
    assert limiter.check("ip").retry_after_seconds == 10


def test_memory_is_bounded() -> None:
    limiter = TokenBucketRateLimiter(capacity=1, per_minute=1, max_keys=10, time_fn=Time())
    for i in range(100):
        limiter.check(f"ip-{i}")
    assert len(limiter._buckets) <= 10


@pytest.mark.parametrize(
    "kwargs", [{"capacity": 0, "per_minute": 1}, {"capacity": 1, "per_minute": 0}]
)
def test_invalid_limits_are_rejected(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(**kwargs)
