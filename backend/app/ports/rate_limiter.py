from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter(Protocol):
    def check(self, key: str) -> RateDecision:
        """Consume one request for `key`; say whether it is allowed (and when to retry)."""
        ...
