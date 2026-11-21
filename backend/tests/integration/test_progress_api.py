"""Progress and preferences over the real API and a temporary database."""

from dataclasses import replace
from pathlib import Path

import pytest
from app.domain.item import Item

from auth_fakes import Env
from library_env import add_item, library_env, logged_in

MISSING_ID = "00000000-0000-4000-8000-000000000000"


def _setup(db_url: str, tmp_path: Path) -> tuple[Env, Item]:
    env, _ = library_env(db_url, tmp_path, scan=False)
    return env, add_item(env, "One", pages=10)


def test_put_computes_percent_and_finished_on_the_server(db_url: str, tmp_path: Path) -> None:
    env, item = _setup(db_url, tmp_path)
    alice = logged_in(env)
    body = alice.put(f"/api/v1/progress/{item.id}", {"locator": 4, "device_id": "phone-1"}).json()
    assert body["item_id"] == item.id and body["locator"] == 4
    assert body["percent"] == 50.0 and body["finished"] is False
    assert body["updated_at"].startswith("2026-11-19T12:00:00")  # the fake server clock
    last = alice.put(f"/api/v1/progress/{item.id}", {"locator": 9}).json()
    assert last["percent"] == 100.0 and last["finished"] is True
    assert alice.get(f"/api/v1/progress/{item.id}").json() == last


@pytest.mark.parametrize("extra", [{"percent": 1}, {"finished": True}, {"user_id": "x"}])
def test_client_cannot_send_percent_or_finished(db_url: str, tmp_path: Path, extra: dict) -> None:  # type: ignore[type-arg]
    env, item = _setup(db_url, tmp_path)
    alice = logged_in(env)
    response = alice.put(f"/api/v1/progress/{item.id}", {"locator": 0} | extra)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    assert alice.get(f"/api/v1/progress/{item.id}").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"locator": -1},
        {"locator": 10},  # == page_count
        {"locator": 10_000},
        {"locator": 2**40},
        {"locator": 1.5},
        {"locator": "3"},
        {"locator": True},
        {"locator": None},
        {},
        {"locator": 0, "device_id": ""},
        {"locator": 0, "device_id": "a" * 65},
        {"locator": 0, "device_id": "bad id!"},
        {"locator": 0, "device_id": "x\n"},
        {"locator": 0, "device_id": 7},
        [],
        "locator",
    ],
)
def test_invalid_bodies_are_a_generic_422(db_url: str, tmp_path: Path, body: object) -> None:
    env, item = _setup(db_url, tmp_path)
    alice = logged_in(env)
    response = alice.put(f"/api/v1/progress/{item.id}", body)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    assert alice.get(f"/api/v1/progress/{item.id}").status_code == 404


def test_unknown_and_missing_items_are_a_generic_404(db_url: str, tmp_path: Path) -> None:
    env, item = _setup(db_url, tmp_path)
    alice = logged_in(env)
    assert alice.put(f"/api/v1/progress/{MISSING_ID}", {"locator": 0}).status_code == 404
    env.container.item_repository.remove_missing(set())  # every item becomes `missing`
    response = alice.put(f"/api/v1/progress/{item.id}", {"locator": 0})
    assert response.status_code == 404 and response.json() == {"detail": "Not found"}


def test_device_id_is_accepted_and_optional(db_url: str, tmp_path: Path) -> None:
    env, item = _setup(db_url, tmp_path)
    alice = logged_in(env)
    url = f"/api/v1/progress/{item.id}"
    assert alice.put(url, {"locator": 0, "device_id": "A_b-9" + "z" * 59}).status_code == 200
    assert alice.put(url, {"locator": 1, "device_id": None}).status_code == 200


def test_last_write_wins_and_keeps_one_row(db_url: str, tmp_path: Path) -> None:
    env, item = _setup(db_url, tmp_path)
    alice = logged_in(env)
    url = f"/api/v1/progress/{item.id}"
    alice.put(url, {"locator": 7})
    env.clock.advance(1)
    alice.put(url, {"locator": 2})  # going back is a legitimate write: the last one wins
    assert alice.get(url).json()["locator"] == 2
    assert alice.get("/api/v1/progress/continue").json()["items"][0]["locator"] == 2


def test_delete_is_idempotent(db_url: str, tmp_path: Path) -> None:
    env, item = _setup(db_url, tmp_path)
    alice = logged_in(env)
    url = f"/api/v1/progress/{item.id}"
    assert alice.delete(url).status_code == 204  # nothing to delete yet
    alice.put(url, {"locator": 1})
    assert alice.delete(url).status_code == 204
    assert alice.delete(url).status_code == 204
    assert alice.get(url).status_code == 404


