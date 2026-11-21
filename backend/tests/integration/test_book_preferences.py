"""Reader preferences (`book_font_scale`, `book_theme`) of GET/PUT /api/v1/me/preferences."""

from pathlib import Path

import pytest
from app.adapters.persistence.preferences_repository import SqlAlchemyPreferencesRepository
from app.domain.preferences import InvalidPreferences, Preferences
from app.services.preferences_service import PreferencesService
from sqlalchemy import text

from auth_fakes import PASSWORD
from library_env import library_env, logged_in

URL = "/api/v1/me/preferences"
BASE = {"theme": "dark", "reading_direction": "ltr"}


def test_defaults_then_full_update(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    alice = logged_in(env)
    assert alice.get(URL).json() == {
        "theme": "system",
        "reading_direction": "rtl",
        "book_font_scale": 100,
        "book_theme": "auto",
    }
    full = BASE | {"book_font_scale": 170, "book_theme": "sepia"}
    assert alice.put(URL, full).json() == full
    assert alice.get(URL).json() == full
    assert logged_in(env).get(URL).json() == full  # server-authoritative: a new session sees it


def test_old_two_field_put_keeps_the_book_settings(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    alice = logged_in(env)
    alice.put(URL, BASE | {"book_font_scale": 150, "book_theme": "dark"})
    saved = alice.put(URL, {"theme": "light", "reading_direction": "rtl"}).json()
    assert saved == {
        "theme": "light",
        "reading_direction": "rtl",
        "book_font_scale": 150,
        "book_theme": "dark",
    }
    only_one = alice.put(URL, {"theme": "light", "reading_direction": "rtl", "book_theme": "auto"})
    assert only_one.json()["book_font_scale"] == 150 and only_one.json()["book_theme"] == "auto"
    nulls = alice.put(
        URL,
        {"theme": "dark", "reading_direction": "rtl", "book_font_scale": None, "book_theme": None},
    )
    assert nulls.json()["book_font_scale"] == 150 and nulls.json()["book_theme"] == "auto"


@pytest.mark.parametrize("scale", [80, 100, 200])
def test_font_scale_bounds_are_inclusive(db_url: str, tmp_path: Path, scale: int) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    alice = logged_in(env)
    assert alice.put(URL, BASE | {"book_font_scale": scale}).json()["book_font_scale"] == scale


@pytest.mark.parametrize(
    "extra",
    [
        {"book_font_scale": 79},
        {"book_font_scale": 201},
        {"book_font_scale": 0},
        {"book_font_scale": -100},
        {"book_font_scale": "150"},
        {"book_font_scale": 150.5},
        {"book_font_scale": True},
        {"book_font_scale": [100]},
        {"book_theme": "blue"},
        {"book_theme": "SEPIA"},
        {"book_theme": 1},
        {"book_theme": "dark</style>"},
        {"book_theme": ["dark"]},
        {"fontsize": 100},
        {"role": "admin"},
    ],
)
def test_invalid_book_settings_are_a_generic_422_and_change_nothing(
    db_url: str, tmp_path: Path, extra: dict[str, object]
) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    alice = logged_in(env)
    before = alice.get(URL).json()
    response = alice.put(URL, BASE | extra)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    assert alice.get(URL).json() == before


def test_book_settings_are_per_user(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    env.create_user("bob", PASSWORD)
    alice, bob = logged_in(env, "alice"), logged_in(env, "bob")
    alice.put(URL, BASE | {"book_font_scale": 190, "book_theme": "sepia"})
    assert bob.get(URL).json()["book_font_scale"] == 100
    assert bob.get(URL).json()["book_theme"] == "auto"
    assert logged_in(env, "alice").get(URL).json()["book_theme"] == "sepia"


def test_anonymous_cannot_read_or_write(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    anon = env.client()
    anon.csrf()
    assert anon.get(URL).status_code == 401
    assert anon.put(URL, BASE | {"book_font_scale": 120}).status_code == 401


def test_repository_roundtrip_and_service_patch(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    repo = SqlAlchemyPreferencesRepository(env.container.session_factory)
    with env.container.session_factory() as session:
        user_id = session.execute(
            text("SELECT id FROM users WHERE username = 'alice'")
        ).scalar_one()
    assert repo.get(user_id) == Preferences("system", "rtl", 100, "auto")
    assert repo.set(user_id, Preferences("light", "ltr", 120, "sepia")) is True
    assert repo.get(user_id) == Preferences("light", "ltr", 120, "sepia")
    service = PreferencesService(repo)
    kept = service.patch(user_id, Preferences("dark", "rtl"))
    assert (kept.book_font_scale, kept.book_theme) == (120, "sepia")
    changed = service.patch(user_id, Preferences("dark", "rtl"), book_font_scale=90)
    assert (changed.book_font_scale, changed.book_theme) == (90, "sepia")
    assert repo.get(user_id) == changed


@pytest.mark.parametrize(
    "scale, theme", [(79, "auto"), (201, "auto"), (True, "auto"), (100, "x"), ("100", "auto")]
)
def test_domain_refuses_values_outside_the_set(scale: object, theme: str) -> None:
    with pytest.raises(InvalidPreferences):
        Preferences("dark", "rtl", scale, theme)  # type: ignore[arg-type]
