"""Series API over a real (temporary) library: grouping, listing, detail, continue, cover, scan."""

import shutil
import uuid
from dataclasses import replace
from pathlib import Path

from app.adapters.persistence.db import create_db_engine
from sqlalchemy import text

from fakes import make_cbz, png
from library_env import ORV, add_item, logged_in, series_env, series_id_by_title

LIST_KEYS = {
    "id",
    "title",
    "kind",
    "chapter_count",
    "has_cover",
    "description",
    "description_lang",
    "metadata_state",
    "progress",
}
DETAIL_KEYS = {
    "id",
    "title",
    "kind",
    "description",
    "description_lang",
    "description_origin",
    "description_source",
    "source",
    "metadata_state",
    "chapter_count",
    "has_cover",
    "chapters",
    "continue",
}


def test_scan_groups_the_library_into_series(db_url: str, tmp_path: Path) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice = logged_in(env)
    body = alice.get("/api/v1/series").json()
    assert set(body) == {"items", "limit", "offset", "has_more"}
    assert (body["limit"], body["offset"], body["has_more"]) == (50, 0, False)
    by_title = {s["title"]: s for s in body["items"]}
    assert set(by_title) == {ORV, "Berserk", "Solo", "Folder Manga", "Mixed Series"}
    assert set(body["items"][0]) == LIST_KEYS
    # 6 numbered + "Extras"; the corrupt file is rejected by the scan, not grouped.
    assert by_title[ORV]["chapter_count"] == 7
    assert by_title["Mixed Series"]["chapter_count"] == 2  # an image folder is a chapter too
    assert by_title["Berserk"]["chapter_count"] == 1
    assert by_title["Folder Manga"]["chapter_count"] == 1
    assert all(s["has_cover"] is True for s in body["items"])
    assert all(s["metadata_state"] == "none" and s["description"] is None for s in body["items"])
    assert by_title[ORV]["progress"] == {"read_chapters": 0, "last_item_id": None}
    # natural order of the series themselves
    assert [s["title"] for s in body["items"]] == sorted(by_title, key=str.casefold)


def test_series_detail_orders_chapters_naturally_and_titles_them(
    db_url: str, tmp_path: Path
) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice = logged_in(env)
    detail = alice.get(f"/api/v1/series/{series_id_by_title(alice, ORV)}").json()
    assert set(detail) == DETAIL_KEYS
    assert detail["source"] is None and detail["continue"] is None
    chapters = detail["chapters"]
    assert [c["number"] for c in chapters] == [0.0, 1.0, 2.0, 10.0, 11.0, 100.0, None]
    assert [c["title"] for c in chapters] == [
        "Capitulo 0",
        "Capitulo 1",
        "Capitulo 2",
        "Capitulo 10",
        "Capitulo 11",
        "Capitulo 100",
        "Extras",
    ]
    assert all(
        set(c) == {"id", "type", "title", "number", "page_count", "progress"} for c in chapters
    )
    assert all(c["type"] == "manga" for c in chapters) and detail["kind"] == "manga"
    assert chapters[0]["page_count"] == 3 and chapters[0]["progress"] is None
    assert detail["chapter_count"] == 7 and detail["has_cover"] is True
    mixed = alice.get(f"/api/v1/series/{series_id_by_title(alice, 'Mixed Series')}").json()
    assert [(c["number"], c["title"]) for c in mixed["chapters"]] == [
        (7.5, "Capitulo 7.5"),
        (8.0, "Capitulo 8"),
    ]


def test_responses_never_contain_a_path_or_file_name(db_url: str, tmp_path: Path) -> None:
    env, lib = series_env(db_url, tmp_path)
    alice = logged_in(env)
    sid = series_id_by_title(alice, ORV)
    raw = alice.get("/api/v1/series").text + alice.get(f"/api/v1/series/{sid}").text
    for forbidden in (".cbz", "rel_path", "folder", "cover_path", str(lib), "series_lib", "\\\\"):
        assert forbidden not in raw
    # the standalone series title is a cleaned name, not "Berserk v03.cbz"
    assert "v03" not in raw


