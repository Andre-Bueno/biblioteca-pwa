"""User entity and username rules. Pure domain: no framework, no I/O."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 64
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

THEMES = ("system", "light", "dark")


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


class UserError(Exception):
    """Base class for user-related domain errors (messages never contain secrets)."""


class InvalidUsernameError(UserError):
    pass


class UsernameAlreadyExistsError(UserError):
    pass


class UserNotFoundError(UserError):
    pass


@dataclass(frozen=True, slots=True)
class User:
    id: str
    username: str
    password_hash: str
    role: Role
    is_active: bool
    theme_pref: str
    created_at: datetime
    updated_at: datetime
    password_changed_at: datetime

    def __repr__(self) -> str:
        # Never expose the hash in logs or tracebacks.
        return f"User(id={self.id!r}, username={self.username!r}, role={self.role.value!r})"


def normalize_username(raw: str) -> str:
    """Trim + lowercase, then validate. Usernames are case-insensitive."""
    username = raw.strip().lower()
    if not USERNAME_MIN_LENGTH <= len(username) <= USERNAME_MAX_LENGTH:
        raise InvalidUsernameError(
            f"username must have {USERNAME_MIN_LENGTH} to {USERNAME_MAX_LENGTH} characters"
        )
    if not _USERNAME_RE.fullmatch(username):
        raise InvalidUsernameError(
            "username may contain only letters, digits, '.', '_' and '-', "
            "and must start with a letter or digit"
        )
    return username
