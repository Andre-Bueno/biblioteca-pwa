from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.main import create_app
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)  # avoid picking up a stray .env
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_create_app_fails_without_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        create_app()


def test_create_app_fails_with_short_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "short-key-1234")
    with pytest.raises(ValidationError):
        create_app()


@pytest.mark.parametrize(
    "key",
    [
        "a" * 64,
        "ab" * 32,
        "abcd" * 16,
        "0" * 40,
        "abcdefgh" * 4,  # 8 distinct chars, repeated block
        "Zk3!pQ9v" * 5,  # 8 distinct chars, repeated block
        "abcdefghijk" * 3,  # 11 distinct chars (< 12)
    ],
)
def test_create_app_fails_with_low_entropy_secret_key(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    monkeypatch.setenv("SECRET_KEY", key)
    with pytest.raises(ValidationError):
        create_app()


@pytest.mark.parametrize(
    "key",
    [
        " Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0",
        "Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0 ",
        "Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0\n",
    ],
)
def test_create_app_rejects_secret_key_with_edge_whitespace(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    monkeypatch.setenv("SECRET_KEY", key)
    with pytest.raises(ValidationError) as info:
        create_app()
    assert "Zk3!pQ9v" not in str(info.value)


def test_create_app_accepts_strong_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0")
    assert create_app().state.settings.SECRET_KEY.startswith("Zk3")