def test_scan_is_idempotent_and_never_duplicates_series(db_url: str, tmp_path: Path) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice = logged_in(env)
    first = {s["title"]: s["id"] for s in alice.get("/api/v1/series").json()["items"]}
    report = env.container.scan_runner.run()
    assert (report.added, report.updated) == (0, 0)
    again = {s["title"]: s["id"] for s in alice.get("/api/v1/series").json()["items"]}
    assert again == first  # same ids, same count
    engine = create_db_engine(env.settings.DATABASE_URL)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM series")).scalar_one() == len(first)
    finally:
        engine.dispose()


def test_regrouping_pass_fixes_ungrouped_items_without_duplicating_series(
    db_url: str, tmp_path: Path
) -> None:
    """Items created before the grouping existed (series_id / chapter_number NULL) are fixed by
    the next scan, even though their files did not change, and reuse the existing series."""
    env, _ = series_env(db_url, tmp_path)
    alice = logged_in(env)
    before = {s["title"]: s["id"] for s in alice.get("/api/v1/series").json()["items"]}
    engine = create_db_engine(env.settings.DATABASE_URL)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE items SET chapter_number = NULL WHERE rel_path LIKE 'Omniscient%'")
            )
            conn.execute(text("UPDATE items SET series_id = NULL WHERE rel_path LIKE 'Mixed%'"))
        listed = [s["title"] for s in alice.get("/api/v1/series").json()["items"]]
        assert "Mixed Series" not in listed  # ungrouped chapters are not listed
        status = env.container.scan_runner.run()
        assert (status.added, status.updated) == (0, 0)
        after = {s["title"]: s["id"] for s in alice.get("/api/v1/series").json()["items"]}
        assert after == before  # folder series reused, nothing duplicated
        detail = alice.get(f"/api/v1/series/{before[ORV]}").json()
        assert detail["chapters"][0]["number"] == 0.0
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM series")).scalar_one() == len(before)
        third = env.container.scan_runner.run()
        assert third.error_count == status.error_count
    finally:
        engine.dispose()


def test_series_without_active_chapters_disappears_and_comes_back(
    db_url: str, tmp_path: Path
) -> None:
    env, lib = series_env(db_url, tmp_path)
    alice = logged_in(env)
    sid = series_id_by_title(alice, "Mixed Series")
    moved = tmp_path / "parked"
    shutil.move(str(lib / "Mixed Series"), str(moved))
    env.container.scan_runner.run()
    titles = [s["title"] for s in alice.get("/api/v1/series").json()["items"]]
    assert "Mixed Series" not in titles
    assert alice.get(f"/api/v1/series/{sid}").status_code == 404
    assert alice.get(f"/api/v1/series/{sid}/cover").status_code == 404
    shutil.move(str(moved), str(lib / "Mixed Series"))
    env.container.scan_runner.run()
    assert series_id_by_title(alice, "Mixed Series") == sid  # same series, ids stay stable


def test_a_missing_chapter_leaves_the_series_but_the_rest_stays(
    db_url: str, tmp_path: Path
) -> None:
    env, lib = series_env(db_url, tmp_path)
    alice = logged_in(env)
    (lib / ORV / "Capitulo - 100.cbz").unlink()
    env.container.scan_runner.run()
    sid = series_id_by_title(alice, ORV)
    detail = alice.get(f"/api/v1/series/{sid}").json()
    assert detail["chapter_count"] == 6
    assert 100.0 not in [c["number"] for c in detail["chapters"]]


def test_new_chapter_joins_its_series_on_the_next_scan(db_url: str, tmp_path: Path) -> None:
    env, lib = series_env(db_url, tmp_path)
    alice = logged_in(env)
    (lib / ORV / "Capitulo - 101.cbz").write_bytes(make_cbz({"1.png": png(1), "2.png": png(2)}))
    env.container.scan_runner.run()
    detail = alice.get(f"/api/v1/series/{series_id_by_title(alice, ORV)}").json()
    assert detail["chapter_count"] == 8
    assert [c["number"] for c in detail["chapters"]][-2:] == [101.0, None]


