from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol

AttemptScope = Literal["ip", "account", "ip_account"]


class LoginAttemptStore(Protocol):
    """Records login attempts. Keys are plain values here; implementations must store only a
    keyed hash of them (never the raw IP or username)."""

    def fingerprint(self, scope: AttemptScope, key: str) -> str:
        """Short, non-reversible identifier of a key, safe to put in audit logs."""
        ...

    def record(self, scope: AttemptScope, key: str, at: datetime, *, success: bool) -> None: ...

    def reserve_failures(self, keys: Sequence[tuple[AttemptScope, str]], at: datetime) -> list[int]:
        """Record one failure per (scope, key) in ONE transaction, BEFORE the password is
        checked, so concurrent attempts see each other. Returns reservation ids for `release`."""
        ...

    def release(self, reservation_ids: Sequence[int]) -> None:
        """Delete reservations (the attempt succeeded, or never really happened)."""
        ...

    def failures_since_last_success(
        self, scope: AttemptScope, key: str, since: datetime
    ) -> list[datetime]:
        """Failure timestamps (ascending) newer than `since` and recorded after the key's most
        recent success (a success resets the counter)."""
        ...

    def last_success_at(self, scope: AttemptScope, key: str) -> datetime | None: ...

    def purge(self, failures_before: datetime, successes_before: datetime) -> int: ...
