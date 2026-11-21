"""items (library catalog)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "items",
        # Opaque UUID (text): the only identifier the client ever sees.
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        # Library-relative POSIX path. Server-side only: never returned by the API.
        sa.Column("rel_path", sa.String(1024), nullable=False, unique=True),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("missing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("type IN ('manga', 'book', 'pdf')", name="ck_items_type"),
        sa.CheckConstraint("page_count >= 0", name="ck_items_page_count"),
    )
    op.create_index("ix_items_type", "items", ["type"])
    op.create_index("ix_items_title", "items", ["title"])
    op.create_index("ix_items_added_at", "items", ["added_at"])
    op.create_index("ix_items_missing", "items", ["missing"])


def downgrade() -> None:
    op.drop_table("items")
