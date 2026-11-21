"""Runs Alembic migrations programmatically (no alembic.ini; URL is passed in).

Where the `migrations/` directory lives is NOT inferred from this file's location once the package
is installed (`pip install .` puts `app/` in site-packages, far from the repo). Resolution order:
an explicit argument, the `MIGRATIONS_DIR` environment variable, then the repo layout (development
checkout: `backend/migrations`). A directory without `env.py` is rejected with a clear error.
"""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR_ENV = "MIGRATIONS_DIR"
# app/adapters/persistence/migrator.py -> backend/ (development checkout only)
_DEV_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


class MigrationsNotFoundError(RuntimeError):
    """The migrations directory is missing or is not an Alembic environment."""


def resolve_migrations_dir(explicit: str | os.PathLike[str] | None = None) -> Path:
    if explicit:
        chosen = Path(explicit)
    elif os.environ.get(MIGRATIONS_DIR_ENV):
        chosen = Path(os.environ[MIGRATIONS_DIR_ENV])
    else:
        chosen = _DEV_MIGRATIONS_DIR
    if not (chosen / "env.py").is_file():
        raise MigrationsNotFoundError(
            f"migrations directory not found; set {MIGRATIONS_DIR_ENV} to the folder "
            "that contains env.py"
        )
    return chosen.resolve()


def _config(url: str, migrations_dir: str | os.PathLike[str] | None) -> Config:
    cfg = Config()
    location = str(resolve_migrations_dir(migrations_dir)).replace("%", "%%")
    cfg.set_main_option("script_location", location)
    cfg.attributes["url"] = url
    return cfg


def upgrade(
    url: str, revision: str = "head", *, migrations_dir: str | os.PathLike[str] | None = None
) -> None:
    command.upgrade(_config(url, migrations_dir), revision)


def downgrade(
    url: str, revision: str = "base", *, migrations_dir: str | os.PathLike[str] | None = None
) -> None:
    command.downgrade(_config(url, migrations_dir), revision)
