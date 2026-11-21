from datetime import datetime, timedelta

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import RefreshTokenRow
from app.domain.auth import RefreshToken
from app.domain.errors import DataAccessError


def _to_domain(row: RefreshTokenRow) -> RefreshToken:
    return RefreshToken(
        id=row.id,
        user_id=row.user_id,
        family_id=row.family_id,
        token_hash=row.token_hash,
        created_at=row.created_at,
        expires_at=row.expires_at,
        used_at=row.used_at,
        revoked_at=row.revoked_at,
    )


class SqlAlchemyRefreshTokenRepository:
    """Each call is its own transaction; driver errors become a generic DataAccessError."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, token: RefreshToken) -> None:
        try:
            with self._session_factory() as session, session.begin():
                session.add(
                    RefreshTokenRow(
                        id=token.id,
                        user_id=token.user_id,
                        family_id=token.family_id,
                        token_hash=token.token_hash,
                        created_at=token.created_at,
                        expires_at=token.expires_at,
                        used_at=token.used_at,
                        revoked_at=token.revoked_at,
                    )
                )
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        try:
            with self._session_factory() as session:
                row = session.scalars(
                    select(RefreshTokenRow).where(RefreshTokenRow.token_hash == token_hash)
                ).first()
                return None if row is None else _to_domain(row)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def mark_used(self, token_id: str, at: datetime) -> bool:
        try:
            with self._session_factory() as session, session.begin():
                result = session.execute(
                    update(RefreshTokenRow)
                    .where(
                        RefreshTokenRow.id == token_id,
                        RefreshTokenRow.used_at.is_(None),
                        RefreshTokenRow.revoked_at.is_(None),
                    )
                    .values(used_at=at)
                )
                return result.rowcount == 1  # type: ignore[attr-defined,no-any-return]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def rotate(
        self, stored_id: str, successor: RefreshToken, at: datetime, grace: timedelta
    ) -> bool:
        try:
            with self._session_factory() as session, session.begin():
                # The guarded UPDATE runs first so the write lock is taken before anything is read:
                # exactly one concurrent caller sees rowcount == 1.
                result = session.execute(
                    update(RefreshTokenRow)
                    .where(
                        RefreshTokenRow.id == stored_id,
                        RefreshTokenRow.used_at.is_(None),
                        RefreshTokenRow.revoked_at.is_(None),
                    )
                    .values(used_at=at)
                )
                if result.rowcount != 1:  # type: ignore[attr-defined]
                    row = session.execute(
                        select(RefreshTokenRow.used_at, RefreshTokenRow.revoked_at).where(
                            RefreshTokenRow.id == stored_id
                        )
                    ).first()
                    if row is None or row.revoked_at is not None or row.used_at is None:
                        return False
                    if grace <= timedelta(0) or at - row.used_at > grace:
                        return False
                session.add(
                    RefreshTokenRow(
                        id=successor.id,
                        user_id=successor.user_id,
                        family_id=successor.family_id,
                        token_hash=successor.token_hash,
                        created_at=successor.created_at,
                        expires_at=successor.expires_at,
                        used_at=successor.used_at,
                        revoked_at=successor.revoked_at,
                    )
                )
                return True
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def revoke_family(self, family_id: str, at: datetime) -> None:
        try:
            with self._session_factory() as session, session.begin():
                session.execute(
                    update(RefreshTokenRow)
                    .where(
                        RefreshTokenRow.family_id == family_id,
                        RefreshTokenRow.revoked_at.is_(None),
                    )
                    .values(revoked_at=at)
                )
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def revoke_all_for_user(self, user_id: str, at: datetime) -> None:
        try:
            with self._session_factory() as session, session.begin():
                session.execute(
                    update(RefreshTokenRow)
                    .where(
                        RefreshTokenRow.user_id == user_id,
                        RefreshTokenRow.revoked_at.is_(None),
                    )
                    .values(revoked_at=at)
                )
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def family_started_at(self, family_id: str) -> datetime | None:
        try:
            with self._session_factory() as session:
                return session.scalar(
                    select(func.min(RefreshTokenRow.created_at)).where(
                        RefreshTokenRow.family_id == family_id
                    )
                )
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def is_family_active(self, family_id: str, user_id: str) -> bool:
        try:
            with self._session_factory() as session:
                found = session.scalar(
                    select(
                        exists().where(
                            RefreshTokenRow.family_id == family_id,
                            RefreshTokenRow.user_id == user_id,
                            RefreshTokenRow.revoked_at.is_(None),
                        )
                    )
                )
                return bool(found)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def purge_dead_families(self, before: datetime) -> int:
        try:
            with self._session_factory() as session, session.begin():
                alive = (
                    select(RefreshTokenRow.family_id)
                    .group_by(RefreshTokenRow.family_id)
                    .having(func.max(RefreshTokenRow.expires_at) >= before)
                )
                result = session.execute(
                    delete(RefreshTokenRow).where(RefreshTokenRow.family_id.not_in(alive))
                )
                return int(result.rowcount)  # type: ignore[attr-defined]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None
