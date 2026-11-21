from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from app.domain.password_policy import PasswordPolicyError
from app.domain.user import (
    InvalidUsernameError,
    Role,
    User,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)
from app.services.user_service import UserService


class FakeRepo:
    def __init__(self) -> None:
        self.by_id: dict[str, User] = {}

    def add(self, user: User) -> None:
        if any(u.username.lower() == user.username.lower() for u in self.by_id.values()):
            raise UsernameAlreadyExistsError("username already exists")
        self.by_id[user.id] = user

    def set_password_hash(self, user_id: str, new_hash: str, now: datetime) -> None:
        user = self.by_id.get(user_id)
        if user is None:
            raise UserNotFoundError("user not found")
        self.by_id[user_id] = replace(
            user, password_hash=new_hash, updated_at=now, password_changed_at=now
        )

    def deactivate(self, user_id: str, now: datetime) -> None:
        user = self.by_id.get(user_id)
        if user is None:
            raise UserNotFoundError("user not found")
        self.by_id[user_id] = replace(user, is_active=False, updated_at=now)

    def get_by_id(self, user_id: str) -> User | None:
        return self.by_id.get(user_id)

    def get_by_username(self, username: str) -> User | None:
        return next((u for u in self.by_id.values() if u.username == username.lower()), None)

    def list_all(self) -> list[User]:
        return sorted(self.by_id.values(), key=lambda u: u.username)


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"fake${password[::-1]}"

    def verify(self, password_hash: str | None, password: str) -> bool:
        return password_hash == self.hash(password)

    def needs_rehash(self, password_hash: str) -> bool:
        return False


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None, Mapping[str, str | int | bool] | None]] = []

    def record(
        self,
        event: str,
        *,
        user_id: str | None = None,
        ip: str | None = None,
        detail: Mapping[str, str | int | bool] | None = None,
    ) -> None:
        self.events.append((event, user_id, detail))

    def purge(self, before: datetime) -> int:
        return 0


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def parts() -> tuple[UserService, FakeRepo, FakeAudit, FakeClock]:
    repo, audit, clock = FakeRepo(), FakeAudit(), FakeClock()
    return UserService(repo, FakeHasher(), audit, clock), repo, audit, clock


def test_create_user_stores_hash_and_audits(
    parts: tuple[UserService, FakeRepo, FakeAudit, FakeClock],
) -> None:
    service, repo, audit, _ = parts
    user = service.create_user("  Alice ", "correct horse battery", role=Role.ADMIN)
    assert user.username == "alice"
    assert user.role is Role.ADMIN
    assert user.is_active is True
    assert user.theme_pref == "system"
    assert user.password_hash != "correct horse battery"
    assert repo.get_by_id(user.id) == user
    assert audit.events == [("user.created", user.id, {"role": "admin", "source": "cli"})]


def test_audit_never_contains_password(
    parts: tuple[UserService, FakeRepo, FakeAudit, FakeClock],
) -> None:
    service, _, audit, _ = parts
    service.create_user("alice", "correct horse battery")
    assert "correct horse battery" not in repr(audit.events)


def test_create_rejects_weak_password_and_stores_nothing(
    parts: tuple[UserService, FakeRepo, FakeAudit, FakeClock],
) -> None:
    service, repo, audit, _ = parts
    with pytest.raises(PasswordPolicyError):
        service.create_user("alice", "short")
    assert repo.by_id == {}
    assert audit.events == []


def test_create_rejects_invalid_username(
    parts: tuple[UserService, FakeRepo, FakeAudit, FakeClock],
) -> None:
    service, *_ = parts
    with pytest.raises(InvalidUsernameError):
        service.create_user("a b", "correct horse battery")


def test_duplicate_username_case_insensitive(
    parts: tuple[UserService, FakeRepo, FakeAudit, FakeClock],
) -> None:
    service, *_ = parts
    service.create_user("alice", "correct horse battery")
    with pytest.raises(UsernameAlreadyExistsError):
        service.create_user("ALICE", "another good password")


def test_reset_password_updates_hash_and_timestamp(
    parts: tuple[UserService, FakeRepo, FakeAudit, FakeClock],
) -> None:
    service, repo, audit, clock = parts
    user = service.create_user("alice", "correct horse battery")
    clock.current += timedelta(days=1)
    updated = service.reset_password("Alice", "brand new passphrase")
    assert updated.password_hash != user.password_hash
    assert updated.password_changed_at == clock.current
    assert updated.created_at == user.created_at
    assert repo.get_by_id(user.id) == updated
    assert audit.events[-1][0] == "user.password_reset"


def test_reset_password_applies_policy_with_username(
    parts: tuple[UserService, FakeRepo, FakeAudit, FakeClock],
) -> None:
    service, *_ = parts
    service.create_user("alice.example", "correct horse battery")
    with pytest.raises(PasswordPolicyError):
        service.reset_password("alice.example", "alice.example")


def test_reset_unknown_user(parts: tuple[UserService, FakeRepo, FakeAudit, FakeClock]) -> None:
    service, *_ = parts
    with pytest.raises(UserNotFoundError):
        service.reset_password("ghost", "correct horse battery")


def test_deactivate(parts: tuple[UserService, FakeRepo, FakeAudit, FakeClock]) -> None:
    service, repo, audit, _ = parts
    user = service.create_user("alice", "correct horse battery")
    result = service.deactivate_user("alice")
    assert result.is_active is False
    assert replace(result, is_active=True, updated_at=user.updated_at) == user
    assert audit.events[-1][0] == "user.deactivated"
    assert [u.username for u in service.list_users()] == ["alice"]


def test_user_repr_hides_hash(parts: tuple[UserService, FakeRepo, FakeAudit, FakeClock]) -> None:
    service, *_ = parts
    user = service.create_user("alice", "correct horse battery")
    assert user.password_hash not in repr(user)
