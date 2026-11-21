"""test_reg_026: metadata enrichment does not depend on the file format of the series.

History: this REG first made series made only of books (EPUB) skip external sources. On 2026-11-21
the owner EXPRESSLY decided that cover and description lookup (ADR 0015) applies to every format
alike (EPUB, CBZ, CBR, folder, PDF), so the skip was removed and this test now asserts the opposite:
a series of EPUB is looked up, gets cover and description, exactly like a series of CBZ. The
numbering is kept; the former name (`..._skips_series_of_books`) would be misleading.
"""

from pathlib import Path

from epub_fixtures import make_epub
from library_env import book_env, logged_in, series_id_by_title
from metadata_fakes import (
    MD_COVER_URL,
    FakeGateway,
    good_jpeg,
    mangadex_entry,
    mangadex_list,
)


def test_reg_026_series_of_epub_is_looked_up_and_gets_cover_and_description(
    db_url: str, tmp_path: Path
) -> None:
    gateway = FakeGateway()
    gateway.route(
        "api.mangadex.org",
        mangadex_list(
            mangadex_entry(title={"en": "Shelf"}, description={"pt-br": "Uma estante de livros."})
        ),
    )
    gateway.route('"search"', {"data": {"Page": {"media": []}}})
    gateway.images[MD_COVER_URL] = good_jpeg(5)
    env, _ = book_env(db_url, tmp_path, {"Shelf/A.epub": make_epub(title="Shelf")}, gateway=gateway)
    env.container.enrich_runner.run()
    assert gateway.calls != []
    alice = logged_in(env)
    series = series_id_by_title(alice, "Shelf")
    detail = alice.get(f"/api/v1/series/{series}").json()
    assert detail["metadata_state"] == "matched"
    assert detail["description"] == "Uma estante de livros."
    assert env.container.series_repository.get(series).cover_path is not None  # type: ignore[union-attr]
