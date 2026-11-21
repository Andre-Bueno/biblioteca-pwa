"""Port: ask the operator's deploy agent to update the app (interface only).

The app never touches Docker; it only sends a signed request. The destination is chosen by the
operator in configuration, never by a client."""

from typing import Protocol

from app.domain.release import UpdateRequest


class UpdateNotifier(Protocol):
    def notify(self, request: UpdateRequest) -> None:
        """Send the request. Raises `UpdateNotifyFailed` (generic: no URL, host, secret or body)
        when it was not accepted."""
        ...
