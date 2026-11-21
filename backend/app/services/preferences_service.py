"""Use cases: read and update the user's reading preferences."""

from dataclasses import replace

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

    def patch(
        self,
        user_id: str,
        preferences: Preferences,
        *,
        book_font_scale: int | None = None,
        book_theme: str | None = None,
    ) -> Preferences:
        """Like `update`, but a book setting that is not given keeps what is already saved (so a
        client that only knows `theme` and `reading_direction` never resets the reader settings).

        The read-then-write is not atomic: two simultaneous PUTs of the same user may overwrite one
        another (last write wins, like the rest of the preferences; ADR 0013)."""
        current = self.get(user_id)
        merged = replace(
            preferences,
            book_font_scale=current.book_font_scale if book_font_scale is None else book_font_scale,
            book_theme=current.book_theme if book_theme is None else book_theme,
        )
        return self.update(user_id, merged)
