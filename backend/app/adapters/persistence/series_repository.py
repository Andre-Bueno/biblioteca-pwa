"""SQLAlchemy implementation of `SeriesRepository`.

Statements use bound parameters; the title search escapes LIKE wildcards. Reading figures
(`read_chapters`, `last_item_id`) always filter by the `user_id` given (it comes from the token).
A series is visible only through an inner join with its active (non-missing) items.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.item_repository import LIKE_ESCAPE, escape_like
from app.adapters.persistence.item_repository import _to_domain as _item_to_domain
from app.adapters.persistence.models import ItemRow, ReadingProgressRow, SeriesRow
from app.domain.errors import DataAccessError
from app.domain.item import Item
from app.domain.metadata import MetadataUpdate
from app.domain.series import Series, SeriesSummary, series_kind, sort_title
from app.ports.clock import Clock


def _to_domain(row: SeriesRow) -> Series:
    return Series(
        id=row.id,
        title=row.title,
        sort_title=row.sort_title,
        folder_rel_path=row.folder_rel_path,
        created_at=row.created_at,
        updated_at=row.updated_at,
        description=row.description,
        description_lang=row.description_lang,
        metadata_source=row.metadata_source,
        external_id=row.external_id,
        metadata_state=row.metadata_state,
        cover_path=row.cover_path,
        source_url=row.source_url,
        title_original=row.title_original,
        metadata_checked_at=row.metadata_checked_at,
        description_origin=row.description_origin,
        description_source_name=row.description_source_name,
        description_source_url=row.description_source_url,
    )


class SqlAlchemySeriesRepository:
    """Each call is its own transaction; driver errors become a generic `DataAccessError`."""

    def __init__(self, session_factory: sessionmaker[Session], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def _new_row(self, folder_rel_path: str | None, title: str) -> SeriesRow:
        now = self._clock.now()
        return SeriesRow(
            id=str(uuid.uuid4()),
            title=title,
            sort_title=sort_title(title),
            folder_rel_path=folder_rel_path,
            metadata_state="none",
            created_at=now,
            updated_at=now,
        )

    def ensure_for_folder(self, folder_rel_path: str, title: str) -> Series:
        stmt = select(SeriesRow).where(SeriesRow.folder_rel_path == folder_rel_path)
        for _attempt in range(2):
            try:
                with self._session_factory() as session, session.begin():
                    row = session.scalars(stmt).first()
                    if row is None:
                        row = self._new_row(folder_rel_path, title)
                        session.add(row)
                    return _to_domain(row)
            except IntegrityError:
                continue  # lost a race with another writer: the row exists now, read it again
            except SQLAlchemyError:
                raise DataAccessError("database error") from None
        raise DataAccessError("database error")

    def create_standalone(self, title: str) -> Series:
        try:
            with self._session_factory() as session, session.begin():
                row = self._new_row(None, title)
                session.add(row)
                return _to_domain(row)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def get(self, series_id: str) -> Series | None:
        has_active = (
            select(ItemRow.id)
            .where(ItemRow.series_id == SeriesRow.id, ItemRow.missing.is_(False))
            .exists()
        )
        try:
            with self._session_factory() as session:
                row = session.scalars(
                    select(SeriesRow).where(SeriesRow.id == series_id, has_active)
                ).first()
                return None if row is None else _to_domain(row)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def list_summaries(
        self, user_id: str, query: str | None, offset: int, limit: int
    ) -> list[SeriesSummary]:
        stmt = (
            select(
                SeriesRow,
                func.count(ItemRow.id),
                func.max(ItemRow.page_count),
                func.min(ItemRow.type),
                func.max(ItemRow.type),
            )
            .join(ItemRow, ItemRow.series_id == SeriesRow.id)
            .where(ItemRow.missing.is_(False))
        )
        if query:
            if "\x00" in query:
                return []  # SQLite LIKE stops at NUL; titles never contain one: nothing matches
            pattern = f"%{escape_like(query)}%"
            stmt = stmt.where(SeriesRow.title.like(pattern, escape=LIKE_ESCAPE))
        stmt = (
            stmt.group_by(SeriesRow.id)
            .order_by(SeriesRow.sort_title, SeriesRow.id)
            .offset(offset)
            .limit(limit)
        )
        try:
            with self._session_factory() as session:
                rows = session.execute(stmt).all()
                ids = [row[0].id for row in rows]
                read, last = self._reading(session, user_id, ids)
                return [
                    SeriesSummary(
                        series=_to_domain(series),
                        chapter_count=count,
                        has_cover=(pages or 0) > 0,
                        read_chapters=read.get(series.id, 0),
                        last_item_id=last.get(series.id),
                        kind=series_kind([lowest] if lowest == highest else [lowest, highest]),
                    )
                    for series, count, pages, lowest, highest in rows
                ]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    @staticmethod
    def _reading(
        session: Session, user_id: str, series_ids: Sequence[str]
    ) -> tuple[dict[str, int], dict[str, str]]:
        """(finished chapters per series, most recently read item per series) for one user."""
        if not series_ids:
            return {}, {}
        base = (
            select(ItemRow.series_id)
            .join(ReadingProgressRow, ReadingProgressRow.item_id == ItemRow.id)
            .where(
                ReadingProgressRow.user_id == user_id,
                ItemRow.missing.is_(False),
                ItemRow.series_id.in_(series_ids),
            )
        )
        finished = session.execute(
            base.add_columns(func.count())
            .where(ReadingProgressRow.finished.is_(True))
            .group_by(ItemRow.series_id)
        )
        read = {sid: count for sid, count in finished}  # noqa: C416 - Row is not a 2-tuple
        last: dict[str, str] = {}
        newest = base.add_columns(ReadingProgressRow.item_id).order_by(
            ReadingProgressRow.updated_at.desc(), ReadingProgressRow.item_id
        )
        for sid, item_id in session.execute(newest):
            last.setdefault(sid, item_id)
        return read, last

    def list_chapters(self, series_id: str) -> list[Item]:
        stmt = select(ItemRow).where(ItemRow.series_id == series_id, ItemRow.missing.is_(False))
        try:
            with self._session_factory() as session:
                return [_item_to_domain(row) for row in session.scalars(stmt)]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def list_for_enrichment(
        self, states: Sequence[str], not_found_before: datetime | None, limit: int
    ) -> list[Series]:
        # Any format counts (no rule by item type): the series needs at least one active item.
        has_active = (
            select(ItemRow.id)
            .where(ItemRow.series_id == SeriesRow.id, ItemRow.missing.is_(False))
            .exists()
        )
        stmt = select(SeriesRow).where(SeriesRow.metadata_state.in_(list(states)), has_active)
        if not_found_before is not None:
            stmt = stmt.where(
                or_(
                    SeriesRow.metadata_state != "not_found",
                    SeriesRow.metadata_checked_at.is_(None),
                    SeriesRow.metadata_checked_at < not_found_before,
                )
            )
        stmt = stmt.order_by(
            SeriesRow.metadata_checked_at.is_not(None), SeriesRow.metadata_checked_at, SeriesRow.id
        ).limit(limit)
        try:
            with self._session_factory() as session:
                return [_to_domain(row) for row in session.scalars(stmt)]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def update_metadata(
        self, series_id: str, update: MetadataUpdate, allowed_states: Sequence[str]
    ) -> bool:
        values: dict[str, object] = {
            "metadata_state": update.state,
            "description": update.description,
            "description_lang": update.description_lang,
            "metadata_source": update.source,
            "external_id": update.external_id,
            "source_url": update.source_url,
            "title_original": update.title_original,
            "cover_path": update.cover_path,
            "metadata_checked_at": update.checked_at,
            "description_origin": update.description_origin,
            "description_source_name": update.description_source_name,
            "description_source_url": update.description_source_url,
            "updated_at": self._clock.now(),
        }
        if update.title is not None:
            values["title"] = update.title
            values["sort_title"] = sort_title(update.title)
        stmt = (
            sql_update(SeriesRow)
            .where(SeriesRow.id == series_id, SeriesRow.metadata_state.in_(list(allowed_states)))
            .values(**values)
        )
        try:
            with self._session_factory() as session, session.begin():
                return int(session.execute(stmt).rowcount) > 0  # type: ignore[attr-defined]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None
