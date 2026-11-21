"""Authentication domain: refresh-token records, access claims and auth errors.

Pure domain: no framework, no I/O. Error messages are generic on purpose and never carry
credentials, tokens or hashes.
"""

from dataclasses import dataclass
from datetime import datetime


class AuthError(Exception):
    """Base class for authentication errors."""


class InvalidCredentialsError(AuthError):
    """Wrong username/password. ONE generic error for unknown, inactive and wrong-password."""


class LoginLockedError(AuthError):
    """Too many failures. Identical for existing and unknown accounts."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("too many attempts")
        self.retry_after_seconds = max(1, retry_after_seconds)


class InvalidSessionError(AuthError):
    """Refresh token unknown, expired, revoked, reused or no longer allowed."""


class NotAuthenticatedError(AuthError):
    """Access token missing or invalid, or the account/session is no longer valid."""


class InvalidTokenError(AuthError):
    """A signed token failed validation (raised by the token service)."""


class CurrentPasswordError(AuthError):
    """The current password given when changing the password is wrong."""


@dataclass(frozen=True, slots=True)
class RefreshToken:
    """A stored refresh token. `token_hash` is SHA-256 of the opaque value (never the value)."""

    id: str
    user_id: str
    family_id: str
    token_hash: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None
    revoked_at: datetime | None = None

    def __repr__(self) -> str:
        return f"RefreshToken(id={self.id!r}, family_id={self.family_id!r})"


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: str
    session_id: str
    token_id: str
    issued_at: datetime
    expires_at: datetime
