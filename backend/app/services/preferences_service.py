"""Use cases: read and update the user's reading preferences."""

from app.domain.preferences import Preferences
from app.domain.user import UserNotFoundError
from app.ports.preferences_repository import PreferencesRepository


class PreferencesService:
    def __init__(self, repo: PreferencesRepository) -> None:
        self._repo = repo

    def get(self, user_id: str) -> Preferences:
        prefs = self._repo.get(user_id)
        if prefs is None:
            raise UserNotFoundError("user not found")
        return prefs

    def update(self, user_id: str, preferences: Preferences) -> Preferences:
        if not self._repo.set(user_id, preferences):
            raise UserNotFoundError("user not found")
        return preferences
