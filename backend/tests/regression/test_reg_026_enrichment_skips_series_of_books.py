"""test_reg_026: series made only of books are never sent to external metadata sources.

Bug risk (EPUB support): book titles are the user's own library and the public sources (MangaDex,
AniList...) know manga; the enrichment would have sent every book series title out (ADR 0015 covers
manga/series titles only) and could attach a wrong cover/description. Cause: `list_for_enrichment`
and `enrich_all(series_id=...)` looked only at "has an active item", not at its type.
"""

from pathlib import Path

from epub_fixtures import make_epub
from library_env import book_env, logged_in, series_id_by_title
from metadata_fakes import FakeGateway, mangadex_entry, mangadex_list


def test_reg_026_no_network_call_and_state_stays_none(db_url: str, tmp_path: Path) -> None:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org", mangadex_list(mangadex_entry(title={"en": "Shelf"})))
    env, _ = book_env(db_url, tmp_path, {"Shelf/A.epub": make_epub(title="Shelf")}, gateway=gateway)
    env.container.enrich_runner.run()
    assert gateway.calls == []
    alice = logged_in(env)
    series = series_id_by_title(alice, "Shelf")
    assert alice.get(f"/api/v1/series/{series}").json()["metadata_state"] == "none"
    report = env.container.metadata_service.enrich_all(force=True, series_id=series)
    assert report.skipped == 1 and gateway.calls == []
