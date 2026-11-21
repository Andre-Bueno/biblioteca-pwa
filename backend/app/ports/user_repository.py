from datetime import datetime
from typing import Protocol

from app.domain.user import User


class UserRepository(Protocol):
    """There is deliberately no "save the whole user" method: writes are targeted so that a
    slow step (password hashing) between read and write cannot overwrite concurrent changes."""

    def add(self, user: User) -> None:
        """Raise UsernameAlreadyExistsError (case-insensitive) or DataAccessError."""
        ...

    def replace_password_hash(
        self,
        user_id: str,
        *,
        expected_hash: str,
        new_hash: str,
        now: datetime,
        password_changed: bool,
    ) -> bool:
        """Compare-and-set for the user's own flows (login rehash, change password).

        Applies only if the user is still ACTIVE and still has `expected_hash`; returns False
        when it did not apply (deactivated, or the password was changed/reset meanwhile).
        `password_changed=False` keeps `password_changed_at` (a rehash is not a password change).
        Raise DataAccessError.
        """
        ...

    def set_password_hash(self, user_id: str, new_hash: str, now: datetime) -> None:
        """Admin reset: unconditional (works on inactive users). Raise UserNotFoundError."""
        ...

    def deactivate(self, user_id: str, now: datetime) -> None:
        """Raise UserNotFoundError or DataAccessError. Idempotent."""
        ...

    def get_by_id(self, user_id: str) -> User | None: ...

    def get_by_username(self, username: str) -> User | None:
        """Case-insensitive lookup."""
        ...

    def list_all(self) -> list[User]: ...
