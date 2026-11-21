"""Per-user reading preferences. Pure domain."""

from dataclasses import dataclass

from app.domain.errors import DomainError

THEMES = ("system", "light", "dark")
READING_DIRECTIONS = ("rtl", "ltr", "vertical")


class InvalidPreferences(DomainError):  # noqa: N818
    """A preference value is not one of the allowed options."""


@dataclass(frozen=True, slots=True)
class Preferences:
    theme: str
    reading_direction: str

    def __post_init__(self) -> None:
        if self.theme not in THEMES or self.reading_direction not in READING_DIRECTIONS:
            raise InvalidPreferences
