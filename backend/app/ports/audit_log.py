from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

AuditDetail = Mapping[str, str | int | bool]


class AuditLog(Protocol):
    def record(
        self,
        event: str,
        *,
        user_id: str | None = None,
        ip: str | None = None,
        detail: AuditDetail | None = None,
    ) -> None:
        """Append an event. `detail` must be short and free of secrets (passwords, tokens)."""
        ...

    def purge(self, before: datetime) -> int:
        """Delete events older than `before` (retention); return how many were removed."""
        ...
