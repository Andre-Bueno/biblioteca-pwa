import pytest
from app.adapters.persistence.db import create_db_engine
from app.adapters.persistence.migrator import downgrade, upgrade
from app.adapters.persistence.models import Base
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

AUTH_TABLES = {"users", "refresh_tokens", "login_attempts", "audit_log"}
TABLES = AUTH_TABLES | {"items", "reading_progress", "series"}
NOW = "2026-01-01 00:00:00"


def _tables(url: str) -> set[str]:
    engine = create_db_engine(url)
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_then_downgrade_on_empty_db(db_url: str) -> None:
    assert _tables(db_url) == set()
    upgrade(db_url)
    assert _tables(db_url) == TABLES
    downgrade(db_url)
    assert _tables(db_url) == set()
    upgrade(db_url)  # and it can go up again
    assert _tables(db_url) == TABLES


def test_upgrade_is_idempotent(db_url: str) -> None:
    upgrade(db_url)
    upgrade(db_url)
    assert _tables(db_url) == TABLES


def test_orm_models_match_migrated_schema(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    try:
        insp = inspect(engine)
        for name, table in Base.metadata.tables.items():
            migrated = {c["name"] for c in insp.get_columns(name)}
            assert {c.name for c in table.columns} == migrated, name
    finally:
        engine.dispose()


def test_expected_indexes_exist(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    try:
        insp = inspect(engine)
        with engine.connect() as conn:
            names = {
                r[0]
                for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'index'"))
            }
        assert "ux_users_username_lower" in names
        assert "ix_login_attempts_lookup" in {i["name"] for i in insp.get_indexes("login_attempts")}
        token_indexes = {i["name"] for i in insp.get_indexes("refresh_tokens")}
        assert {"ix_refresh_tokens_user_id", "ix_refresh_tokens_family_id"} <= token_indexes
    finally:
        engine.dispose()


def test_sqlite_pragmas_applied(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
            assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
    finally:
        engine.dispose()


def _insert_user(conn: object, uid: str, username: str) -> None:
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO users (id, username, password_hash, role, is_active, theme_pref, "
            "created_at, updated_at, password_changed_at) VALUES "
            "(:id, :u, 'h', 'user', 1, 'system', :t, :t, :t)"
        ),
        {"id": uid, "u": username, "t": NOW},
    )


def test_username_unique_case_insensitive(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    try:
        with engine.begin() as conn:
            _insert_user(conn, "1", "Alice")
        with pytest.raises(IntegrityError), engine.begin() as conn:
            _insert_user(conn, "2", "alice")
    finally:
        engine.dispose()


def test_token_hash_unique_and_fk_enforced(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    insert = text(
        "INSERT INTO refresh_tokens (id, user_id, family_id, token_hash, created_at, expires_at) "
        "VALUES (:id, :uid, 'f', :th, :t, :t)"
    )
    try:
        with engine.begin() as conn:
            _insert_user(conn, "u1", "alice")
            conn.execute(insert, {"id": "a", "uid": "u1", "th": "x" * 64, "t": NOW})
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(insert, {"id": "b", "uid": "u1", "th": "x" * 64, "t": NOW})
        with pytest.raises(IntegrityError), engine.begin() as conn:  # FK to missing user
            conn.execute(insert, {"id": "c", "uid": "nobody", "th": "y" * 64, "t": NOW})
    finally:
        engine.dispose()


def test_check_constraints(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, username, password_hash, role, is_active, theme_pref,"
                    " created_at, updated_at, password_changed_at) VALUES "
                    "('1', 'bob', 'h', 'root', 1, 'system', :t, :t, :t)"
                ),
                {"t": NOW},
            )
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO login_attempts (scope, key_hash, attempted_at, success) "
                    "VALUES ('galaxy', 'k', :t, 0)"
                ),
                {"t": NOW},
            )
    finally:
        engine.dispose()


def test_0002_downgrades_to_0001_and_back_keeping_auth_tables(db_url: str) -> None:
    upgrade(db_url)
    downgrade(db_url, "0001")
    assert _tables(db_url) == AUTH_TABLES  # items, reading_progress and series are gone
    upgrade(db_url)
    assert _tables(db_url) == TABLES


def _item_indexes(url: str) -> set[str]:
    engine = create_db_engine(url)
    try:
        return {i["name"] for i in inspect(engine).get_indexes("items") if i["name"]}
    finally:
        engine.dispose()


def test_0003_is_reversible_and_keeps_item_rows(db_url: str) -> None:
    upgrade(db_url, "0002")
    assert {"ix_items_title", "ix_items_missing"} <= _item_indexes(db_url)
    engine = create_db_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO items (id, type, title, rel_path, format, page_count, size, "
                    "mtime_ns, added_at, updated_at) VALUES "
                    "('a', 'manga', 't', 'a.cbz', 'cbz', 1, 1, 1, :t, :t)"
                ),
                {"t": NOW},
            )
        upgrade(db_url)
        assert not {"ix_items_title", "ix_items_missing"} & _item_indexes(db_url)
        downgrade(db_url, "0002")
        assert {"ix_items_title", "ix_items_missing"} <= _item_indexes(db_url)
        upgrade(db_url)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM items")).scalar_one() == 1
    finally:
        engine.dispose()


