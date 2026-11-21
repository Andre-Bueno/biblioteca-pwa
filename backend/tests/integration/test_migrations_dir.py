"""The migrations folder is found without relying on where the package is installed."""

import shutil
from pathlib import Path

import pytest
from app.adapters.persistence import migrator
from app.adapters.persistence.migrator import MigrationsNotFoundError, resolve_migrations_dir
from sqlalchemy import create_engine, inspect

REPO_MIGRATIONS = Path(migrator.__file__).resolve().parents[3] / "migrations"


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_env_variable_wins_over_the_repo_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_url: str
) -> None:
    copy = tmp_path / "installed" / "migrations"
    shutil.copytree(REPO_MIGRATIONS, copy, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setenv("MIGRATIONS_DIR", str(copy))
    assert resolve_migrations_dir() == copy.resolve()
    migrator.upgrade(db_url)  # runs from the copy, as it would from /app/migrations
    assert {"users", "items"} <= _tables(db_url)


def test_explicit_argument_wins_over_the_env_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIGRATIONS_DIR", str(tmp_path / "does-not-exist"))
    assert resolve_migrations_dir(REPO_MIGRATIONS) == REPO_MIGRATIONS.resolve()


def test_default_is_the_repo_checkout_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIGRATIONS_DIR", raising=False)
    assert resolve_migrations_dir() == REPO_MIGRATIONS.resolve()


@pytest.mark.parametrize("make_dir", [False, True])
def test_missing_or_invalid_directory_gives_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_url: str, make_dir: bool
) -> None:
    bogus = tmp_path / "nothing-here"
    if make_dir:
        bogus.mkdir()  # exists, but is not an Alembic environment (no env.py)
    monkeypatch.setenv("MIGRATIONS_DIR", str(bogus))
    with pytest.raises(MigrationsNotFoundError, match="MIGRATIONS_DIR") as info:
        migrator.upgrade(db_url)
    assert str(bogus) not in str(info.value)
    with pytest.raises(MigrationsNotFoundError):
        migrator.downgrade(db_url)


def test_dockerfile_sets_migrations_dir() -> None:
    dockerfile = (REPO_MIGRATIONS.parents[1] / "infra" / "Dockerfile").read_text(encoding="utf-8")
    assert "MIGRATIONS_DIR=/app/migrations" in dockerfile
