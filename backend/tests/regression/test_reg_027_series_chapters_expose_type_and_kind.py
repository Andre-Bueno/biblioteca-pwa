"""test_reg_027: series chapters carry `type`, and series carry `kind`.

Bug: `GET /series/{id}` chapters had no `type`, so the frontend could not tell a book (whose
`page_count` is its number of chapters) from a manga and would have shown "1 pagina" for a book.
Cause: `ChapterOut` was built before books existed.
"""

from pathlib import Path

from epub_fixtures import make_epub
from library_env import book_env, logged_in, series_id_by_title


def test_reg_027_a_book_chapter_says_it_is_a_book(db_url: str, tmp_path: Path) -> None:
    env, _ = book_env(db_url, tmp_path, {"Shelf/Only.epub": make_epub(title="Only")})
    alice = logged_in(env)
    detail = alice.get(f"/api/v1/series/{series_id_by_title(alice, 'Shelf')}").json()
    assert detail["kind"] == "book"
    assert [(c["type"], c["page_count"]) for c in detail["chapters"]] == [("book", 3)]
    listed = alice.get("/api/v1/series").json()["items"]
    assert [s["kind"] for s in listed] == ["book"]