def test_continue_orders_by_recency_and_excludes_finished_and_missing(
    db_url: str, tmp_path: Path
) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    a, b, c, done, gone = (add_item(env, n, pages=10) for n in ("A", "B", "C", "Done", "Gone"))
    alice = logged_in(env)
    for item, locator in ((a, 1), (b, 2), (done, 9), (gone, 3), (c, 4)):
        alice.put(f"/api/v1/progress/{item.id}", {"locator": locator})
        env.clock.advance(10)
    alice.put(f"/api/v1/progress/{a.id}", {"locator": 5})  # A becomes the most recent
    env.container.item_repository.update(replace(gone, missing=True))
    items = alice.get("/api/v1/progress/continue").json()["items"]
    assert [i["item"]["title"] for i in items] == ["A", "C", "B"]
    assert items[0]["locator"] == 5 and items[0]["finished"] is False
    assert set(items[0]) == {
        "item", "series_id", "series_title", "locator", "percent", "finished", "updated_at"
    }  # fmt: skip
    assert items[0]["series_id"] is None and items[0]["series_title"] is None  # ungrouped item
    assert set(items[0]["item"]) == {
        "id", "type", "title", "format", "page_count", "added_at", "has_cover"
    }  # fmt: skip


def test_continue_limit_default_cap_and_validation(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    alice = logged_in(env)
    for n in range(55):
        item = add_item(env, f"Item {n:02d}", pages=10)
        alice.put(f"/api/v1/progress/{item.id}", {"locator": 1})
        env.clock.advance(1)
    assert len(alice.get("/api/v1/progress/continue").json()["items"]) == 10
    assert len(alice.get("/api/v1/progress/continue?limit=3").json()["items"]) == 3
    assert len(alice.get("/api/v1/progress/continue?limit=50").json()["items"]) == 50
    assert len(alice.get("/api/v1/progress/continue?limit=100000").json()["items"]) == 50
    for bad in ("0", "-1", "abc", ""):
        assert alice.get(f"/api/v1/progress/continue?limit={bad}").status_code == 422


def test_removed_item_disappears_from_continue_but_progress_survives(
    db_url: str, tmp_path: Path
) -> None:
    env, item = _setup(db_url, tmp_path)
    alice = logged_in(env)
    alice.put(f"/api/v1/progress/{item.id}", {"locator": 2})
    env.container.item_repository.remove_missing(set())
    assert alice.get("/api/v1/progress/continue").json() == {"items": []}


def test_preferences_defaults_and_update(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    alice = logged_in(env)
    defaults = {"book_font_scale": 100, "book_theme": "auto"}
    assert (
        alice.get("/api/v1/me/preferences").json()
        == {
            "theme": "system",
            "reading_direction": "rtl",
        }
        | defaults
    )
    saved = {"theme": "dark", "reading_direction": "vertical"} | defaults
    # The pre-0008 body (two fields) still works and keeps the book settings.
    assert (
        alice.put(
            "/api/v1/me/preferences", {"theme": "dark", "reading_direction": "vertical"}
        ).json()
        == saved
    )
    assert alice.get("/api/v1/me/preferences").json() == saved
    again = logged_in(env)  # a new session still sees what was saved
    assert again.get("/api/v1/me/preferences").json() == saved
    assert again.get("/api/v1/auth/me").json()["theme_pref"] == "dark"


@pytest.mark.parametrize(
    "body",
    [
        {"theme": "blue", "reading_direction": "rtl"},
        {"theme": "dark", "reading_direction": "diagonal"},
        {"theme": "dark"},
        {"reading_direction": "rtl"},
        {"theme": "dark", "reading_direction": "rtl", "role": "admin"},
        {"theme": 1, "reading_direction": "rtl"},
        {"theme": None, "reading_direction": None},
        {},
        [],
    ],
)
def test_invalid_preferences_are_a_generic_422_and_change_nothing(
    db_url: str, tmp_path: Path, body: object
) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    alice = logged_in(env)
    response = alice.put("/api/v1/me/preferences", body)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    assert alice.get("/api/v1/me/preferences").json() == {
        "theme": "system",
        "reading_direction": "rtl",
        "book_font_scale": 100,
        "book_theme": "auto",
    }


def test_normal_page_turning_is_not_rate_limited(db_url: str, tmp_path: Path) -> None:
    """Default global limit (600/min, burst 200): a reader saving every page stays far below it."""
    env, _ = library_env(
        db_url,
        tmp_path,
        scan=False,
        RATE_LIMIT_API_BURST=200,
        RATE_LIMIT_API_PER_MINUTE=600,
    )
    item = add_item(env, "Long", pages=200)
    alice = logged_in(env)
    for page in range(120):  # two requests per page turn (image + progress) would be 240/2 min
        assert alice.put(f"/api/v1/progress/{item.id}", {"locator": page}).status_code == 200


def test_updated_at_is_utc_with_offset_on_put_get_and_continue(db_url: str, tmp_path: Path) -> None:
    env, item = _setup(db_url, tmp_path)
    alice = logged_in(env)
    put = alice.put(f"/api/v1/progress/{item.id}", {"locator": 2}).json()["updated_at"]
    got = alice.get(f"/api/v1/progress/{item.id}").json()["updated_at"]
    listed = alice.get("/api/v1/progress/continue").json()["items"][0]["updated_at"]
    for value in (put, got, listed):
        assert value.endswith(("Z", "+00:00")), value
    assert put == got == listed
