import json
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import AuditLogRow
from app.domain.errors import DataAccessError
from app.ports.audit_log import AuditDetail
from app.ports.clock import Clock

MAX_EVENT_LENGTH = 64
MAX_IP_LENGTH = 45
MAX_DETAIL_BYTES = 512


class SqlAlchemyAuditLog:
    def __init__(self, session_factory: sessionmaker[Session], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def record(
        self,
        event: str,
        *,
        user_id: str | None = None,
        ip: str | None = None,
        detail: AuditDetail | None = None,
    ) -> None:
        stored: dict[str, str | int | bool] | None = None
        if detail:
            stored = dict(detail)
            if len(json.dumps(stored).encode()) > MAX_DETAIL_BYTES:
                stored = {"truncated": True}
        try:
            with self._session_factory() as session, session.begin():
                session.add(
                    AuditLogRow(
                        at=self._clock.now(),
                        event=event[:MAX_EVENT_LENGTH],
                        user_id=user_id,
                        ip=None if ip is None else ip[:MAX_IP_LENGTH],
                        detail=stored,
                    )
                )
        except SQLAlchemyError:
            raise DataAccessError("database error") from None

    def purge(self, before: datetime) -> int:
        try:
            with self._session_factory() as session, session.begin():
                result = session.execute(delete(AuditLogRow).where(AuditLogRow.at < before))
                return int(result.rowcount or 0)  # type: ignore[attr-defined]
        except SQLAlchemyError:
            raise DataAccessError("database error") from None
