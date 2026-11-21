"""Progress of books over the real API: the item type decides how the locator is read."""

from pathlib import Path

import pytest
from app.domain.progress import encode_book_locator

from auth_fakes import Env
from epub_fixtures import make_epub
from library_env import add_item, book_env, item_id_by_title, logged_in


@pytest.fixture
def env(db_url: str, tmp_path: Path) -> Env:
    four = [(f"C{i}", f"<p>{i}</p>") for i in range(4)]
    return book_env(db_url, tmp_path, {"Four.epub": make_epub(chapters=four, title="Four")})[0]


def test_saving_inside_a_chapter_derives_percent_and_finished(env: Env) -> None:
    alice = logged_in(env)
    item = item_id_by_title(alice, "Four")
    url = f"/api/v1/progress/{item}"
    body = alice.put(url, {"locator": encode_book_locator(1, 5000)}).json()
    assert body["locator"] == 15_000 and body["percent"] == pytest.approx(37.5)
    assert body["finished"] is False
    last = alice.put(url, {"locator": encode_book_locator(3, 9000)}).json()
    assert last["finished"] is True and last["percent"] == pytest.approx(97.5)
    assert alice.put(url, {"locator": encode_book_locator(3, 8999)}).json()["finished"] is False
    assert alice.get(url).json()["locator"] == 38_999


@pytest.mark.parametrize("locator", [40_000, 40_001, 99_999_999, 2_147_483_647])
def test_chapter_beyond_the_book_is_a_generic_422_and_nothing_is_saved(
    env: Env, locator: int
) -> None:
    alice = logged_in(env)
    item = item_id_by_title(alice, "Four")
    alice.put(f"/api/v1/progress/{item}", {"locator": 10_000})
    response = alice.put(f"/api/v1/progress/{item}", {"locator": locator})
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    assert alice.get(f"/api/v1/progress/{item}").json()["locator"] == 10_000


def test_manga_locator_rules_did_not_change(env: Env) -> None:
    manga = add_item(env, "Manga", pages=3)
    alice = logged_in(env)
    url = f"/api/v1/progress/{manga.id}"
    assert alice.put(url, {"locator": 2}).json()["finished"] is True
    assert alice.put(url, {"locator": 3}).status_code == 422
    assert alice.put(url, {"locator": 10_000}).status_code == 422
    assert alice.get(url).json()["locator"] == 2


def test_a_finished_book_leaves_continue_reading_and_an_ongoing_one_stays(env: Env) -> None:
    alice = logged_in(env)
    item = item_id_by_title(alice, "Four")
    alice.put(f"/api/v1/progress/{item}", {"locator": 20_000})
    shown = alice.get("/api/v1/progress/continue").json()["items"]
    assert [e["item"]["id"] for e in shown] == [item] and shown[0]["locator"] == 20_000
    alice.put(f"/api/v1/progress/{item}", {"locator": 39_500})
    assert alice.get("/api/v1/progress/continue").json()["items"] == []
