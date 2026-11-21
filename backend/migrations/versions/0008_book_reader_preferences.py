"""users.book_font_scale and users.book_theme (EPUB reader preferences)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-21

- `book_font_scale`: percent 80..200, default 100. `book_theme`: 'auto' | 'light' | 'dark' |
  'sepia', default 'auto'. Both NOT NULL with a default and a column CHECK, so existing users get
  the defaults and nothing can store a value the reader would refuse.
- Plain `ALTER TABLE ADD COLUMN` (no table rebuild): a batch rebuild would DROP `users` and, with
  foreign keys on, cascade-delete sessions and reading progress (see 0004).
Fully reversible; downgrade drops the two columns (SQLite >= 3.35); everything else is untouched.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN book_font_scale INTEGER NOT NULL DEFAULT 100 "
        "CONSTRAINT ck_users_book_font_scale CHECK (book_font_scale BETWEEN 80 AND 200)"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN book_theme VARCHAR(8) NOT NULL DEFAULT 'auto' "
        "CONSTRAINT ck_users_book_theme "
        "CHECK (book_theme IN ('auto', 'light', 'dark', 'sepia'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN book_theme")
    op.execute("ALTER TABLE users DROP COLUMN book_font_scale")
