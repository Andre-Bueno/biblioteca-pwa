"""reading_progress table and users.reading_direction

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-19

- `reading_progress`: one row per (user, item); deleting the user or the item removes it (CASCADE).
- `users.reading_direction`: new preference next to `theme_pref`. Added with a plain `ALTER TABLE
  ADD COLUMN` (NOT NULL + default + column CHECK) so existing users stay untouched: a batch table
  rebuild would DROP `users` and, with foreign keys on, cascade-delete the sessions.
Fully reversible; downgrade drops the table and the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN reading_direction VARCHAR(16) NOT NULL DEFAULT 'rtl' "
        "CONSTRAINT ck_users_reading_direction "
        "CHECK (reading_direction IN ('rtl', 'ltr', 'vertical'))"
    )
    op.create_table(
        "reading_progress",
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "item_id", sa.String(36), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("locator", sa.Integer(), nullable=False),
        sa.Column("percent", sa.Float(), nullable=False),
        sa.Column("finished", sa.Boolean(), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "item_id"),
        sa.CheckConstraint("locator >= 0", name="ck_reading_progress_locator"),
        sa.CheckConstraint("percent >= 0 AND percent <= 100", name="ck_reading_progress_percent"),
    )
    op.create_index(
        "ix_reading_progress_user_updated",
        "reading_progress",
        ["user_id", sa.text("updated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_reading_progress_user_updated", table_name="reading_progress")
    op.drop_table("reading_progress")
    op.execute("ALTER TABLE users DROP COLUMN reading_direction")
