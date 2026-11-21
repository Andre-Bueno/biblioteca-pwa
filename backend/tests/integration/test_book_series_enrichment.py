"""Series made only of books are never sent to external metadata sources (no network at all)."""

from pathlib import Path

from epub_fixtures import make_epub
from fakes import make_cbz, png
from library_env import book_env, logged_in, series_id_by_title
from metadata_fakes import FakeGateway, mangadex_entry, mangadex_list


def _library() -> dict[str, bytes]:
    return {
        "Only Books/One.epub": make_epub(title="Book One"),
        "Only Books/Two.epub": make_epub(title="Book Two"),
        "Solo Book.epub": make_epub(title="Loose Title"),
        "Mixed/Cap 1.cbz": make_cbz({"1.png": png(1), "2.png": png(2)}),
        "Mixed/Companion.epub": make_epub(title="Companion"),
    }


def _gateway() -> FakeGateway:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org", mangadex_list(mangadex_entry(title={"en": "Mixed"})))
    gateway.route('"search"', {"data": {"Page": {"media": []}}})
    return gateway


def test_enrichment_skips_series_of_books_and_never_calls_the_network(
    db_url: str, tmp_path: Path
) -> None:
    gateway = _gateway()
    env, _ = book_env(db_url, tmp_path, _library(), gateway=gateway)
    status = env.container.enrich_runner.run()
    assert status.state.value == "finished"
    queried = " ".join(url for _kind, url in gateway.calls)
    for title in ("Only", "Book", "Loose", "Solo", "Companion"):
        assert title not in queried, title  # no title of a book left the server
    assert "Mixed" in queried  # a series with a manga chapter is still looked up
    alice = logged_in(env)
    for title in ("Only Books", "Solo Book"):
        detail = alice.get(f"/api/v1/series/{series_id_by_title(alice, title)}").json()
        assert detail["metadata_state"] == "none"
        assert detail["description"] is None


def test_enrichment_of_one_series_of_books_is_skipped_too(db_url: str, tmp_path: Path) -> None:
    gateway = _gateway()
    env, _ = book_env(db_url, tmp_path, _library(), gateway=gateway)
    alice = logged_in(env)
    series_id = series_id_by_title(alice, "Only Books")
    report = env.container.metadata_service.enrich_all(force=True, series_id=series_id)
    assert (report.matched, report.not_found, report.skipped) == (0, 0, 1)
    assert gateway.calls == []
    state = alice.get(f"/api/v1/series/{series_id}").json()["metadata_state"]
    assert state == "none"


def test_the_series_repository_never_lists_a_series_of_books(db_url: str, tmp_path: Path) -> None:
    env, _ = book_env(db_url, tmp_path, _library())
    titles = {
        s.title for s in env.container.series_repository.list_for_enrichment(("none",), None, 100)
    }
    assert titles == {"Mixed"}
