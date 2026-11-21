"""SQLAlchemy implementation of `ItemRepository`.

Every statement is built with bound parameters; the title search escapes LIKE wildcards instead of
passing user text into the pattern as-is.
"""

import builtins
from collections.abc import Collection, Iterator

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import ItemRow
from app.domain.errors import DataAccessError, ItemNotFound
from app.domain.item import Item, ItemType
from app.ports.clock import Clock

LIKE_ESCAPE = "\\"
_CHUNK = 500  # stays far below SQLite's bound-variable limit


def escape_like(text: str) -> str:
    """Make `text` match literally inside a LIKE pattern (escapes the escape char, % and _)."""
    return (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


def _to_domain(row: ItemRow) -> Item:
    return Item(
        id=row.id,
        type=ItemType(row.type),
        title=row.title,
        rel_path=row.rel_path,
        format=row.format,
        page_count=row.page_count,
        size=row.size,
        mtime_ns=row.mtime_ns,
        added_at=row.added_at,
        content_hash=row.content_hash,
        missing=row.missing,
        series_id=row.series_id,
        chapter_number=row.chapter_number,
    )


def _chunks(values: builtins.list[str]) -> Iterator[builtins.list[str]]:
    for start in range(0, len(values), _CHUNK):
        yield values[start : start + _CHUNK]


class SqlAlchemyItemRepository:
    """Each call is its own transaction; driver errors become a generic `DataAccessError`."""

    def __init__(self, session_factory: sessionmaker[Session], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def add(self, item: Item) -> None:
        now = self._clock.now()
        try:
            with self._session_factory() as session, session.begin():
                session.add(
                    ItemRow(
                        id=item.id,
                        type=item.type.value,
                        title=item.title,
                        rel_path=item.rel_path,
                        format=item.format,
                        page_count=item.page_count,
                        content_hash=item.content_hash,
                        size=item.size,
                        mtime_ns=item.mtime_ns,
                        added_at=item.added_at,
                        updated_at=now,
                        missing=item.missing,
                        series_id=item.series_id,
                        chapter_number=item.chapter_number,
                    )
                )
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def update(self, item: Item) -> None:
        now = self._clock.now()
        try:
            with self._session_factory() as session, session.begin():
                row = session.get(ItemRow, item.id)
                if row is None:
                    raise ItemNotFound
                row.type = item.type.value
                row.title = item.title
                row.format = item.format
                row.page_count = item.page_count
                row.content_hash = item.content_hash
                row.size = item.size
                row.mtime_ns = item.mtime_ns
                row.missing = item.missing
                row.series_id = item.series_id
                row.chapter_number = item.chapter_number
                row.updated_at = now
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def get(self, item_id: str) -> Item | None:
        try:
            with self._session_factory() as session:
                row = session.get(ItemRow, item_id)
                return None if row is None or row.missing else _to_domain(row)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def get_by_rel_path(self, rel_path: str) -> Item | None:
        try:
            with self._session_factory() as session:
                row = session.scalars(select(ItemRow).where(ItemRow.rel_path == rel_path)).first()
                return None if row is None else _to_domain(row)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def list(
        self, offset: int, limit: int, item_type: ItemType | None = None
    ) -> builtins.list[Item]:
        return self._page([], offset, limit, item_type)

    def search(
        self, query: str, offset: int, limit: int, item_type: ItemType | None = None
    ) -> builtins.list[Item]:
        if "\x00" in query:
            # SQLite's LIKE stops reading the pattern at a NUL, which would widen the match; titles
            # are sanitized at scan time and can never contain one, so nothing can match.
            return []
        pattern = f"%{escape_like(query)}%"
        return self._page(
            [ItemRow.title.like(pattern, escape=LIKE_ESCAPE)], offset, limit, item_type
        )

    def _page(
        self,
        conditions: builtins.list[ColumnElement[bool]],
        offset: int,
        limit: int,
        item_type: ItemType | None,
    ) -> builtins.list[Item]:
        stmt = select(ItemRow).where(ItemRow.missing.is_(False), *conditions)
        if item_type is not None:
            stmt = stmt.where(ItemRow.type == item_type.value)
        # (lower(title), id): deterministic order, so pages never overlap or skip rows.
        stmt = stmt.order_by(func.lower(ItemRow.title), ItemRow.id).offset(offset).limit(limit)
        try:
            with self._session_factory() as session:
                return [_to_domain(r) for r in session.scalars(stmt)]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def remove_missing(self, present_rel_paths: Collection[str]) -> int:
        present = set(present_rel_paths)
        now = self._clock.now()
        try:
            with self._session_factory() as session, session.begin():
                rows = session.execute(
                    select(ItemRow.id, ItemRow.rel_path).where(ItemRow.missing.is_(False))
                ).all()
                gone = [row_id for row_id, rel in rows if rel not in present]
                for chunk in _chunks(gone):
                    session.execute(
                        update(ItemRow)
                        .where(ItemRow.id.in_(chunk))
                        .values(missing=True, updated_at=now)
                    )
                return len(gone)
        except SQLAlchemyError:
            raise DataAccessError("database error") from None
