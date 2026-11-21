"""HTTP schemas for progress and preferences. Strict, no extra fields, bounded values."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.library_schemas import ItemOut
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
    theme: Literal["system", "light", "dark"]
    reading_direction: Literal["rtl", "ltr", "vertical"]

    def to_domain(self) -> Preferences:
        return Preferences(theme=self.theme, reading_direction=self.reading_direction)


class PreferencesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme: str
    reading_direction: str

    @classmethod
    def from_domain(cls, p: Preferences) -> "PreferencesOut":
        return cls(theme=p.theme, reading_direction=p.reading_direction)
