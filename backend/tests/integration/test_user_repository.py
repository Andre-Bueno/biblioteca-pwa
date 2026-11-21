from dataclasses import replace
from datetime import UTC, datetime

import pytest
from app.adapters.persistence.audit_log import SqlAlchemyAuditLog
from app.adapters.persistence.db import create_db_engine, create_session_factory
from app.adapters.persistence.models import AuditLogRow
from app.adapters.persistence.user_repository import SqlAlchemyUserRepository
from app.adapters.security.system_clock import SystemClock
from app.domain.errors import DataAccessError
from app.domain.user import (
    Role,
    User,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

NOW = datetime(2026, 1, 1, 12, 30, tzinfo=UTC)


def make_user(uid: str = "id-1", username: str = "alice") -> User:
    return User(uid, username, "hash-value", Role.USER, True, "system", NOW, NOW, NOW)


def test_add_and_get_roundtrip_keeps_aware_utc(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    user = make_user()
    repo.add(user)
    assert repo.get_by_id("id-1") == user
    loaded = repo.get_by_username("ALICE")
    assert loaded == user
    assert loaded is not None
    assert loaded.created_at.tzinfo is not None


def test_get_missing_returns_none(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    assert repo.get_by_id("x") is None
    assert repo.get_by_username("x") is None


def test_duplicate_username_case_insensitive(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    repo.add(make_user("1", "alice"))
    with pytest.raises(UsernameAlreadyExistsError):
        repo.add(make_user("2", "Alice"))
    assert len(repo.list_all()) == 1


def test_set_password_hash_and_deactivate(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    user = make_user()
    repo.add(user)
    later = datetime(2026, 2, 1, tzinfo=UTC)
    repo.set_password_hash("id-1", "new-hash", later)
    repo.deactivate("id-1", later)
    assert repo.get_by_id("id-1") == replace(
        user,
        is_active=False,
        password_hash="new-hash",
        updated_at=later,
        password_changed_at=later,
    )


def test_targeted_writes_on_missing_user(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    with pytest.raises(UserNotFoundError):
        repo.deactivate("ghost", NOW)
    with pytest.raises(UserNotFoundError):
        repo.set_password_hash("ghost", "h", NOW)


def test_list_all_sorted(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    repo.add(make_user("2", "bob"))
    repo.add(make_user("1", "alice"))
    assert [u.username for u in repo.list_all()] == ["alice", "bob"]


def test_unmigrated_db_raises_generic_error(db_url: str) -> None:
    engine = create_db_engine(db_url)
    try:
        repo = SqlAlchemyUserRepository(create_session_factory(engine))
        with pytest.raises(DataAccessError) as exc:
            repo.add(make_user())
        assert "hash-value" not in str(exc.value)
        assert exc.value.__cause__ is None
        assert exc.value.__suppress_context__ is True
    finally:
        engine.dispose()


def test_audit_log_records_and_limits_detail(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyUserRepository(session_factory)
    repo.add(make_user())
    audit = SqlAlchemyAuditLog(session_factory, SystemClock())
    audit.record("user.created", user_id="id-1", ip="127.0.0.1", detail={"role": "user"})
    audit.record("e" * 200, detail={"k": "v" * 2000})
    with session_factory() as s:
        rows = s.scalars(select(AuditLogRow).order_by(AuditLogRow.id)).all()
    assert rows[0].user_id == "id-1"
    assert rows[0].detail == {"role": "user"}
    assert rows[0].at.tzinfo is not None
    assert len(rows[1].event) == 64
    assert rows[1].detail == {"truncated": True}


def test_audit_log_unknown_user_id_is_a_generic_error(
    session_factory: sessionmaker[Session],
) -> None:
    audit = SqlAlchemyAuditLog(session_factory, SystemClock())
    with pytest.raises(DataAccessError):
        audit.record("x", user_id="does-not-exist")