def test_items_indexes_and_constraints(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    insert = text(
        "INSERT INTO items (id, type, title, rel_path, format, page_count, size, mtime_ns, "
        "added_at, updated_at) VALUES (:id, :type, 't', :rel, 'cbz', :pages, 1, 1, :t, :t)"
    )
    row = {"id": "a", "type": "manga", "rel": "a.cbz", "pages": 1, "t": NOW}
    try:
        names = {i["name"] for i in inspect(engine).get_indexes("items")}
        assert {"ix_items_type", "ix_items_added_at"} <= names
        assert not {"ix_items_title", "ix_items_missing"} & names  # dropped by 0003 (unusable)
        with engine.begin() as conn:
            conn.execute(insert, row)
        with pytest.raises(IntegrityError), engine.begin() as conn:  # rel_path is unique
            conn.execute(insert, row | {"id": "b"})
        with pytest.raises(IntegrityError), engine.begin() as conn:  # unknown type
            conn.execute(insert, row | {"id": "c", "rel": "c.cbz", "type": "video"})
        with pytest.raises(IntegrityError), engine.begin() as conn:  # negative page count
            conn.execute(insert, row | {"id": "d", "rel": "d.cbz", "pages": -1})
    finally:
        engine.dispose()


def _columns(url: str, table: str) -> set[str]:
    engine = create_db_engine(url)
    try:
        return {c["name"] for c in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def test_0004_is_reversible_and_keeps_users_and_their_sessions(db_url: str) -> None:
    upgrade(db_url, "0003")
    assert "reading_direction" not in _columns(db_url, "users")
    engine = create_db_engine(db_url)
    try:
        with engine.begin() as conn:
            _insert_user(conn, "u1", "alice")
            conn.execute(
                text(
                    "INSERT INTO refresh_tokens (id, user_id, family_id, token_hash, created_at, "
                    "expires_at) VALUES ('t', 'u1', 'f', :h, :t, :t)"
                ),
                {"h": "x" * 64, "t": NOW},
            )
        upgrade(db_url)
        assert "reading_direction" in _columns(db_url, "users")
        assert "reading_progress" in _tables(db_url)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT theme_pref, reading_direction FROM users")).one()
            assert tuple(row) == ("system", "rtl")  # existing user gets the default
            assert conn.execute(text("SELECT count(*) FROM refresh_tokens")).scalar_one() == 1
        downgrade(db_url, "0003")
        assert "reading_direction" not in _columns(db_url, "users")
        assert "reading_progress" not in _tables(db_url)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
            assert conn.execute(text("SELECT count(*) FROM refresh_tokens")).scalar_one() == 1
        upgrade(db_url)
        assert "reading_direction" in _columns(db_url, "users")
    finally:
        engine.dispose()


def test_reading_progress_constraints(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    insert = text(
        "INSERT INTO reading_progress (user_id, item_id, locator, percent, finished, updated_at) "
        "VALUES (:u, :i, :l, :p, 0, :t)"
    )
    row = {"u": "u1", "i": "a", "l": 0, "p": 10.0, "t": NOW}
    try:
        with engine.begin() as conn:
            _insert_user(conn, "u1", "alice")
            conn.execute(
                text(
                    "INSERT INTO items (id, type, title, rel_path, format, page_count, size, "
                    "mtime_ns, added_at, updated_at) VALUES "
                    "('a', 'manga', 't', 'a.cbz', 'cbz', 1, 1, 1, :t, :t)"
                ),
                {"t": NOW},
            )
            conn.execute(insert, row)
        bad_rows = (
            row,  # primary key (user_id, item_id)
            row | {"i": "zzz"},  # unknown item (FK)
            row | {"u": "nobody"},  # unknown user (FK)
            row | {"l": -1},
            row | {"p": 100.5},
            row | {"p": -0.1},
        )
        for bad in bad_rows:
            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(insert, bad)
        with pytest.raises(IntegrityError), engine.begin() as conn:  # CHECK on the new column
            conn.execute(text("UPDATE users SET reading_direction = 'up'"))
        names = {i["name"] for i in inspect(engine).get_indexes("reading_progress")}
        assert "ix_reading_progress_user_updated" in names
    finally:
        engine.dispose()


def _insert_item(conn: object, item_id: str, rel_path: str, title: str = "t") -> None:
    conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO items (id, type, title, rel_path, format, page_count, size, mtime_ns, "
            "added_at, updated_at) VALUES (:id, 'manga', :title, :rel, 'cbz', 3, 1, 1, :t, :t)"
        ),
        {"id": item_id, "rel": rel_path, "title": title, "t": NOW},
    )


def test_0005_backfills_series_and_downgrades_keeping_items_and_progress(db_url: str) -> None:
    upgrade(db_url, "0004")
    assert "series" not in _tables(db_url)
    engine = create_db_engine(db_url)
    try:
        with engine.begin() as conn:
            _insert_user(conn, "u1", "alice")
            _insert_item(conn, "a", "Saga/Capitulo - 1.cbz", "Capitulo - 1")
            _insert_item(conn, "b", "Saga/Capitulo - 10.cbz", "Capitulo - 10")
            _insert_item(conn, "c", "Pub/Deep  Series/Cap 2.cbz", "Cap 2")
            _insert_item(conn, "d", "Berserk v03.cbz", "Berserk v03")
            _insert_item(conn, "e", "Solo.cbz", "Solo")
            conn.execute(
                text(
                    "INSERT INTO reading_progress (user_id, item_id, locator, percent, finished, "
                    "updated_at) VALUES ('u1', 'a', 1, 66.0, 0, :t)"
                ),
                {"t": NOW},
            )
        upgrade(db_url)
        assert {"series_id", "chapter_number"} <= _columns(db_url, "items")
        with engine.connect() as conn:
            links = dict(conn.execute(text("SELECT id, series_id FROM items")).all())
            assert all(links.values())  # every existing item got a series
            assert links["a"] == links["b"]  # same folder, same series
            assert len({links["a"], links["c"], links["d"], links["e"]}) == 4
            series = {
                r.id: r
                for r in conn.execute(
                    text("SELECT id, title, folder_rel_path, metadata_state FROM series")
                )
            }
            assert len(series) == 4  # Saga, Deep Series, Berserk v03 and Solo (standalone)
            assert (series[links["a"]].title, series[links["a"]].folder_rel_path) == (
                "Saga",
                "Saga",
            )
            assert series[links["c"]].title == "Deep Series"  # whitespace collapsed
            assert series[links["c"]].folder_rel_path == "Pub/Deep  Series"
            assert series[links["e"]].folder_rel_path is None  # loose file: standalone
            assert {s.metadata_state for s in series.values()} == {"none"}
            assert (
                conn.execute(
                    text("SELECT count(*) FROM items WHERE chapter_number IS NOT NULL")
                ).scalar_one()
                == 0
            )
            assert conn.execute(text("SELECT count(*) FROM reading_progress")).scalar_one() == 1
        downgrade(db_url, "0004")
        assert not {"series_id", "chapter_number"} & _columns(db_url, "items")
        assert "series" not in _tables(db_url)
        assert "ix_items_series_id" not in _item_indexes(db_url)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM items")).scalar_one() == 5
            # progress is still there: the downgrade never rebuilt (and so never emptied) `items`
            assert conn.execute(text("SELECT count(*) FROM reading_progress")).scalar_one() == 1
        upgrade(db_url)  # up again: the backfill runs again on the same data
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM series")).scalar_one() == 4
            assert (
                conn.execute(
                    text("SELECT count(*) FROM items WHERE series_id IS NULL")
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


def test_0005_on_an_empty_library_and_series_constraints(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    insert = text(
        "INSERT INTO series (id, title, sort_title, folder_rel_path, metadata_state, created_at, "
        "updated_at) VALUES (:id, 't', 't', :folder, :state, :t, :t)"
    )
    row = {"id": "s1", "folder": "Saga", "state": "none", "t": NOW}
    try:
        with engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM series")).scalar_one() == 0
            conn.execute(insert, row)
            conn.execute(insert, row | {"id": "s2", "folder": None})
            conn.execute(insert, row | {"id": "s3", "folder": None})  # NULL is not "equal" to NULL
        with pytest.raises(IntegrityError), engine.begin() as conn:  # folder is unique
            conn.execute(insert, row | {"id": "s4"})
        with pytest.raises(IntegrityError), engine.begin() as conn:  # state is a closed set
            conn.execute(insert, row | {"id": "s5", "folder": "x", "state": "weird"})
        with engine.begin() as conn:
            _insert_item(conn, "i1", "Saga/Cap 1.cbz")
            conn.execute(text("UPDATE items SET series_id = 's1', chapter_number = 1.5"))
        with pytest.raises(IntegrityError), engine.begin() as conn:  # FK to a missing series
            conn.execute(text("UPDATE items SET series_id = 'nope'"))
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM series WHERE id = 's1'"))  # ON DELETE SET NULL
        with engine.connect() as conn:
            assert conn.execute(text("SELECT series_id FROM items")).scalar_one() is None
            assert conn.execute(text("SELECT chapter_number FROM items")).scalar_one() == 1.5
        assert "ix_items_series_id" in _item_indexes(migrated_url)
    finally:
        engine.dispose()


NEW_SERIES_COLUMNS = {"source_url", "metadata_checked_at", "title_original"}


def test_0006_adds_nullable_columns_and_downgrades_keeping_everything_else(db_url: str) -> None:
    upgrade(db_url, "0005")
    assert not NEW_SERIES_COLUMNS & _columns(db_url, "series")
    engine = create_db_engine(db_url)
    try:
        with engine.begin() as conn:
            _insert_user(conn, "u1", "alice")
            _insert_item(conn, "a", "Saga/Capitulo - 1.cbz", "Capitulo - 1")
            conn.execute(
                text(
                    "INSERT INTO reading_progress (user_id, item_id, locator, percent, finished, "
                    "updated_at) VALUES ('u1', 'a', 1, 50.0, 0, :t)"
                ),
                {"t": NOW},
            )
            conn.execute(
                text(
                    "INSERT INTO series (id, title, sort_title, folder_rel_path, description, "
                    "description_lang, metadata_source, external_id, metadata_state, cover_path, "
                    "created_at, updated_at) VALUES ('s1', 'Saga', 'saga', 'Saga', 'kept', "
                    "'pt-br', 'mangadex', 'x', 'matched', 'c.jpg', :t, :t)"
                ),
                {"t": NOW},
            )
            conn.execute(text("UPDATE items SET series_id = 's1'"))
        upgrade(db_url)
        assert _columns(db_url, "series") >= NEW_SERIES_COLUMNS
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT description, description_lang, metadata_source, metadata_state, "
                    "cover_path, source_url, metadata_checked_at, title_original FROM series"
                )
            ).one()
            assert tuple(row) == ("kept", "pt-br", "mangadex", "matched", "c.jpg", None, None, None)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE series SET source_url = 'https://mangadex.org/title/x', "
                    "metadata_checked_at = :t, title_original = 'Saga (orig)'"
                ),
                {"t": NOW},
            )
        with pytest.raises(IntegrityError), engine.begin() as conn:  # CHECK still guards the state
            conn.execute(text("UPDATE series SET metadata_state = 'weird'"))
        downgrade(db_url, "0005")
        assert not NEW_SERIES_COLUMNS & _columns(db_url, "series")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT title, description, metadata_state, cover_path FROM series")
            ).one()
            assert tuple(row) == ("Saga", "kept", "matched", "c.jpg")
            assert conn.execute(text("SELECT count(*) FROM items")).scalar_one() == 1
            # progress survives: no table was rebuilt, so no cascade ran
            assert conn.execute(text("SELECT count(*) FROM reading_progress")).scalar_one() == 1
        upgrade(db_url)
        assert _columns(db_url, "series") >= NEW_SERIES_COLUMNS
    finally:
        engine.dispose()


