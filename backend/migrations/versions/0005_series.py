"""series table, items.series_id and items.chapter_number (with backfill)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-20

- `series`: groups chapters. `folder_rel_path` (library-relative, server-side only) is unique and
  NULL for a standalone series (a loose file in the library root).
- `items.series_id` (FK, ON DELETE SET NULL, indexed) and `items.chapter_number` are added with a
  plain `ALTER TABLE ADD COLUMN`: a table rebuild would DROP `items` and, with foreign keys on,
  cascade-delete every `reading_progress` row.
- Backfill: one series per distinct parent folder of `items.rel_path`, one standalone series per
  root item. Idempotent (only items without a series). Titles here are a plain version of the
  domain rule; the library scan later fills `chapter_number` and keeps everything in sync.
- Downgrade drops the index and the two columns (SQLite >= 3.35) and then the table; items and
  reading progress are untouched.
"""

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PAD = 12


def _sort_title(title: str) -> str:
    parts = re.split(rf"([0-9]{{1,{_PAD}}})", title.casefold())
    return "".join(p.zfill(_PAD) if i % 2 == 1 else p for i, p in enumerate(parts))[:255]


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip()[:200] or "Untitled"


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("sort_title", sa.String(255), nullable=False),
        sa.Column("folder_rel_path", sa.String(1024), nullable=True, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("description_lang", sa.String(16), nullable=True),
        sa.Column("metadata_source", sa.String(32), nullable=True),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("metadata_state", sa.String(16), nullable=False, server_default="none"),
        sa.Column("cover_path", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "metadata_state IN ('none', 'matched', 'manual', 'not_found')",
            name="ck_series_metadata_state",
        ),
    )
    op.create_index("ix_series_sort_title", "series", ["sort_title", "id"])
    op.execute(
        "ALTER TABLE items ADD COLUMN series_id VARCHAR(36) "
        "REFERENCES series(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE items ADD COLUMN chapter_number FLOAT")
    op.create_index("ix_items_series_id", "items", ["series_id"])
    _backfill()


def _backfill() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = conn.execute(
        sa.text("SELECT id, rel_path, title FROM items WHERE series_id IS NULL")
    ).all()
    by_folder: dict[str, str] = {}
    insert_series = sa.text(
        "INSERT INTO series (id, title, sort_title, folder_rel_path, metadata_state, created_at,"
        " updated_at) VALUES (:id, :title, :sort, :folder, 'none', :now, :now)"
    )
    link = sa.text("UPDATE items SET series_id = :sid WHERE id = :iid")
    for item_id, rel_path, item_title in rows:
        folder = rel_path.rstrip("/").rpartition("/")[0]
        if folder:
            sid = by_folder.get(folder)
            if sid is None:
                sid = str(uuid.uuid4())
                title = _clean(folder.rpartition("/")[2])
                params = {"id": sid, "title": title, "sort": _sort_title(title), "folder": folder}
                conn.execute(insert_series, params | {"now": now})
                by_folder[folder] = sid
        else:
            sid = str(uuid.uuid4())
            title = _clean(item_title)
            params = {"id": sid, "title": title, "sort": _sort_title(title), "folder": None}
            conn.execute(insert_series, params | {"now": now})
        conn.execute(link, {"sid": sid, "iid": item_id})


def downgrade() -> None:
    op.drop_index("ix_items_series_id", table_name="items")
    op.execute("ALTER TABLE items DROP COLUMN series_id")
    op.execute("ALTER TABLE items DROP COLUMN chapter_number")
    op.drop_index("ix_series_sort_title", table_name="series")
    op.drop_table("series")
