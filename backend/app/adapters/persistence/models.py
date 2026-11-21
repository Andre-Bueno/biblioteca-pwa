"""ORM models. The schema itself is owned by Alembic migrations (`backend/migrations`)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Stores timezone-aware datetimes as naive UTC (SQLite has no tz) and returns aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool]
    theme_pref: Mapped[str] = mapped_column(String(16))
    # server_default: inserts that do not mention it (user creation) get 'rtl' from the database.
    reading_direction: Mapped[str] = mapped_column(String(16), server_default="rtl")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    password_changed_at: Mapped[datetime] = mapped_column(UTCDateTime)


class RefreshTokenRow(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    family_id: Mapped[str] = mapped_column(String(36))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256 hex, never raw
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(45))


class LoginAttemptRow(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64))
    attempted_at: Mapped[datetime] = mapped_column(UTCDateTime)
    success: Mapped[bool]


class SeriesRow(Base):
    __tablename__ = "series"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    sort_title: Mapped[str] = mapped_column(String(255))
    # Library-relative folder; server-side only. NULL = standalone series (loose root file).
    folder_rel_path: Mapped[str | None] = mapped_column(String(1024), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    description_lang: Mapped[str | None] = mapped_column(String(16))
    metadata_source: Mapped[str | None] = mapped_column(String(32))
    external_id: Mapped[str | None] = mapped_column(String(128))
    metadata_state: Mapped[str] = mapped_column(String(16), server_default="none")
    # Relative to the data directory (never absolute); filled by the metadata step.
    cover_path: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Added by 0006. `source_url` is built server-side (https page of the match); no remote cover
    # URL is ever stored.
    source_url: Mapped[str | None] = mapped_column(String(512))
    metadata_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    title_original: Mapped[str | None] = mapped_column(String(255))
    # Added by 0007: attribution of the description (CHECK in the migration).
    description_origin: Mapped[str | None] = mapped_column(String(16))
    description_source_name: Mapped[str | None] = mapped_column(String(64))
    description_source_url: Mapped[str | None] = mapped_column(String(512))


class ItemRow(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(255))
    rel_path: Mapped[str] = mapped_column(String(1024), unique=True)
    format: Mapped[str] = mapped_column(String(16))
    page_count: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    mtime_ns: Mapped[int] = mapped_column(BigInteger)
    added_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    missing: Mapped[bool]
    series_id: Mapped[str | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), index=True
    )
    chapter_number: Mapped[float | None] = mapped_column(Float)


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime)
    event: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    ip: Mapped[str | None] = mapped_column(String(45))
    detail: Mapped[Any | None] = mapped_column(JSON)


class ReadingProgressRow(Base):
    __tablename__ = "reading_progress"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[str] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    locator: Mapped[int] = mapped_column(Integer)
    percent: Mapped[float] = mapped_column(Float)
    finished: Mapped[bool]
    device_id: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
