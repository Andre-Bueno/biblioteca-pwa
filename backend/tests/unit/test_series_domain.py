"""Pure rules of series grouping: name parsing, ordering, titles, where to continue."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from app.domain.item import Item, ItemType
from app.domain.progress import Progress
from app.domain.series import (
    MAX_DESCRIPTION_PREVIEW,
    chapter_title,
    group_entry,
    parse_chapter_number,
    pick_continue,
    short_description,
    sort_chapters,
    sort_title,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Capitulo - 100", 100.0),
        ("Capitulo - 0", 0.0),
        ("Capitulo - 7", 7.0),
        ("Capítulo 12", 12.0),
        ("Cap 12", 12.0),
        ("Cap. 3", 3.0),
        ("Chapter 7.5", 7.5),
        ("chapter_8", 8.0),
        ("c012", 12.0),
        ("Vol 03", 3.0),
        ("Volume 10", 10.0),
        ("Berserk v03", 3.0),
        ("Berserk - Vol 01", 1.0),
        ("Vol 2 Ch 9", 9.0),  # a chapter marker wins over a volume marker
        ("012", 12.0),
        ("7.5", 7.5),
        ("Omniscient Reader's Viewpoint Cap 4", 4.0),  # apostrophe in the name
        ("Capítulo 1 – 愛", 1.0),  # unicode after the number
        ("Berserk", None),
        ("Extras", None),
        ("", None),
        ("Abc 12", None),  # 'c' inside a word is not a marker
        ("Doc5", None),
        ("Capitulo", None),
        ("Capitulo - ", None),
        ("..", None),
        ("Cap ٣", None),  # non-ASCII digits are not numbers
        ("Cap 1234567", None),  # too many digits: refused, not parsed
        ("‮c‭ 5", None),  # bidi override right before the marker
    ],
)
def test_parse_chapter_number(name: str, expected: float | None) -> None:
    assert parse_chapter_number(name) == expected


def test_parse_is_safe_on_hostile_and_huge_names() -> None:
    assert parse_chapter_number("Cap 1\x00 2") == 1.0
    assert parse_chapter_number("a" * 100_000) is None
    assert parse_chapter_number(" " * 100_000 + "Cap 5") is None  # cut before any regex runs
    assert parse_chapter_number("9" * 100_000) is None


def test_group_entry_folder_series_and_number() -> None:
    g = group_entry("Omniscient Reader's Viewpoint/Capitulo - 100.cbz", False)
    assert (g.folder_rel_path, g.series_title, g.chapter_number) == (
        "Omniscient Reader's Viewpoint",
        "Omniscient Reader's Viewpoint",
        100.0,
    )


def test_group_entry_series_is_the_immediate_parent_only() -> None:
    g = group_entry("Publisher/Berserk/Vol 03.cbz", False)
    assert (g.folder_rel_path, g.series_title, g.chapter_number) == (
        "Publisher/Berserk",
        "Berserk",
        3.0,
    )


@pytest.mark.parametrize(
    ("rel", "title", "number"),
    [
        ("Berserk v03.cbz", "Berserk", 3.0),
        ("Berserk - Vol 01.cbz", "Berserk", 1.0),
        ("One Piece Cap 12.cbz", "One Piece", 12.0),
        ("Dr. Stone c012.cbz", "Dr. Stone", 12.0),
        ("Vol 1.cbz", "Vol 1", 1.0),  # nothing left after stripping: keep the clean name
        ("Capitulo 5.cbz", "Capitulo 5", 5.0),
        ("Berserkv03.cbz", "Berserkv03", None),  # glued marker: not safe to strip
        ("Death Note.cbz", "Death Note", None),
        ("Re Zero 3.cbz", "Re Zero 3", None),  # a bare trailing number is part of the title
    ],
)
def test_group_entry_root_file_is_a_standalone_series(
    rel: str, title: str, number: float | None
) -> None:
    g = group_entry(rel, False)
    assert g.folder_rel_path is None
    assert (g.series_title, g.chapter_number) == (title, number)


def test_group_entry_root_folder_item_is_standalone_and_inner_folder_is_a_chapter() -> None:
    root = group_entry("Folder Manga", True)
    assert (root.folder_rel_path, root.series_title) == (None, "Folder Manga")
    inner = group_entry("Series X/Chapter 7.5", True)
    assert (inner.folder_rel_path, inner.series_title, inner.chapter_number) == (
        "Series X",
        "Series X",
        7.5,
    )


@pytest.mark.parametrize(
    "rel",
    [
        "../evil/Cap 1.cbz",
        "a/../../b.cbz",
        "name\x00evil/Cap 1.cbz",
        "‮gnp.cbz",
        "<script>/Cap 1.cbz",
        "x​⁦y/Cap 1.cbz",
    ],
)
def test_group_entry_hostile_names_never_yield_unsafe_titles(rel: str) -> None:
    g = group_entry(rel, False)
    assert g.series_title
    assert "\x00" not in g.series_title
    assert "<" not in g.series_title and ">" not in g.series_title
    assert not any(ch in g.series_title for ch in "‮‭⁦​")
    assert len(g.series_title) <= 200


def test_chapter_title_from_number_or_fallback() -> None:
    assert chapter_title(100.0, "Capitulo - 100") == "Capitulo 100"
    assert chapter_title(0.0, "x") == "Capitulo 0"
    assert chapter_title(7.5, "x") == "Capitulo 7.5"
    assert chapter_title(None, "Extras") == "Extras"


def _item(ident: str, title: str, number: float | None) -> Item:
    return Item(
        id=ident,
        type=ItemType.MANGA,
        title=title,
        rel_path=f"S/{title}.cbz",
        format="cbz",
        page_count=3,
        size=1,
        mtime_ns=1,
        added_at=T0,
        chapter_number=number,
    )


def test_chapters_sort_by_number_then_natural_name_and_no_number_last() -> None:
    chapters = [
        _item("a", "Capitulo - 100", 100.0),
        _item("b", "Capitulo - 10", 10.0),
        _item("c", "Capitulo - 2", 2.0),
        _item("d", "Capitulo - 0", 0.0),
        _item("e", "Extra 10", None),
        _item("f", "Extra 2", None),
        _item("g", "Capitulo - 7.5", 7.5),
    ]
    assert [c.chapter_number for c in sort_chapters(chapters)] == [
        0.0,
        2.0,
        7.5,
        10.0,
        100.0,
        None,
        None,
    ]
    assert [c.title for c in sort_chapters(chapters)][-2:] == ["Extra 2", "Extra 10"]


def test_equal_numbers_order_by_natural_name_then_id() -> None:
    chapters = [
        _item("z", "Cap 1 b10", 1.0),
        _item("y", "Cap 1 b2", 1.0),
        _item("x", "Cap 1 b2", 1.0),
    ]
    assert [c.id for c in sort_chapters(chapters)] == ["x", "y", "z"]


def test_sort_title_is_natural_and_case_insensitive() -> None:
    titles = ["Series 10", "series 2", "Series 100", "Alpha", "beta"]
    assert sorted(titles, key=sort_title) == [
        "Alpha",
        "beta",
        "series 2",
        "Series 10",
        "Series 100",
    ]
    assert len(sort_title("9" * 5000)) <= 255


def test_short_description_is_bounded() -> None:
    assert short_description(None) is None
    assert short_description("curta") == "curta"
    long = short_description("x" * 1000)
    assert long is not None and len(long) <= MAX_DESCRIPTION_PREVIEW


def _progress(item: Item, locator: int, finished: bool, minutes: int) -> Progress:
    return Progress(
        user_id="u",
        item_id=item.id,
        locator=locator,
        percent=50.0,
        finished=finished,
        updated_at=T0 + timedelta(minutes=minutes),
    )


def test_continue_is_none_when_never_read() -> None:
    chapters = sort_chapters([_item("a", "Cap 1", 1.0), _item("b", "Cap 2", 2.0)])
    assert pick_continue(chapters, {}) is None


def test_continue_is_the_most_recent_unfinished_chapter() -> None:
    a, b, c = (_item(x, f"Cap {n}", float(n)) for n, x in enumerate("abc", start=1))
    progress = {
        a.id: _progress(a, 2, True, 1),
        b.id: _progress(b, 1, False, 5),
        c.id: _progress(c, 0, False, 9),
    }
    point = pick_continue([a, b, c], progress)
    assert point is not None and (point.item_id, point.locator) == ("c", 0)


def test_continue_is_the_next_unread_chapter_when_all_started_are_finished() -> None:
    a, b, c, d = (_item(x, f"Cap {n}", float(n)) for n, x in enumerate("abcd", start=1))
    progress = {a.id: _progress(a, 2, True, 1), b.id: _progress(b, 2, True, 2)}
    point = pick_continue([a, b, c, d], progress)
    assert point is not None and (point.item_id, point.locator) == ("c", 0)
    everything = {c_.id: _progress(c_, 2, True, 1) for c_ in (a, b, c, d)}
    assert pick_continue([a, b, c, d], everything) is None  # nothing left to read


def test_continue_skips_chapters_already_started_after_the_last_finished() -> None:
    a, b = _item("a", "Cap 1", 1.0), _item("b", "Cap 2", 2.0)
    only_first = {a.id: replace(_progress(a, 2, True, 1))}
    point = pick_continue([a, b], only_first)
    assert point is not None and point.item_id == "b"
