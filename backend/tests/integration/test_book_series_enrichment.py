"""Series of books (EPUB) are enriched exactly like series of any other format.

Owner decision of 2026-11-21 (ADR 0015 extended): cover and description lookup applies to EPUB, CBZ,
CBR, folder and PDF alike. There is no rule by format anywhere: not in the automatic run, not in
the single-series run, not in the repository query, not in the admin's manual search/selection.
"""

from pathlib import Path

from epub_fixtures import make_epub
from fakes import make_cbz, png
from library_env import ADMIN, book_env, logged_in, series_id_by_title
from metadata_fakes import (
    MD_COVER_URL,
    MD_ID,
    FakeGateway,
    good_jpeg,
    mangadex_entry,
    mangadex_list,
)


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
    entry = mangadex_entry(title={"en": "Only Books"}, description={"pt-br": "Texto."})
    gateway.route(f"/manga/{MD_ID}", {"result": "ok", "data": entry})  # by id (manual selection)
    gateway.route("api.mangadex.org", mangadex_list(entry))
    gateway.route('"search"', {"data": {"Page": {"media": []}}})
    gateway.images[MD_COVER_URL] = good_jpeg(3)
    return gateway


def test_automatic_run_looks_up_series_of_books_like_any_other(db_url: str, tmp_path: Path) -> None:
    gateway = _gateway()
    env, _ = book_env(db_url, tmp_path, _library(), gateway=gateway)
    status = env.container.enrich_runner.run()
    assert status.state.value == "finished"
    queried = " ".join(url for _kind, url in gateway.calls)
    for title in ("Only", "Solo", "Mixed"):
        assert title in queried, title  # every series, books included, was looked up
    alice = logged_in(env)
    detail = alice.get(f"/api/v1/series/{series_id_by_title(alice, 'Only Books')}").json()
    assert detail["metadata_state"] == "matched"
    assert detail["description"] == "Texto."


def test_enrichment_of_one_series_of_books_is_done_too(db_url: str, tmp_path: Path) -> None:
    gateway = _gateway()
    env, _ = book_env(db_url, tmp_path, _library(), gateway=gateway)
    alice = logged_in(env)
    series_id = series_id_by_title(alice, "Only Books")
    report = env.container.metadata_service.enrich_all(force=True, series_id=series_id)
    assert (report.matched, report.not_found, report.skipped) == (1, 0, 0)
    assert gateway.calls != []
    state = alice.get(f"/api/v1/series/{series_id}").json()["metadata_state"]
    assert state == "matched"


def test_the_series_repository_lists_every_series_regardless_of_format(
    db_url: str, tmp_path: Path
) -> None:
    env, _ = book_env(db_url, tmp_path, _library())
    titles = {
        s.title for s in env.container.series_repository.list_for_enrichment(("none",), None, 100)
    }
    assert titles == {"Only Books", "Solo Book", "Mixed"}


def test_admin_search_and_selection_work_for_a_series_of_books(db_url: str, tmp_path: Path) -> None:
    gateway = _gateway()
    env, _ = book_env(db_url, tmp_path, _library(), gateway=gateway)
    admin = logged_in(env, ADMIN)
    sid = series_id_by_title(admin, "Only Books")
    found = admin.get(f"/api/v1/series/{sid}/metadata/candidates")
    assert found.status_code == 200 and found.json()
    selected = admin.post(
        f"/api/v1/series/{sid}/metadata/select", {"provider": "mangadex", "external_id": MD_ID}
    )
    assert selected.status_code == 200
    assert selected.json()["metadata_state"] == "manual"


def _lib_for(fmt: str) -> dict[str, bytes]:
    if fmt == "cbz":
        return {"Parity/Cap 1.cbz": make_cbz({"1.png": png(1), "2.png": png(2)})}
    if fmt == "epub":
        return {"Parity/Cap 1.epub": make_epub(title="Cap 1")}
    return {"Parity/Cap 1/1.png": png(1), "Parity/Cap 1/2.png": png(2)}  # folder of images


def _outcome(db_url: str, tmp_path: Path, fmt: str) -> tuple[object, object]:
    gateway = FakeGateway()
    gateway.route(
        "api.mangadex.org",
        mangadex_list(mangadex_entry(title={"en": "Parity"}, description={"pt-br": "Igual."})),
    )
    gateway.route('"search"', {"data": {"Page": {"media": []}}})
    gateway.images[MD_COVER_URL] = good_jpeg(9)
    root = tmp_path / fmt
    root.mkdir()
    own_db = db_url.replace("test.db", f"{fmt}.db")  # one database per run
    assert own_db != db_url
    env, _ = book_env(own_db, root, _lib_for(fmt), gateway=gateway)
    env.container.enrich_runner.run()
    alice = logged_in(env)
    sid = series_id_by_title(alice, "Parity")
    detail = alice.get(f"/api/v1/series/{sid}").json()
    seen = {
        k: detail[k]
        for k in (
            "metadata_state",
            "description",
            "description_lang",
            "description_origin",
            "source",
        )
    }
    seen["cover_downloaded"] = env.container.series_repository.get(sid).cover_path is not None  # type: ignore[union-attr]
    return gateway.calls, seen


def test_parity_same_calls_and_result_for_cbz_epub_and_folder(db_url: str, tmp_path: Path) -> None:
    results = {fmt: _outcome(db_url, tmp_path, fmt) for fmt in ("cbz", "epub", "folder")}
    reference = results["cbz"]
    assert reference[0] != []  # the reference run did call the (fake) gateway
    assert reference[1]["metadata_state"] == "matched"  # type: ignore[index]
    assert reference[1]["cover_downloaded"] is True  # type: ignore[index]
    for fmt, outcome in results.items():
        assert outcome == reference, fmt
