"""`kind` of a series and `type` of each chapter in GET /series and GET /series/{id}."""

from pathlib import Path

from app.domain.series import series_kind

from epub_fixtures import make_epub
from fakes import make_cbz, png
from library_env import book_env, logged_in, series_id_by_title


def library() -> dict[str, bytes]:
    return {
        "Shelf/One.epub": make_epub(title="Book One"),
        "Shelf/Two.epub": make_epub(title="Book Two"),
        "Mixed/Cap 1.cbz": make_cbz({"1.png": png(1), "2.png": png(2)}),
        "Mixed/Companion.epub": make_epub(title="Companion"),
        "Comic/Cap 1.cbz": make_cbz({"1.png": png(3), "2.png": png(4)}),
        "Loose Book.epub": make_epub(title="Loose"),
    }


def test_series_kind_rule() -> None:
    assert series_kind(["manga", "manga"]) == "manga"
    assert series_kind(["book"]) == "book"
    assert series_kind(["book", "manga"]) == "mixed"
    assert series_kind(["pdf"]) == "mixed" and series_kind([]) == "mixed"
    assert series_kind(iter(["book", "book"])) == "book"


def test_list_and_detail_carry_kind_and_chapters_carry_type(db_url: str, tmp_path: Path) -> None:
    env, _ = book_env(db_url, tmp_path, library())
    alice = logged_in(env)
    listing = alice.get("/api/v1/series?limit=100").json()["items"]
    kinds = {s["title"]: s["kind"] for s in listing}
    assert kinds["Shelf"] == "book" and kinds["Mixed"] == "mixed" and kinds["Comic"] == "manga"
    assert [k for t, k in kinds.items() if t not in ("Shelf", "Mixed", "Comic")] == ["book"]
    for title, kind in (("Shelf", "book"), ("Mixed", "mixed"), ("Comic", "manga")):
        detail = alice.get(f"/api/v1/series/{series_id_by_title(alice, title)}").json()
        assert detail["kind"] == kind
        assert all(
            set(c) == {"id", "type", "title", "number", "page_count", "progress"}
            for c in detail["chapters"]
        )
    mixed = alice.get(f"/api/v1/series/{series_id_by_title(alice, 'Mixed')}").json()
    assert sorted(c["type"] for c in mixed["chapters"]) == ["book", "manga"]
    shelf = alice.get(f"/api/v1/series/{series_id_by_title(alice, 'Shelf')}").json()
    assert {c["type"] for c in shelf["chapters"]} == {"book"}
    # for a book `page_count` is its number of chapters, and the title is the OPF title
    assert {c["title"] for c in shelf["chapters"]} == {"Book One", "Book Two"}
    assert all(c["page_count"] == 3 for c in shelf["chapters"])


def test_kind_values_are_a_closed_set(db_url: str, tmp_path: Path) -> None:
    env, _ = book_env(db_url, tmp_path, library())
    alice = logged_in(env)
    for item in alice.get("/api/v1/series?limit=100").json()["items"]:
        assert item["kind"] in {"manga", "book", "mixed"}
