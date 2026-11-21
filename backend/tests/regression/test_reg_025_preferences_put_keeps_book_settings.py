"""test_reg_025: a PUT of the preferences without the book fields must not reset them.

Bug risk (migration 0008): `PreferencesIn.to_domain()` fills the book fields with their defaults, so
a client that only knows `theme` and `reading_direction` (the contract before 0008) would silently
reset the reader's font scale and theme on every save. Cause: omitted fields were treated as
"default" instead of "keep what is saved".
"""

from pathlib import Path

from library_env import library_env, logged_in


def test_reg_025_old_put_does_not_reset_book_settings(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    alice = logged_in(env)
    url = "/api/v1/me/preferences"
    alice.put(
        url,
        {
            "theme": "dark",
            "reading_direction": "ltr",
            "book_font_scale": 160,
            "book_theme": "sepia",
        },
    )
    saved = alice.put(url, {"theme": "light", "reading_direction": "rtl"}).json()
    assert (saved["book_font_scale"], saved["book_theme"]) == (160, "sepia")
    assert alice.get(url).json() == saved
