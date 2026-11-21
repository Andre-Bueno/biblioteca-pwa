"""Series routes need a session; progress shown is always the caller's; nothing leaks a path."""

import uuid
from pathlib import Path

import pytest

from library_env import ORV, logged_in, series_env, series_id_by_title


@pytest.mark.parametrize("suffix", ["", "/cover"])
def test_anonymous_gets_401_before_any_id_check(db_url: str, tmp_path: Path, suffix: str) -> None:
    env, _ = series_env(db_url, tmp_path)
    sid = series_id_by_title(logged_in(env), ORV)
    anonymous = env.client()
    assert anonymous.get("/api/v1/series").status_code == 401
    assert anonymous.get(f"/api/v1/series/{sid}{suffix}").status_code == 401
    # an invalid or unknown id must not be distinguishable from a valid one without a session
    assert anonymous.get(f"/api/v1/series/not-an-id{suffix}").status_code == 401
    assert anonymous.get(f"/api/v1/series/{uuid.uuid4()}{suffix}").status_code == 401


def test_garbage_or_foreign_tokens_are_refused(db_url: str, tmp_path: Path) -> None:
    env, _ = series_env(db_url, tmp_path)
    client = env.client()
    for token in ("garbage", "a.b.c", ""):
        assert client.get("/api/v1/series", cookies={"access_token": token}).status_code == 401


def test_series_routes_do_not_accept_writes(db_url: str, tmp_path: Path) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice = logged_in(env)
    sid = series_id_by_title(alice, ORV)
    for path in ("/api/v1/series", f"/api/v1/series/{sid}", f"/api/v1/series/{sid}/cover"):
        assert alice.put(path, {"title": "x"}).status_code == 405
        assert alice.post(path, {"title": "x"}).status_code in (403, 405)
        assert alice.delete(path).status_code == 405
    assert alice.get(f"/api/v1/series/{sid}").json()["title"] == ORV


def test_one_users_reading_never_shows_for_another(db_url: str, tmp_path: Path) -> None:
    env, _ = series_env(db_url, tmp_path)
    alice, bob = logged_in(env), logged_in(env, "bob")
    sid = series_id_by_title(alice, ORV)
    chapter = alice.get(f"/api/v1/series/{sid}").json()["chapters"][2]["id"]
    assert alice.put(f"/api/v1/progress/{chapter}", {"locator": 1}).status_code == 200

    seen_by_bob = bob.get(f"/api/v1/series/{sid}").json()
    assert seen_by_bob["continue"] is None
    assert [c["progress"] for c in seen_by_bob["chapters"]] == [None] * 7
    assert chapter not in bob.get("/api/v1/series").text
    assert chapter not in bob.get("/api/v1/progress/continue").text
    # and Alice does see her own
    assert alice.get(f"/api/v1/series/{sid}").json()["continue"] == {
        "item_id": chapter,
        "locator": 1,
    }
