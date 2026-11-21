"""User preferences port (interface only)."""

from typing import Protocol

from app.domain.preferences import Preferences


class PreferencesRepository(Protocol):
    def get(self, user_id: str) -> Preferences | None:
        """None when the user does not exist."""
        ...

    def set(self, user_id: str, preferences: Preferences) -> bool:
        """Targeted write of the preference columns only. False when the user does not exist."""
        ...
