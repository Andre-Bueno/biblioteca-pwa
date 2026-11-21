"""SqlAlchemyItemRepository on a real migrated SQLite database."""

import uuid
from dataclasses import replace
from datetime import timedelta

import pytest
from app.adapters.persistence.audit_log import SqlAlchemyAuditLog
from app.adapters.persistence.item_repository import SqlAlchemyItemRepository, escape_like
from app.adapters.persistence.models import AuditLogRow, ItemRow
from app.domain.errors import ItemNotFound
from app.domain.item import Item, ItemType
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from auth_fakes import START, FakeClock


def make_item(
    title: str = "Title",
    rel_path: str | None = None,
    *,
    item_type: ItemType = ItemType.MANGA,
    pages: int = 3,
) -> Item:
    return Item(
        id=str(uuid.uuid4()),
        type=item_type,
        title=title,
        rel_path=rel_path or f"{uuid.uuid4()}.cbz",
        format="cbz",
        page_count=pages,
        size=10,
        mtime_ns=1_700_000_000_000_000_000,
        added_at=START,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def repo(session_factory: sessionmaker[Session], clock: FakeClock) -> SqlAlchemyItemRepository:
    return SqlAlchemyItemRepository(session_factory, clock)


def test_add_get_roundtrip_and_update(repo: SqlAlchemyItemRepository, clock: FakeClock) -> None:
    item = make_item("Vol 1", "a/Vol 1.cbz")
    repo.add(item)
    assert repo.get(item.id) == item
    assert repo.get_by_rel_path("a/Vol 1.cbz") == item
    assert repo.get("nope") is None

    clock.advance(60)
    repo.update(replace(item, page_count=9, content_hash="h" * 64))
    loaded = repo.get(item.id)
    assert loaded is not None
    assert (loaded.page_count, loaded.content_hash) == (9, "h" * 64)
    with pytest.raises(ItemNotFound):
        repo.update(make_item())


def test_updated_at_comes_from_the_injected_clock(
    repo: SqlAlchemyItemRepository, session_factory: sessionmaker[Session], clock: FakeClock
) -> None:
    item = make_item()
    repo.add(item)
    clock.advance(3600)
    repo.update(item)
    with session_factory() as session:
        row = session.get(ItemRow, item.id)
        assert row is not None
        assert row.updated_at == clock.now()


def test_list_is_stably_ordered_and_pages_do_not_overlap(repo: SqlAlchemyItemRepository) -> None:
    # Same title on purpose: the id breaks the tie so paging stays deterministic.
    items = [make_item("Same") for _ in range(7)] + [make_item("alpha"), make_item("Zeta")]
    for item in items:
        repo.add(item)
    pages = [repo.list(offset, 4) for offset in (0, 4, 8)]
    seen = [i.id for page in pages for i in page]
    assert sorted(seen) == sorted(i.id for i in items)
    assert len(seen) == len(set(seen)) == 9
    assert [i.title for i in repo.list(0, 100)][0] == "alpha"  # case-insensitive order
    assert [i.id for i in repo.list(0, 100)] == seen
    assert repo.list(100, 10) == []


def test_type_filter(repo: SqlAlchemyItemRepository) -> None:
    repo.add(make_item("m", item_type=ItemType.MANGA))
    repo.add(make_item("b", item_type=ItemType.BOOK))
    assert [i.title for i in repo.list(0, 10, ItemType.BOOK)] == ["b"]
    assert [i.title for i in repo.search("m", 0, 10, ItemType.BOOK)] == []
    assert [i.title for i in repo.search("m", 0, 10, ItemType.MANGA)] == ["m"]


def test_remove_missing_hides_items_and_revive_keeps_id(repo: SqlAlchemyItemRepository) -> None:
    keep, gone = make_item("keep", "keep.cbz"), make_item("gone", "gone.cbz")
    repo.add(keep)
    repo.add(gone)
    assert repo.remove_missing({"keep.cbz"}) == 1
    assert repo.remove_missing({"keep.cbz"}) == 0  # already flagged: not counted again
    assert repo.get(gone.id) is None
    assert [i.title for i in repo.list(0, 10)] == ["keep"]
    assert repo.search("gone", 0, 10) == []
    hidden = repo.get_by_rel_path("gone.cbz")
    assert hidden is not None
    assert hidden.missing

    repo.update(replace(hidden, missing=False))
    assert repo.get(gone.id) is not None


def test_remove_missing_handles_more_rows_than_one_sql_chunk(
    repo: SqlAlchemyItemRepository,
) -> None:
    for i in range(1_200):
        repo.add(make_item(f"t{i}", f"f{i}.cbz"))
    assert repo.remove_missing({"f0.cbz"}) == 1_199
    assert [i.rel_path for i in repo.list(0, 10)] == ["f0.cbz"]


TITLES = [
    "100% real",
    "snake_case",
    'say "hi"',
    "it's here",
    "back\\slash",
    "Ação Épica",
    "plain title",
    "日本語のタイトル",
]


@pytest.fixture
def titled(repo: SqlAlchemyItemRepository) -> SqlAlchemyItemRepository:
    for title in TITLES:
        repo.add(make_item(title))
    return repo


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("%", ["100% real"]),  # a literal percent sign, not "match everything"
        ("_", ["snake_case"]),  # a literal underscore, not "any char"
        ("\\", ["back\\slash"]),
        ("k\\s", ["back\\slash"]),
        ('"hi"', ['say "hi"']),
        ("'", ["it's here"]),
        ("ação", ["Ação Épica"]),
        ("日本語", ["日本語のタイトル"]),
        ("PLAIN", ["plain title"]),
        ("%l", []),  # would match "real"/"plain" if % acted as a wildcard
        ("s_ake", []),  # would match "snake" if _ acted as a wildcard
        ("100%_", []),
    ],
)
def test_search_treats_wildcards_literally(
    titled: SqlAlchemyItemRepository, query: str, expected: list[str]
) -> None:
    assert [i.title for i in titled.search(query, 0, 50)] == expected