def test_progress_and_continue_belong_to_the_authenticated_user(
    db_url: str, tmp_path: Path
) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice, bob = logged_in(env), logged_in(env, "bob")
    sid = series_id_by_title(alice, ORV)
    chapters = alice.get(f"/api/v1/series/{sid}").json()["chapters"]
    ch0, ch1, ch2, ch10 = (c["id"] for c in chapters[:4])

    assert alice.put(f"/api/v1/progress/{ch10}", {"locator": 1}).status_code == 200
    detail = alice.get(f"/api/v1/series/{sid}").json()
    assert detail["continue"] == {"item_id": ch10, "locator": 1}
    assert detail["chapters"][3]["progress"]["locator"] == 1
    assert detail["chapters"][3]["progress"]["finished"] is False
    assert set(detail["chapters"][3]["progress"]) == {"locator", "percent", "finished"}

    # Bob sees nothing of Alice's reading: not in the detail, not in the list.
    bob_detail = bob.get(f"/api/v1/series/{sid}").json()
    assert bob_detail["continue"] is None
    assert all(c["progress"] is None for c in bob_detail["chapters"])
    bob_row = next(s for s in bob.get("/api/v1/series").json()["items"] if s["id"] == sid)
    assert bob_row["progress"] == {"read_chapters": 0, "last_item_id": None}

    # Finish chapters 0..2 and 10: nothing unfinished left, so the next unread chapter (11).
    for item_id in (ch0, ch1, ch2, ch10):
        env.clock.advance(10)
        assert alice.put(f"/api/v1/progress/{item_id}", {"locator": 2}).status_code == 200
    detail = alice.get(f"/api/v1/series/{sid}").json()
    assert detail["continue"] == {"item_id": detail["chapters"][4]["id"], "locator": 0}
    row = next(s for s in alice.get("/api/v1/series").json()["items"] if s["id"] == sid)
    assert row["progress"] == {"read_chapters": 4, "last_item_id": ch10}
    # Bob still has nothing, and his own reading does not touch Alice's.
    assert bob.put(f"/api/v1/progress/{ch0}", {"locator": 0}).status_code == 200
    again = alice.get(f"/api/v1/series/{sid}").json()
    assert again["chapters"][0]["progress"]["finished"] is True
    bob_row = next(s for s in bob.get("/api/v1/series").json()["items"] if s["id"] == sid)
    assert bob_row["progress"] == {"read_chapters": 0, "last_item_id": ch0}


def test_continue_reading_shelf_carries_the_series(db_url: str, tmp_path: Path) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice = logged_in(env)
    sid = series_id_by_title(alice, ORV)
    ch = alice.get(f"/api/v1/series/{sid}").json()["chapters"][1]["id"]
    alice.put(f"/api/v1/progress/{ch}", {"locator": 0})
    solo = add_item(env, "Loose", pages=5)  # an ungrouped item keeps working
    alice.put(f"/api/v1/progress/{solo.id}", {"locator": 1})
    items = alice.get("/api/v1/progress/continue").json()["items"]
    by_title = {i["item"]["title"]: i for i in items}
    grouped = by_title["Capitulo - 1"]
    assert (grouped["series_id"], grouped["series_title"]) == (sid, ORV)
    assert by_title["Loose"]["series_id"] is None and by_title["Loose"]["series_title"] is None


def test_limit_is_capped_and_validated(db_url: str, tmp_path: Path) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice = logged_in(env)
    assert alice.get("/api/v1/series?limit=100000").json()["limit"] == 100
    assert alice.get("/api/v1/series?limit=2").json()["has_more"] is True
    page2 = alice.get("/api/v1/series?limit=2&offset=2").json()
    assert (page2["offset"], len(page2["items"])) == (2, 2)
    everything = [s["id"] for s in alice.get("/api/v1/series").json()["items"]]
    paged = [
        s["id"]
        for offset in (0, 2, 4)
        for s in alice.get(f"/api/v1/series?limit=2&offset={offset}").json()["items"]
    ]
    assert paged == everything  # stable order: no overlap, no gap
    for bad in ("limit=0", "limit=-1", "limit=abc", "offset=-1", "offset=99999999999"):
        assert alice.get(f"/api/v1/series?{bad}").status_code == 422, bad
    assert alice.get(f"/api/v1/series?q={'a' * 100}").status_code == 200
    assert alice.get(f"/api/v1/series?q={'a' * 101}").status_code == 422


