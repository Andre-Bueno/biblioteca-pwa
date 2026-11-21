"""SQLAlchemy implementation of `PreferencesRepository` (columns of `users`)."""

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import UserRow
from app.domain.errors import DataAccessError
from app.domain.preferences import Preferences


class SqlAlchemyPreferencesRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, user_id: str) -> Preferences | None:
        try:
            with self._session_factory() as session:
                row = session.execute(
                    select(
                        UserRow.theme_pref,
                        UserRow.reading_direction,
                        UserRow.book_font_scale,
                        UserRow.book_theme,
                    ).where(UserRow.id == user_id)
                ).first()
                return None if row is None else Preferences(row[0], row[1], row[2], row[3])
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def set(self, user_id: str, preferences: Preferences) -> bool:
        # Targeted UPDATE of the four preference columns only (never the whole user).
        try:
            with self._session_factory() as session, session.begin():
                result = session.execute(
                    update(UserRow)
                    .where(UserRow.id == user_id)
                    .values(
                        theme_pref=preferences.theme,
                        reading_direction=preferences.reading_direction,
                        book_font_scale=preferences.book_font_scale,
                        book_theme=preferences.book_theme,
                    )
                )
                return result.rowcount == 1  # type: ignore[attr-defined,no-any-return]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None
