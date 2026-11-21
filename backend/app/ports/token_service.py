from datetime import datetime
from typing import Protocol

from app.domain.auth import AccessClaims


class TokenService(Protocol):
    def issue_access_token(
        self, *, user_id: str, session_id: str, issued_at: datetime, expires_at: datetime
    ) -> str:
        """Signed access token carrying the user id, session id (refresh family) and a unique id."""
        ...

    def decode_access_token(self, token: str, *, now: datetime) -> AccessClaims:
        """Validate signature (fixed algorithm), required claims and time window at `now`.

        Raise `InvalidTokenError` (no detail) for anything wrong.
        """
        ...
