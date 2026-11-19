from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 32
MIN_SECRET_DISTINCT_CHARS = 12
MAX_REPEATED_BLOCK = 8


def _is_repeated_block(value: str) -> bool:
    """True if value is a block of <= MAX_REPEATED_BLOCK chars repeated (last copy may be cut)."""
    return any(
        (value[:n] * (len(value) // n + 1))[: len(value)] == value
        for n in range(1, MAX_REPEATED_BLOCK + 1)
    )


class Settings(BaseSettings):
    """Application settings, read from environment variables (never committed).

    `hide_input_in_errors` keeps secret values out of validation errors (and thus logs).
    Client IP behind a proxy is decided solely by uvicorn's FORWARDED_ALLOW_IPS.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # No default on purpose: the app must refuse to start without a real secret.
    SECRET_KEY: str = Field(min_length=MIN_SECRET_LENGTH)
    ALLOWED_ORIGINS: list[str] = Field(default_factory=list)
    COOKIE_SECURE: bool = True
    LIBRARY_PATH: Path = Path("/library")
    DATABASE_URL: str = "sqlite:///./data/app.db"

    @field_validator("SECRET_KEY")
    @classmethod
    def _reject_weak_secret(cls, value: str) -> str:
        # Messages must never include the value itself.
        if value != value.strip():
            raise ValueError("SECRET_KEY must not have leading or trailing whitespace")
        if len(set(value)) < MIN_SECRET_DISTINCT_CHARS:
            raise ValueError(
                f"SECRET_KEY must contain at least {MIN_SECRET_DISTINCT_CHARS} distinct characters"
            )
        if _is_repeated_block(value):
            raise ValueError(
                f"SECRET_KEY must not be a block of {MAX_REPEATED_BLOCK} or fewer characters "
                "repeated"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
