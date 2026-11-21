"""REG-002: migrations folder not found once the package is installed.

Bug: `migrator.py` located `migrations/` with `Path(__file__).parents[3]`, which points into
site-packages after `pip install .`, so `python -m app.cli migrate` failed in the container.
Cause: the location was inferred from the module path. Now MIGRATIONS_DIR (env/Settings) is
honored, the Dockerfile sets it, and a missing folder is a clear error.
"""

import shutil
from pathlib import Path

import pytest
from app.adapters.persistence import migrator
from app.adapters.persistence.migrator import MigrationsNotFoundError
from sqlalchemy import create_engine, inspect

REPO = Path(migrator.__file__).resolve().parents[3]


def test_migrations_run_from_a_directory_unrelated_to_the_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "app-root" / "migrations"
    shutil.copytree(REPO / "migrations", elsewhere, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setenv("MIGRATIONS_DIR", str(elsewhere))
    url = f"sqlite:///{(tmp_path / 'x.db').as_posix()}"
    migrator.upgrade(url)
    engine = create_engine(url)
    try:
        assert "items" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_missing_directory_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIGRATIONS_DIR", str(tmp_path / "nope"))
    with pytest.raises(MigrationsNotFoundError, match="MIGRATIONS_DIR"):
        migrator.upgrade(f"sqlite:///{(tmp_path / 'x.db').as_posix()}")
