"""test_reg_024: a book's progress locator is `chapter * 10000 + offset`, validated by item type.

Bug (found while adding EPUB reading): `compute_position` treated every locator as a page index, so
a book locator such as 15000 was rejected (>= chapter count) and a page-style locator on a book
would have been accepted as "chapter 0, offset N". Cause: progress rules knew only page-based
items. Manga and PDF must keep the old meaning.
"""

import pytest
from app.domain.item import ItemType
from app.domain.progress import InvalidLocator, compute_position


def test_reg_024_book_locator_means_chapter_and_offset() -> None:
    assert compute_position(15_000, 4, ItemType.BOOK) == (37.5, False)
    assert compute_position(39_000, 4, ItemType.BOOK)[1] is True  # last chapter, >= 90%


def test_reg_024_a_book_locator_past_the_last_chapter_is_refused() -> None:
    with pytest.raises(InvalidLocator):
        compute_position(40_000, 4, ItemType.BOOK)


def test_reg_024_page_items_keep_the_page_meaning() -> None:
    assert compute_position(3, 4, ItemType.MANGA) == (100.0, True)
    assert compute_position(3, 4, ItemType.PDF) == (100.0, True)
    with pytest.raises(InvalidLocator):
        compute_position(10_000, 4, ItemType.MANGA)
