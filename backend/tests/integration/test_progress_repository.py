"""Progress repository on a real SQLite file: upsert races, CASCADE and per-user scoping."""

import threading
import uuid
from dataclasses import replace
from datetime import timedelta

from app.adapters.persistence.db import create_db_engine, create_session_factory
from app.adapters.persistence.migrator import upgrade
from app.adapters.persistence.preferences_repository import SqlAlchemyPreferencesRepository
from app.adapters.persistence.progress_repository import SqlAlchemyProgressRepository
from app.adapters.persistence.user_repository import SqlAlchemyUserRepository
from app.domain.preferences import Preferences
from app.domain.progress import Progress
from sqlalchemy import text

from auth_fakes import START, FakeClock, make_user


def _progress(user_id: str, item_id: str, locator: int = 1, minutes: int = 0) -> Progress:
    return Progress(
        user_id=user_id,
        item_id=item_id,
        locator=locator,
        percent=float(locator),
        finished=False,
        updated_at=START + timedelta(minutes=minutes),
        device_id="d",
    )


class Rig:
    def __init__(self, db_url: str) -> None:
        upgrade(db_url)
        self.engine = create_db_engine(db_url)
        self.factory = create_session_factory(self.engine)
        self.users = SqlAlchemyUserRepository(self.factory)
        self.progress = SqlAlchemyProgressRepository(self.factory)
        for name in ("alice", "bob"):
            self.users.add(make_user(name))

    def item(self, title: str, pages: int = 10) -> str:
        from app.adapters.persistence.item_repository import SqlAlchemyItemRepository
        from app.domain.item import Item, ItemType

        item = Item(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, title)),
            type=ItemType.MANGA,
            title=title,
            rel_path=f"{title}.cbz",
            format="cbz",
            page_count=pages,
            size=1,
            mtime_ns=1,
            added_at=START,
        )
        SqlAlchemyItemRepository(self.factory, FakeClock()).add(item)
        return item.id

    def count(self, table: str) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())  # noqa: S608


def test_upsert_replaces_and_get_round_trips(db_url: str) -> None:
    rig = Rig(db_url)
    item = rig.item("a")
    rig.progress.upsert(_progress("id-alice", item, 2))
    rig.progress.upsert(replace(_progress("id-alice", item, 5, minutes=1), device_id=None))
    got = rig.progress.get("id-alice", item)
    assert got is not None and got.locator == 5 and got.device_id is None
    assert got.updated_at == START + timedelta(minutes=1)  # aware UTC round trip
    assert rig.count("reading_progress") == 1
    assert rig.progress.get("id-bob", item) is None


def test_concurrent_upserts_do_not_fail_and_leave_one_row(db_url: str) -> None:
    rig = Rig(db_url)
    item = rig.item("a")
    errors: list[BaseException] = []
    barrier = threading.Barrier(16)

    def worker(n: int) -> None:
        try:
            barrier.wait()
            for i in range(10):
                rig.progress.upsert(_progress("id-alice", item, (n * 10 + i) % 10))
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert rig.count("reading_progress") == 1
    assert rig.progress.get("id-alice", item) is not None


def test_cascade_when_the_item_or_the_user_is_deleted(db_url: str) -> None:
    rig = Rig(db_url)
    a, b = rig.item("a"), rig.item("b")
    for user in ("id-alice", "id-bob"):
        rig.progress.upsert(_progress(user, a))
        rig.progress.upsert(_progress(user, b))
    assert rig.count("reading_progress") == 4
    with rig.engine.begin() as conn:
        conn.execute(text("DELETE FROM items WHERE id = :i"), {"i": a})
    assert rig.count("reading_progress") == 2
    with rig.engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = 'id-alice'"))
    assert rig.count("reading_progress") == 1
    assert rig.progress.get("id-bob", b) is not None


def test_list_continue_is_scoped_ordered_and_limited(db_url: str) -> None:
    rig = Rig(db_url)
    ids = [rig.item(t) for t in ("a", "b", "c")]
    for minutes, item in enumerate(ids):
        rig.progress.upsert(_progress("id-alice", item, minutes=minutes))
    rig.progress.upsert(_progress("id-bob", ids[0], minutes=99))
    rig.progress.upsert(replace(_progress("id-alice", ids[0], minutes=50), finished=True))
    entries = rig.progress.list_continue("id-alice", 10)
    assert [e.item.id for e in entries] == [ids[2], ids[1]]  # finished excluded, newest first
    assert [e.item.id for e in rig.progress.list_continue("id-alice", 1)] == [ids[2]]


def test_preferences_repository_targets_only_its_columns(db_url: str) -> None:
    rig = Rig(db_url)
    prefs = SqlAlchemyPreferencesRepository(rig.factory)
    assert prefs.get("id-alice") == Preferences("system", "rtl")
    assert prefs.set("id-alice", Preferences("light", "ltr")) is True
    assert prefs.get("id-alice") == Preferences("light", "ltr")
    assert prefs.get("id-bob") == Preferences("system", "rtl")
    assert prefs.set("ghost", Preferences("dark", "rtl")) is False
    assert prefs.get("ghost") is None
    user = rig.users.get_by_id("id-alice")
    assert user is not None and user.theme_pref == "light" and user.is_active
