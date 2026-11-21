"""series description attribution: description_origin, description_source_name/url

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-20

- `description_origin`: 'source' (written by the source), 'translated' (automatic translation of the
  source's English text) or 'manual' (typed by the admin); NULL = no description / unknown.
  A CHECK keeps it a closed set. `description_source_name` / `description_source_url` say whose
  text it is (for a translation: the source of the ORIGINAL English text); the URL is https.
- Plain `ALTER TABLE ADD COLUMN` (no table rebuild, so reading progress is never touched).
- Backfill of descriptions written by the previous release: from a source -> 'source' with that
  source's name and page; typed by hand (no source) -> 'manual'. Idempotent (NULL origin only).
- Downgrade drops the three columns (SQLite >= 3.35); everything else is untouched.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE series ADD COLUMN description_origin VARCHAR(16) "
        "CONSTRAINT ck_series_description_origin "
        "CHECK (description_origin IN ('source', 'translated', 'manual'))"
    )
    op.execute("ALTER TABLE series ADD COLUMN description_source_name VARCHAR(64)")
    op.execute("ALTER TABLE series ADD COLUMN description_source_url VARCHAR(512)")
    op.execute(
        "UPDATE series SET description_origin = 'source', "
        "description_source_name = CASE metadata_source WHEN 'mangadex' THEN 'MangaDex' "
        "WHEN 'anilist' THEN 'AniList' ELSE metadata_source END, "
        "description_source_url = source_url "
        "WHERE description IS NOT NULL AND metadata_source IS NOT NULL "
        "AND description_origin IS NULL"
    )
    op.execute(
        "UPDATE series SET description_origin = 'manual' "
        "WHERE description IS NOT NULL AND description_origin IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE series DROP COLUMN description_source_url")
    op.execute("ALTER TABLE series DROP COLUMN description_source_name")
    op.execute("ALTER TABLE series DROP COLUMN description_origin")
