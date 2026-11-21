"""Authorization of the progress and preferences routes: anonymous, other user (IDOR), CSRF."""

from pathlib import Path

import pytest
from app.domain.user import Role

from auth_fakes import PASSWORD
from library_env import add_item, library_env, logged_in

MISSING_ID = "00000000-0000-4000-8000-000000000000"


def test_anonymous_gets_401_everywhere(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    item = add_item(env, "One")
    anon = env.client()
    anon.csrf()
    base = f"/api/v1/progress/{item.id}"
    assert anon.get(base).status_code == 401
    assert anon.get("/api/v1/progress/continue").status_code == 401
    assert anon.put(base, {"locator": 0}).status_code == 401
    assert anon.delete(base).status_code == 401
    assert anon.get("/api/v1/me/preferences").status_code == 401
    prefs = {"theme": "dark", "reading_direction": "ltr"}
    assert anon.put("/api/v1/me/preferences", prefs).status_code == 401


def test_a_user_never_reads_or_changes_another_users_progress(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    env.create_user("bob", PASSWORD, role=Role.USER)
    item = add_item(env, "One", pages=10)
    alice, bob = logged_in(env, "alice"), logged_in(env, "bob")
    url = f"/api/v1/progress/{item.id}"

    assert alice.put(url, {"locator": 3}).status_code == 200
    assert bob.get(url).status_code == 404  # bob has no progress of his own
    assert bob.get("/api/v1/progress/continue").json() == {"items": []}

    assert bob.put(url, {"locator": 8}).status_code == 200
    assert bob.delete(url).status_code == 204
    assert alice.get(url).json()["locator"] == 3  # bob's write and delete never touched alice's


def test_preferences_are_per_user(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    env.create_user("bob", PASSWORD)
    alice, bob = logged_in(env, "alice"), logged_in(env, "bob")
    saved = {"theme": "dark", "reading_direction": "vertical"}
    assert alice.put("/api/v1/me/preferences", saved).status_code == 200
    assert bob.get("/api/v1/me/preferences").json() == {
        "theme": "system",
        "reading_direction": "rtl",
    }
    assert alice.get("/api/v1/me/preferences").json() == saved


def test_writes_require_csrf(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    item = add_item(env, "One")
    alice = logged_in(env)
    plain = {"Origin": alice.ORIGIN}  # no X-CSRF-Token
    http = alice.http
    assert (
        http.put(f"/api/v1/progress/{item.id}", json={"locator": 0}, headers=plain).status_code
        == 403
    )
    assert http.delete(f"/api/v1/progress/{item.id}", headers=plain).status_code == 403
    prefs = {"theme": "dark", "reading_direction": "ltr"}
    assert http.put("/api/v1/me/preferences", json=prefs, headers=plain).status_code == 403
    assert alice.get(f"/api/v1/progress/{item.id}").status_code == 404  # nothing was written


@pytest.mark.parametrize("bad_id", ["x", "1", "../etc/passwd", "A" * 36, "0" * 36, "continue2"])
def test_malformed_ids_are_a_generic_404(db_url: str, tmp_path: Path, bad_id: str) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    alice = logged_in(env)
    assert alice.get(f"/api/v1/progress/{bad_id}").status_code == 404
    assert alice.put(f"/api/v1/progress/{bad_id}", {"locator": 0}).status_code == 404
    assert alice.delete(f"/api/v1/progress/{bad_id}").status_code == 404


def test_responses_are_no_store_and_never_leak_paths(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    item = add_item(env, "One", rel_path="secret/dir/one.cbz")
    alice = logged_in(env)
    put = alice.put(f"/api/v1/progress/{item.id}", {"locator": 0})
    cont = alice.get("/api/v1/progress/continue")
    for response in (put, cont, alice.get("/api/v1/me/preferences")):
        assert "no-store" in response.headers["cache-control"]
        assert "secret" not in response.text and "rel_path" not in response.text
    assert set(put.json()) == {"item_id", "locator", "percent", "finished", "updated_at"}
