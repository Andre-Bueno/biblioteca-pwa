"""SQLAlchemy implementation of `ProgressRepository`.

Every statement filters by the `user_id` it is given (it comes from the authenticated token, never
from the client). The write is a single `INSERT ... ON CONFLICT DO UPDATE`, so two devices saving at
the same time can never create duplicates or fail: the last statement to run wins.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.item_repository import _to_domain as _item_to_domain
from app.adapters.persistence.models import ItemRow, ReadingProgressRow, SeriesRow
from app.domain.errors import DataAccessError
from app.domain.progress import ContinueEntry, Progress

_CHUNK = 500  # stays far below SQLite's bound-variable limit


def _utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; every stored instant is UTC, so say so explicitly."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _to_domain(row: ReadingProgressRow) -> Progress:
    return Progress(
        user_id=row.user_id,
        item_id=row.item_id,
        locator=row.locator,
        percent=row.percent,
        finished=row.finished,
        updated_at=_utc(row.updated_at),
        device_id=row.device_id,
    )


def _upsert_statement(dialect_name: str, values: dict[str, Any]) -> Any:
    insert = postgresql.insert if dialect_name == "postgresql" else sqlite.insert
    stmt = insert(ReadingProgressRow).values(**values)
    changes = {k: v for k, v in values.items() if k not in ("user_id", "item_id")}
    return stmt.on_conflict_do_update(index_elements=["user_id", "item_id"], set_=changes)


class SqlAlchemyProgressRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def upsert(self, progress: Progress) -> None:
        values: dict[str, Any] = {
            "user_id": progress.user_id,
            "item_id": progress.item_id,
            "locator": progress.locator,
            "percent": progress.percent,
            "finished": progress.finished,
            "device_id": progress.device_id,
            "updated_at": progress.updated_at,
        }
        try:
            with self._session_factory() as session, session.begin():
                session.execute(_upsert_statement(session.get_bind().dialect.name, values))
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def get(self, user_id: str, item_id: str) -> Progress | None:
        try:
            with self._session_factory() as session:
                row = session.get(ReadingProgressRow, (user_id, item_id))
                return None if row is None else _to_domain(row)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def delete(self, user_id: str, item_id: str) -> None:
        try:
            with self._session_factory() as session, session.begin():
                session.execute(
                    sa_delete(ReadingProgressRow).where(
                        ReadingProgressRow.user_id == user_id,
                        ReadingProgressRow.item_id == item_id,
                    )
                )
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def list_for_items(self, user_id: str, item_ids: Sequence[str]) -> dict[str, Progress]:
        found: dict[str, Progress] = {}
        try:
            with self._session_factory() as session:
                for start in range(0, len(item_ids), _CHUNK):
                    chunk = list(item_ids[start : start + _CHUNK])
                    stmt = select(ReadingProgressRow).where(
                        ReadingProgressRow.user_id == user_id,
                        ReadingProgressRow.item_id.in_(chunk),
                    )
                    for row in session.scalars(stmt):
                        found[row.item_id] = _to_domain(row)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None
        return found

    def list_continue(self, user_id: str, limit: int) -> list[ContinueEntry]:
        stmt = (
            select(ReadingProgressRow, ItemRow, SeriesRow.id, SeriesRow.title)
            .join(ItemRow, ItemRow.id == ReadingProgressRow.item_id)
            .outerjoin(SeriesRow, SeriesRow.id == ItemRow.series_id)
            .where(
                ReadingProgressRow.user_id == user_id,
                ReadingProgressRow.finished.is_(False),
                ItemRow.missing.is_(False),
            )
            .order_by(ReadingProgressRow.updated_at.desc(), ReadingProgressRow.item_id)
            .limit(limit)
        )
        try:
            with self._session_factory() as session:
                return [
                    ContinueEntry(
                        item=_item_to_domain(item),
                        progress=_to_domain(prog),
                        series_id=series_id,
                        series_title=series_title,
                    )
                    for prog, item, series_id, series_title in session.execute(stmt)
                ]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None
