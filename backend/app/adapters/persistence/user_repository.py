from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import UserRow
from app.domain.errors import DataAccessError
from app.domain.user import (
    Role,
    User,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)


def _to_domain(row: UserRow) -> User:
    return User(
        id=row.id,
        username=row.username,
        password_hash=row.password_hash,
        role=Role(row.role),
        is_active=row.is_active,
        theme_pref=row.theme_pref,
        created_at=row.created_at,
        updated_at=row.updated_at,
        password_changed_at=row.password_changed_at,
    )


class SqlAlchemyUserRepository:
    """Each call is its own transaction. Driver errors are replaced by a generic DataAccessError
    (`from None`) so statements/parameters never reach logs or tracebacks."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, user: User) -> None:
        try:
            with self._session_factory() as session, session.begin():
                session.add(
                    UserRow(
                        id=user.id,
                        username=user.username,
                        password_hash=user.password_hash,
                        role=user.role.value,
                        is_active=user.is_active,
                        theme_pref=user.theme_pref,
                        created_at=user.created_at,
                        updated_at=user.updated_at,
                        password_changed_at=user.password_changed_at,
                    )
                )
        except IntegrityError:
            raise UsernameAlreadyExistsError("username already exists") from None
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    # Writes are targeted UPDATEs (never "write back the whole object read earlier"): a slow
    # Argon2 step between read and write must not overwrite a concurrent change such as a
    # deactivation or password reset made by the CLI.

    def replace_password_hash(
        self,
        user_id: str,
        *,
        expected_hash: str,
        new_hash: str,
        now: datetime,
        password_changed: bool,
    ) -> bool:
        values: dict[str, Any] = {"password_hash": new_hash, "updated_at": now}
        if password_changed:
            values["password_changed_at"] = now
        try:
            with self._session_factory() as session, session.begin():
                result = session.execute(
                    update(UserRow)
                    .where(
                        UserRow.id == user_id,
                        UserRow.is_active.is_(True),
                        UserRow.password_hash == expected_hash,
                    )
                    .values(**values)
                )
                return result.rowcount == 1  # type: ignore[attr-defined,no-any-return]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def set_password_hash(self, user_id: str, new_hash: str, now: datetime) -> None:
        try:
            with self._session_factory() as session, session.begin():
                result = session.execute(
                    update(UserRow)
                    .where(UserRow.id == user_id)
                    .values(password_hash=new_hash, updated_at=now, password_changed_at=now)
                )
                if result.rowcount != 1:  # type: ignore[attr-defined]
                    raise UserNotFoundError("user not found")
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def deactivate(self, user_id: str, now: datetime) -> None:
        try:
            with self._session_factory() as session, session.begin():
                result = session.execute(
                    update(UserRow)
                    .where(UserRow.id == user_id)
                    .values(is_active=False, updated_at=now)
                )
                if result.rowcount != 1:  # type: ignore[attr-defined]
                    raise UserNotFoundError("user not found")
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def get_by_id(self, user_id: str) -> User | None:
        try:
            with self._session_factory() as session:
                row = session.get(UserRow, user_id)
                return None if row is None else _to_domain(row)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def get_by_username(self, username: str) -> User | None:
        try:
            with self._session_factory() as session:
                row = session.scalars(
                    select(UserRow).where(func.lower(UserRow.username) == username.lower())
                ).first()
                return None if row is None else _to_domain(row)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def list_all(self) -> list[User]:
        try:
            with self._session_factory() as session:
                rows = session.scalars(select(UserRow).order_by(UserRow.username)).all()
                return [_to_domain(r) for r in rows]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None
