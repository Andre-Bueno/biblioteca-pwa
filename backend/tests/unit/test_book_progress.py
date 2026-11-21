"""Book locator: `chapter_index * 10000 + offset_bp`, percent and finished (pure domain)."""

import pytest
from app.domain.item import ItemType
from app.domain.progress import (
    InvalidLocator,
    compute_book_position,
    compute_position,
    encode_book_locator,
    split_book_locator,
)


def test_encode_and_split_roundtrip() -> None:
    for chapter, offset in ((0, 0), (0, 9999), (7, 1234), (99_999, 9999)):
        locator = encode_book_locator(chapter, offset)
        assert locator == chapter * 10_000 + offset
        assert split_book_locator(locator) == (chapter, offset)
    assert encode_book_locator(99_999, 9999) < 2**31  # fits an INT32


@pytest.mark.parametrize("chapter, offset", [(0, -1), (0, 10_000), (-1, 0), (3, 12_345)])
def test_encode_rejects_out_of_range_parts(chapter: int, offset: int) -> None:
    with pytest.raises(InvalidLocator):
        encode_book_locator(chapter, offset)


def test_percent_is_chapter_plus_offset_over_chapters() -> None:
    assert compute_book_position(0, 4) == (0.0, False)
    assert compute_book_position(10_000, 4) == (25.0, False)
    percent, finished = compute_book_position(1 * 10_000 + 5_000, 4)
    assert (percent, finished) == (37.5, False)
    assert compute_book_position(0, 1)[0] == 0.0


def test_finished_only_on_the_last_chapter_from_offset_9000() -> None:
    assert compute_book_position(3 * 10_000 + 8_999, 4)[1] is False
    percent, finished = compute_book_position(3 * 10_000 + 9_000, 4)
    assert finished is True and percent == pytest.approx(97.5)
    assert compute_book_position(3 * 10_000 + 9_999, 4)[0] < 100.0
    assert compute_book_position(2 * 10_000 + 9_999, 4)[1] is False  # not the last chapter
    assert compute_book_position(9_000, 1)[1] is True  # a one-chapter book


@pytest.mark.parametrize(
    "locator, chapters",
    [(-1, 4), (4 * 10_000, 4), (4 * 10_000 + 5, 4), (10**9, 4), (0, 0), (0, 100_001)],
)
def test_locator_outside_the_book_is_invalid(locator: int, chapters: int) -> None:
    with pytest.raises(InvalidLocator):
        compute_book_position(locator, chapters)


def test_the_largest_book_still_validates() -> None:
    assert compute_book_position(99_999 * 10_000 + 9_000, 100_000)[1] is True


def test_manga_and_pdf_are_unchanged() -> None:
    for kind in (ItemType.MANGA, ItemType.PDF):
        assert compute_position(0, 4, kind) == (25.0, False)
        assert compute_position(3, 4, kind) == (100.0, True)
        with pytest.raises(InvalidLocator):
            compute_position(4, 4, kind)
        with pytest.raises(InvalidLocator):
            compute_position(10_000, 4, kind)  # a book-style locator means nothing on a manga
    assert compute_position(3, 4) == (100.0, True)  # the old two-argument call
    assert compute_position(10_000, 4, ItemType.BOOK) == (25.0, False)
