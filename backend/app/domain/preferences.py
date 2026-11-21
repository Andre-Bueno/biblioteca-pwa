"""Per-user reading preferences. Pure domain."""

from dataclasses import dataclass

from app.domain.book import (
    BOOK_THEMES,
    DEFAULT_BOOK_THEME,
    DEFAULT_FONT_SCALE,
    MAX_FONT_SCALE,
    MIN_FONT_SCALE,
)
from app.domain.errors import DomainError

THEMES = ("system", "light", "dark")
READING_DIRECTIONS = ("rtl", "ltr", "vertical")


class InvalidPreferences(DomainError):  # noqa: N818
    """A preference value is not one of the allowed options."""


def valid_book_font_scale(value: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and MIN_FONT_SCALE <= value <= MAX_FONT_SCALE
    )


@dataclass(frozen=True, slots=True)
class Preferences:
    theme: str
    reading_direction: str
    book_font_scale: int = DEFAULT_FONT_SCALE  # 80..200 (percent)
    book_theme: str = DEFAULT_BOOK_THEME  # auto | light | dark | sepia

    def __post_init__(self) -> None:
        if (
            self.theme not in THEMES
            or self.reading_direction not in READING_DIRECTIONS
            or not valid_book_font_scale(self.book_font_scale)
            or self.book_theme not in BOOK_THEMES
        ):
            raise InvalidPreferences