ATTRIBUTION_COLUMNS = {"description_origin", "description_source_name", "description_source_url"}


def test_0007_adds_attribution_backfills_and_downgrades_keeping_data(db_url: str) -> None:
    upgrade(db_url, "0006")
    assert not ATTRIBUTION_COLUMNS & _columns(db_url, "series")
    insert = text(
        "INSERT INTO series (id, title, sort_title, folder_rel_path, description, "
        "metadata_source, source_url, metadata_state, created_at, updated_at) VALUES "
        "(:id, :id, :id, :id, :d, :src, :url, :state, :t, :t)"
    )
    rows = [
        {
            "id": "md",
            "d": "from md",
            "src": "mangadex",
            "url": "https://mangadex.org/title/x",
            "state": "matched",
        },
        {"id": "al", "d": "from al", "src": "anilist", "url": None, "state": "matched"},
        {"id": "hand", "d": "typed", "src": None, "url": None, "state": "manual"},
        {"id": "bare", "d": None, "src": None, "url": None, "state": "none"},
    ]
    engine = create_db_engine(db_url)
    try:
        with engine.begin() as conn:
            for row in rows:
                conn.execute(insert, row | {"t": NOW})
        upgrade(db_url)
        assert _columns(db_url, "series") >= ATTRIBUTION_COLUMNS
        with engine.connect() as conn:
            got = {
                r.id: (r.description_origin, r.description_source_name, r.description_source_url)
                for r in conn.execute(
                    text(
                        "SELECT id, description_origin, description_source_name, "
                        "description_source_url FROM series"
                    )
                )
            }
        assert got == {
            "md": ("source", "MangaDex", "https://mangadex.org/title/x"),
            "al": ("source", "AniList", None),
            "hand": ("manual", None, None),
            "bare": (None, None, None),
        }
        for value in ("source", "translated", "manual", None):
            with engine.begin() as conn:
                conn.execute(text("UPDATE series SET description_origin = :v"), {"v": value})
        with pytest.raises(IntegrityError), engine.begin() as conn:  # a closed set
            conn.execute(text("UPDATE series SET description_origin = 'machine'"))
        downgrade(db_url, "0006")
        assert not ATTRIBUTION_COLUMNS & _columns(db_url, "series")
        with engine.connect() as conn:
            kept = dict(conn.execute(text("SELECT id, description FROM series")).all())
        assert kept == {"md": "from md", "al": "from al", "hand": "typed", "bare": None}
        upgrade(db_url)
        assert _columns(db_url, "series") >= ATTRIBUTION_COLUMNS
    finally:
        engine.dispose()


