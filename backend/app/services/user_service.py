"""Use cases for managing accounts (admin-only; there is no public registration)."""

import uuid
from dataclasses import replace

from app.domain.password_policy import validate_password
from app.domain.user import Role, User, UserNotFoundError, normalize_username
from app.ports.audit_log import AuditLog
from app.ports.clock import Clock
from app.ports.password_hasher import PasswordHasher
from app.ports.user_repository import UserRepository


class UserService:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        audit: AuditLog,
        clock: Clock,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._audit = audit
        self._clock = clock

    def create_user(
        self, username: str, password: str, *, role: Role = Role.USER, source: str = "cli"
    ) -> User:
        name = normalize_username(username)
        validate_password(password, name)
        now = self._clock.now()
        user = User(
            id=str(uuid.uuid4()),
            username=name,
            password_hash=self._hasher.hash(password),
            role=role,
            is_active=True,
            theme_pref="system",
            created_at=now,
            updated_at=now,
            password_changed_at=now,
        )
        self._users.add(user)
        self._audit.record(
            "user.created", user_id=user.id, detail={"role": role.value, "source": source}
        )
        return user

    def reset_password(self, username: str, password: str, *, source: str = "cli") -> User:
        user = self._require(username)
        validate_password(password, user.username)
        now = self._clock.now()
        new_hash = self._hasher.hash(password)
        self._users.set_password_hash(user.id, new_hash, now)
        updated = replace(user, password_hash=new_hash, updated_at=now, password_changed_at=now)
        self._audit.record("user.password_reset", user_id=user.id, detail={"source": source})
        return updated

    def deactivate_user(self, username: str, *, source: str = "cli") -> User:
        user = self._require(username)
        now = self._clock.now()
        self._users.deactivate(user.id, now)
        updated = replace(user, is_active=False, updated_at=now)
        self._audit.record("user.deactivated", user_id=user.id, detail={"source": source})
        return updated

    def list_users(self) -> list[User]:
        return self._users.list_all()

    def _require(self, username: str) -> User:
        user = self._users.get_by_username(normalize_username(username))
        if user is None:
            raise UserNotFoundError("user not found")
        return user
