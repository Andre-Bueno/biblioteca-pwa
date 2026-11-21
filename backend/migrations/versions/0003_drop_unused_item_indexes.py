"""drop item indexes that no query can use

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19

Data is untouched (only index structures change) and the migration is fully reversible.

- `ix_items_title`: listing orders by `lower(title)` and search uses `LIKE '%needle%'`; neither can
  use a plain index on `title`, so it only slowed down writes during scans.
- `ix_items_missing`: a boolean with almost every row `false` has no selectivity worth an index.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_items_title", table_name="items")
    op.drop_index("ix_items_missing", table_name="items")


def downgrade() -> None:
    op.create_index("ix_items_title", "items", ["title"])
    op.create_index("ix_items_missing", "items", ["missing"])