@pytest.mark.parametrize(
    "payload",
    [
        "' OR '1'='1",
        "'; DROP TABLE items; --",
        '" OR 1=1 --',
        "%' UNION SELECT password_hash FROM users --",
        "a\x00b",
        "\\' OR 1=1",
    ],
)
def test_search_is_not_injectable(
    titled: SqlAlchemyItemRepository,
    session_factory: sessionmaker[Session],
    payload: str,
) -> None:
    assert titled.search(payload, 0, 50) == []
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ItemRow)) == len(TITLES)
    assert len(titled.list(0, 50)) == len(TITLES)


def test_escape_like() -> None:
    assert escape_like("a%b_c\\d") == "a\\%b\\_c\\\\d"
    assert escape_like("plain") == "plain"


def test_items_table_matches_the_model(session_factory: sessionmaker[Session]) -> None:
    engine = session_factory.kw["bind"]
    migrated = {c["name"] for c in inspect(engine).get_columns("items")}
    assert migrated == {c.name for c in ItemRow.__table__.columns}


# ---------------------------------------------------------------- audit retention


def test_audit_purge_deletes_only_older_events(
    session_factory: sessionmaker[Session], clock: FakeClock
) -> None:
    audit = SqlAlchemyAuditLog(session_factory, clock)
    audit.record("old.one")
    clock.advance(86_400 * 10)
    audit.record("old.two")
    clock.advance(86_400 * 10)
    audit.record("recent")
    assert audit.purge(clock.now() - timedelta(days=15)) == 1  # only "old.one" is 20 days old
    with session_factory() as session:
        events = list(session.scalars(select(AuditLogRow.event).order_by(AuditLogRow.id)))
    assert events == ["old.two", "recent"]
    assert audit.purge(clock.now() - timedelta(days=15)) == 0
