"""Passwords never reach the database, logs or error messages in clear text."""

import logging
import sqlite3
from pathlib import Path

import pytest
from app.adapters.persistence.audit_log import SqlAlchemyAuditLog
from app.adapters.persistence.user_repository import SqlAlchemyUserRepository
from app.adapters.security.argon2_hasher import Argon2Hasher
from app.adapters.security.system_clock import SystemClock
from app.domain.password_policy import PasswordPolicyError
from app.domain.user import UsernameAlreadyExistsError
from app.services.user_service import UserService
from sqlalchemy.orm import Session, sessionmaker

PASSPHRASE = "Tr0ub4dor&3-unique-marker"


def _service(sf: sessionmaker[Session], hasher: Argon2Hasher) -> UserService:
    clock = SystemClock()
    return UserService(SqlAlchemyUserRepository(sf), hasher, SqlAlchemyAuditLog(sf, clock), clock)


def test_password_stored_only_as_argon2id_hash(
    session_factory: sessionmaker[Session], migrated_url: str, fast_hasher: Argon2Hasher
) -> None:
    _service(session_factory, fast_hasher).create_user("alice", PASSPHRASE)
    db_file = Path(migrated_url.removeprefix("sqlite:///"))
    with sqlite3.connect(db_file) as conn:
        (stored,) = conn.execute("SELECT password_hash FROM users").fetchone()
        dump = "\n".join(conn.iterdump())
    assert stored.startswith("$argon2id$")
    assert PASSPHRASE not in dump
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_file) + suffix)
        if side.exists():
            assert PASSPHRASE.encode() not in side.read_bytes()


def test_password_not_in_logs_or_errors(
    session_factory: sessionmaker[Session],
    fast_hasher: Argon2Hasher,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service(session_factory, fast_hasher)
    with caplog.at_level(logging.DEBUG):
        service.create_user("alice", PASSPHRASE)
        with pytest.raises(UsernameAlreadyExistsError) as dup:
            service.create_user("alice", PASSPHRASE)
        with pytest.raises(PasswordPolicyError) as weak:
            service.create_user("bob", "weak-pw")
    assert PASSPHRASE not in caplog.text
    assert PASSPHRASE not in str(dup.value)
    assert "weak-pw" not in str(weak.value)
    assert "weak-pw" not in caplog.text


def test_audit_detail_has_no_secrets(
    session_factory: sessionmaker[Session], migrated_url: str, fast_hasher: Argon2Hasher
) -> None:
    service = _service(session_factory, fast_hasher)
    service.create_user("alice", PASSPHRASE)
    service.reset_password("alice", PASSPHRASE + "-new")
    with sqlite3.connect(Path(migrated_url.removeprefix("sqlite:///"))) as conn:
        rows = conn.execute("SELECT event, detail FROM audit_log").fetchall()
    assert [r[0] for r in rows] == ["user.created", "user.password_reset"]
    assert all("argon2" not in (r[1] or "") and PASSPHRASE not in (r[1] or "") for r in rows)
