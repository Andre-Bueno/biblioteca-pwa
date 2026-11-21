"""HTTP schemas for progress and preferences. Strict, no extra fields, bounded values."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.library_schemas import ItemOut
from app.domain.book import (
    DEFAULT_BOOK_THEME,
    DEFAULT_FONT_SCALE,
    MAX_FONT_SCALE,
    MIN_FONT_SCALE,
)
from app.domain.preferences import Preferences
from app.domain.progress import ContinueEntry, Progress

MAX_LOCATOR = 2_147_483_647
DEVICE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SaveProgressRequest(_Strict):
    locator: int = Field(ge=0, le=MAX_LOCATOR)
    device_id: str | None = Field(default=None, pattern=DEVICE_ID_PATTERN)


class ProgressOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    locator: int
    percent: float
    finished: bool
    updated_at: datetime

    @classmethod
    def from_domain(cls, p: Progress) -> "ProgressOut":
        return cls(
            item_id=p.item_id,
            locator=p.locator,
            percent=p.percent,
            finished=p.finished,
            updated_at=p.updated_at,
        )


class ContinueItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: ItemOut
    series_id: str | None
    series_title: str | None
    locator: int
    percent: float
    finished: bool
    updated_at: datetime

    @classmethod
    def from_domain(cls, e: ContinueEntry) -> "ContinueItemOut":
        return cls(
            item=ItemOut.from_domain(e.item),
            series_id=e.series_id,
            series_title=e.series_title,
            locator=e.progress.locator,
            percent=e.progress.percent,
            finished=e.progress.finished,
            updated_at=e.progress.updated_at,
        )


class ContinueListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ContinueItemOut]


class PreferencesIn(_Strict):
    """The two book fields are optional: a client that omits them keeps what is saved (a PUT with
    only `theme` and `reading_direction`, as before 0008, still works). Extras are rejected."""

    theme: Literal["system", "light", "dark"]
    reading_direction: Literal["rtl", "ltr", "vertical"]
    book_font_scale: int | None = Field(default=None, ge=MIN_FONT_SCALE, le=MAX_FONT_SCALE)
    book_theme: Literal["auto", "light", "dark", "sepia"] | None = None

    def to_domain(self) -> Preferences:
        """The preferences with the book fields at their defaults when omitted. The router uses
        `PreferencesService.patch` so omitted book fields keep the saved values instead."""
        return Preferences(
            theme=self.theme,
            reading_direction=self.reading_direction,
            book_font_scale=(
                DEFAULT_FONT_SCALE if self.book_font_scale is None else self.book_font_scale
            ),
            book_theme=DEFAULT_BOOK_THEME if self.book_theme is None else self.book_theme,
        )


class PreferencesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: str
    reading_direction: str
    book_font_scale: int
    book_theme: str

    @classmethod
    def from_domain(cls, p: Preferences) -> "PreferencesOut":
        return cls(
            theme=p.theme,
            reading_direction=p.reading_direction,
            book_font_scale=p.book_font_scale,
            book_theme=p.book_theme,
        )