def test_search_treats_wildcards_and_quotes_literally(db_url: str, tmp_path: Path) -> None:
    env, lib = series_env(db_url, tmp_path, scan=False)
    for name in ("100% Wolf", "a_b", "aXb", "O'Brien"):
        folder = lib / name
        folder.mkdir()
        (folder / "Cap 1.cbz").write_bytes(make_cbz({"1.png": png(1)}))
    env.container.scan_runner.run()
    alice = logged_in(env)

    def titles(q: str) -> list[str]:
        response = alice.http.get("/api/v1/series", params={"q": q})
        assert response.status_code == 200, q
        return [s["title"] for s in response.json()["items"]]

    assert titles("%") == ["100% Wolf"]
    assert titles("_") == ["a_b"]
    assert titles("a_b") == ["a_b"]
    assert titles("\\") == []  # a backslash is literal too (and matches nothing here)
    assert sorted(titles("'")) == ["O'Brien", ORV]
    assert titles("o'b") == ["O'Brien"]  # case-insensitive
    assert titles('"; DROP TABLE series; --') == []
    assert titles("\x00") == []
    assert titles("   ") == titles("")  # blank means no filter
    assert "Folder Manga" in titles("folder")
    assert alice.get("/api/v1/series?q=%25%27%22").json()["items"] == []


def test_series_cover_is_the_first_readable_chapter_and_privately_cached(
    db_url: str, tmp_path: Path
) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice = logged_in(env)
    sid = series_id_by_title(alice, ORV)
    response = alice.get(f"/api/v1/series/{sid}/cover")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == png(0)  # first page of "Capitulo - 0"
    assert response.headers["cache-control"] == "private, max-age=3600"
    assert "pragma" not in response.headers
    assert "x-internal-cache-class" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"
    revalidated = alice.http.get(
        f"/api/v1/series/{sid}/cover", headers={"If-None-Match": response.headers["etag"]}
    )
    assert revalidated.status_code == 304
    assert revalidated.headers["cache-control"] == "private, max-age=3600"


def test_series_cover_404_when_no_chapter_is_readable(db_url: str, tmp_path: Path) -> None:
    env, _ = series_env(db_url, tmp_path, scan=False)
    alice = logged_in(env)
    series = env.container.series_repository.create_standalone("Ghost")
    for name, pages in (("a", 0), ("b", 2)):  # no pages; file that does not exist on disk
        item = add_item(env, name, pages=pages, rel_path=f"ghost/{name}.cbz")
        env.container.item_repository.update(replace(item, series_id=series.id))
    response = alice.get(f"/api/v1/series/{series.id}/cover")
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"  # errors are never cacheable
    assert response.json() == {"detail": "Not found"}


def test_series_cover_skips_an_unreadable_chapter(db_url: str, tmp_path: Path) -> None:
    env, lib = series_env(db_url, tmp_path)
    alice = logged_in(env)
    sid = series_id_by_title(alice, ORV)
    (lib / ORV / "Capitulo - 0.cbz").write_bytes(b"corrupted after the scan")
    response = alice.get(f"/api/v1/series/{sid}/cover")
    assert response.status_code == 200
    assert response.content == png(1)  # falls through to "Capitulo - 1"


def test_invalid_ids_are_a_generic_404(db_url: str, tmp_path: Path) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice = logged_in(env)
    unknown = str(uuid.uuid4())
    for bad in ("not-a-uuid", unknown, unknown.upper(), "0" * 36, "%2e%2e", "1" * 37, "a" * 500):
        for suffix in ("", "/cover"):
            response = alice.get(f"/api/v1/series/{bad}{suffix}")
            assert response.status_code == 404, (bad, suffix)
            assert response.json() == {"detail": "Not found"}


def test_a_series_id_is_not_an_item_id_and_vice_versa(db_url: str, tmp_path: Path) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice = logged_in(env)
    sid = series_id_by_title(alice, ORV)
    chapter = alice.get(f"/api/v1/series/{sid}").json()["chapters"][0]["id"]
    assert alice.get(f"/api/v1/items/{sid}").status_code == 404
    assert alice.get(f"/api/v1/series/{chapter}").status_code == 404
    assert alice.get(f"/api/v1/series/{chapter}/cover").status_code == 404
