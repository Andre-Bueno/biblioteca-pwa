import os
import tempfile

# Hermetic settings, decided BEFORE any app module reads them (`app.main` builds an app on import):
# never inherit a developer's real SECRET_KEY / DATABASE_URL / LIBRARY_PATH / ... from the
# environment, and never read a real `.env` (Settings reads ".env" from the current directory).
from app.core.config import Settings

for _name in Settings.model_fields:
    os.environ.pop(_name, None)
TEST_SECRET = "test-only-secret-key-not-for-production-0123456789"
os.environ["SECRET_KEY"] = TEST_SECRET  # always ours, never one inherited from the environment

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from app.adapters.persistence.db import create_db_engine, create_session_factory  # noqa: E402
from app.adapters.persistence.migrator import upgrade  # noqa: E402
from app.adapters.security.argon2_hasher import Argon2Hasher  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

_cwd = os.getcwd()
with tempfile.TemporaryDirectory() as _empty:
    os.chdir(_empty)  # a stray `.env` in the repo must not be read by the import-time app
    try:
        from app.main import create_app  # noqa: E402
    finally:
        os.chdir(_cwd)

from auth_fakes import Env, make_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _hermetic_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Every test: no Settings variable from the real environment and an empty working directory
    (no `.env`); tests that need a variable set it with `monkeypatch.setenv`."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))


@pytest.fixture
def client(db_url: str) -> TestClient:
    return TestClient(create_app(make_settings(db_url)))


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """URL of an empty temporary SQLite file."""
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def migrated_url(db_url: str) -> str:
    upgrade(db_url)
    return db_url


@pytest.fixture
def session_factory(migrated_url: str) -> Iterator[sessionmaker[Session]]:
    engine = create_db_engine(migrated_url)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def fast_hasher() -> Argon2Hasher:
    return Argon2Hasher(time_cost=1, memory_cost_kib=8, parallelism=1)


@pytest.fixture
def env(db_url: str) -> Env:
    """Wired app on a migrated temp database with a fake clock and the user "alice"."""
    environment = Env(db_url)
    environment.create_user()
    return environment
