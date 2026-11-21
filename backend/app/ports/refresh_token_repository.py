from datetime import datetime, timedelta
from typing import Protocol

from app.domain.auth import RefreshToken


class RefreshTokenRepository(Protocol):
    """Persistence of refresh tokens. Errors surface as `DataAccessError` (generic message)."""

    def add(self, token: RefreshToken) -> None: ...

    def get_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    def mark_used(self, token_id: str, at: datetime) -> bool:
        """Atomically set `used_at` if the token is unused and not revoked.

        Return False when it was already used/revoked (a concurrent or replayed use).
        """
        ...

    def rotate(
        self, stored_id: str, successor: RefreshToken, at: datetime, grace: timedelta
    ) -> bool:
        """Atomically (ONE transaction) consume `stored_id` and store its `successor`.

        Succeeds when the token is unused and not revoked (it is marked used), or when it was
        already used no more than `grace` ago (a legitimate concurrent/retried refresh: the
        successor is stored as a sibling). Returns False, storing nothing, when the token is
        revoked, missing, or was used longer ago than `grace` (reuse).
        """
        ...

    def revoke_family(self, family_id: str, at: datetime) -> None:
        """Revoke every token of the family that is not revoked yet."""
        ...

    def revoke_all_for_user(self, user_id: str, at: datetime) -> None: ...

    def family_started_at(self, family_id: str) -> datetime | None:
        """Creation time of the first token of the family (session absolute lifetime)."""
        ...

    def is_family_active(self, family_id: str, user_id: str) -> bool:
        """True if the family belongs to the user and has at least one non-revoked token."""
        ...

    def purge_dead_families(self, before: datetime) -> int:
        """Delete families whose newest token expired before `before`."""
        ...