BOOK_COLUMNS = {"book_font_scale", "book_theme"}


def test_0008_adds_book_preferences_and_downgrades_keeping_users_and_sessions(db_url: str) -> None:
    upgrade(db_url, "0007")
    assert not BOOK_COLUMNS & _columns(db_url, "users")
    engine = create_db_engine(db_url)
    try:
        with engine.begin() as conn:
            _insert_user(conn, "u1", "alice")
            conn.execute(
                text(
                    "INSERT INTO refresh_tokens (id, user_id, family_id, token_hash, created_at, "
                    "expires_at) VALUES ('t', 'u1', 'f', :h, :t, :t)"
                ),
                {"h": "x" * 64, "t": NOW},
            )
            _insert_item(conn, "a", "Saga/Cap 1.cbz")
            conn.execute(
                text(
                    "INSERT INTO reading_progress (user_id, item_id, locator, percent, finished, "
                    "updated_at) VALUES ('u1', 'a', 1, 50.0, 0, :t)"
                ),
                {"t": NOW},
            )
        upgrade(db_url)
        assert _columns(db_url, "users") >= BOOK_COLUMNS
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT theme_pref, reading_direction, book_font_scale, book_theme FROM users")
            ).one()
            assert tuple(row) == ("system", "rtl", 100, "auto")  # the existing user got defaults
        for scale, theme in ((80, "auto"), (200, "light"), (150, "dark"), (100, "sepia")):
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE users SET book_font_scale = :s, book_theme = :t"),
                    {"s": scale, "t": theme},
                )
        for bad in (
            "UPDATE users SET book_font_scale = 79",
            "UPDATE users SET book_font_scale = 201",
            "UPDATE users SET book_theme = 'neon'",
            "UPDATE users SET book_font_scale = NULL",
            "UPDATE users SET book_theme = NULL",
        ):
            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(text(bad))
        downgrade(db_url, "0007")
        assert not BOOK_COLUMNS & _columns(db_url, "users")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 1
            assert conn.execute(text("SELECT count(*) FROM refresh_tokens")).scalar_one() == 1
            # no table rebuild: nothing was cascaded away
            assert conn.execute(text("SELECT count(*) FROM reading_progress")).scalar_one() == 1
            assert conn.execute(text("SELECT count(*) FROM items")).scalar_one() == 1
        upgrade(db_url)
        assert _columns(db_url, "users") >= BOOK_COLUMNS
    finally:
        engine.dispose()
