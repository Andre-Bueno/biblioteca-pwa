import hashlib
import hmac
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import LoginAttemptRow
from app.domain.errors import DataAccessError
from app.ports.login_attempt_store import AttemptScope

FINGERPRINT_LENGTH = 16


class SqlAlchemyLoginAttemptStore:
    """Login attempts in `login_attempts`. IPs and usernames are stored only as
    HMAC-SHA256(key, "<scope>\\0<value>") (hex): the table is useless for enumerating accounts
    or locating clients if it leaks, and a hash from one scope never matches another."""

    def __init__(self, session_factory: sessionmaker[Session], hash_key: bytes) -> None:
        if len(hash_key) < 16:
            raise ValueError("hash key too short")
        self._session_factory = session_factory
        self._hash_key = hash_key

    def _hash(self, scope: AttemptScope, key: str) -> str:
        return hmac.new(self._hash_key, f"{scope}\0{key}".encode(), hashlib.sha256).hexdigest()

    def fingerprint(self, scope: AttemptScope, key: str) -> str:
        return self._hash(scope, key)[:FINGERPRINT_LENGTH]

    def record(self, scope: AttemptScope, key: str, at: datetime, *, success: bool) -> None:
        try:
            with self._session_factory() as session, session.begin():
                session.add(
                    LoginAttemptRow(
                        scope=scope,
                        key_hash=self._hash(scope, key),
                        attempted_at=at,
                        success=success,
                    )
                )
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def reserve_failures(self, keys: Sequence[tuple[AttemptScope, str]], at: datetime) -> list[int]:
        try:
            with self._session_factory() as session, session.begin():
                rows = [
                    LoginAttemptRow(
                        scope=scope, key_hash=self._hash(scope, key), attempted_at=at, success=False
                    )
                    for scope, key in keys
                ]
                session.add_all(rows)
                session.flush()
                return [row.id for row in rows]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def release(self, reservation_ids: Sequence[int]) -> None:
        if not reservation_ids:
            return
        try:
            with self._session_factory() as session, session.begin():
                session.execute(
                    delete(LoginAttemptRow).where(
                        LoginAttemptRow.id.in_(list(reservation_ids)),
                        LoginAttemptRow.success.is_(False),
                    )
                )
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def failures_since_last_success(
        self, scope: AttemptScope, key: str, since: datetime
    ) -> list[datetime]:
        key_hash = self._hash(scope, key)
        same_key = and_(LoginAttemptRow.scope == scope, LoginAttemptRow.key_hash == key_hash)
        try:
            with self._session_factory() as session:
                last_success_id = (
                    session.scalar(
                        select(func.max(LoginAttemptRow.id)).where(
                            same_key, LoginAttemptRow.success.is_(True)
                        )
                    )
                    or 0
                )
                rows = session.scalars(
                    select(LoginAttemptRow.attempted_at)
                    .where(
                        same_key,
                        LoginAttemptRow.success.is_(False),
                        LoginAttemptRow.id > last_success_id,
                        LoginAttemptRow.attempted_at > since,
                    )
                    .order_by(LoginAttemptRow.id)
                ).all()
                return sorted(rows)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def last_success_at(self, scope: AttemptScope, key: str) -> datetime | None:
        try:
            with self._session_factory() as session:
                return session.scalar(
                    select(func.max(LoginAttemptRow.attempted_at)).where(
                        LoginAttemptRow.scope == scope,
                        LoginAttemptRow.key_hash == self._hash(scope, key),
                        LoginAttemptRow.success.is_(True),
                    )
                )
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def purge(self, failures_before: datetime, successes_before: datetime) -> int:
        try:
            with self._session_factory() as session, session.begin():
                result = session.execute(
                    delete(LoginAttemptRow).where(
                        (
                            LoginAttemptRow.success.is_(False)
                            & (LoginAttemptRow.attempted_at < failures_before)
                        )
                        | (
                            LoginAttemptRow.success.is_(True)
                            & (LoginAttemptRow.attempted_at < successes_before)
                        )
                    )
                )
                return int(result.rowcount)  # type: ignore[attr-defined]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None
