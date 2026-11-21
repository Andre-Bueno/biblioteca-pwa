"""Alembic environment. The URL is injected via `config.attributes["url"]`."""

from alembic import context
from app.adapters.persistence.db import create_db_engine

config = context.config
url = config.attributes.get("url")
if not isinstance(url, str):
    raise RuntimeError("database url not provided; run migrations via `python -m app.cli migrate`")

engine = create_db_engine(url)
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
