"""series metadata fields: source_url, metadata_checked_at, title_original

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-20

- Three nullable columns on `series`, added with a plain `ALTER TABLE ADD COLUMN` (no table
  rebuild: `items.series_id` has a foreign key to `series` and `reading_progress` depends on
  `items`, so a rebuild could cascade-delete reading progress).
- The CHECK on `metadata_state` already exists since 0005 (`none`, `matched`, `manual`,
  `not_found`); nothing to change there.
- No remote cover URL is stored: the cover is downloaded once to the data dir and `cover_path`
  (0005) keeps only its relative name.
- Downgrade drops the three columns (SQLite >= 3.35); every other column and row is untouched.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE series ADD COLUMN source_url VARCHAR(512)")
    op.execute("ALTER TABLE series ADD COLUMN metadata_checked_at DATETIME")
    op.execute("ALTER TABLE series ADD COLUMN title_original VARCHAR(255)")


def downgrade() -> None:
    op.execute("ALTER TABLE series DROP COLUMN title_original")
    op.execute("ALTER TABLE series DROP COLUMN metadata_checked_at")
    op.execute("ALTER TABLE series DROP COLUMN source_url")
