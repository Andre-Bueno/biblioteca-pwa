"""Series: grouping of chapters (items) by their parent folder. Pure rules, no I/O.

Names come from the file system and are untrusted text: everything here only reads them, and every
title that can be shown goes through `sanitize_title`.

Known limitation: a folder series is identified by its library-relative folder path. Renaming the
folder creates a new series (the old one loses its chapters and disappears from the listing).
"""

import posixpath
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.item import Item
from app.domain.library import natural_key, sanitize_title
from app.domain.progress import Progress

MAX_NAME_LENGTH = 255  # names longer than this are cut before any regex runs on them
MAX_DESCRIPTION_PREVIEW = 300
SORT_TITLE_MAX = 255
_PAD = 12


class MetadataState(StrEnum):
    NONE = "none"
    MATCHED = "matched"
    MANUAL = "manual"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class Series:
    """A group of chapters. `id` is an opaque UUID; `folder_rel_path` never leaves the server.

    `folder_rel_path` is None for a standalone series (a loose file in the library root, whose
    link to the series lives only in `Item.series_id`). `cover_path` is relative to the data dir.
    """

    id: str
    title: str
    sort_title: str
    folder_rel_path: str | None
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    description_lang: str | None = None
    metadata_source: str | None = None
    external_id: str | None = None
    metadata_state: str = MetadataState.NONE.value
    cover_path: str | None = None
    source_url: str | None = None  # https page of the match at the source (built server-side)
    title_original: str | None = None  # title of the match at the source
    metadata_checked_at: datetime | None = None
    # Where the description comes from: "source" | "translated" | "manual" (None = unknown/none).
    description_origin: str | None = None
    description_source_name: str | None = None
    description_source_url: str | None = None


@dataclass(frozen=True, slots=True)
class SeriesSummary:
    """A series with its active chapter count and one user's reading counters."""

    series: Series
    chapter_count: int
    has_cover: bool
    read_chapters: int
    last_item_id: str | None
    kind: str = "manga"  # see `series_kind`


@dataclass(frozen=True, slots=True)
class Grouping:
    """Where one library entry belongs: its series and its chapter number."""

    folder_rel_path: str | None  # None = standalone series (entry directly in the root)
    series_title: str
    chapter_number: float | None


@dataclass(frozen=True, slots=True)
class ContinuePoint:
    item_id: str
    locator: int


# ASCII only (`re.A`): `[0-9]` and `[a-z]`, never Unicode digits or letters.
_NUM = r"([0-9]{1,6}(?:\.[0-9]{1,3})?)(?![0-9])"
_FLAGS = re.IGNORECASE | re.ASCII
_CHAPTER_WORDS = r"(?:cap[ií]tulo|chapter|chap|cap|ch|c)"
_VOLUME_WORDS = r"(?:volume|vol|v)"
_CHAPTER = re.compile(rf"(?<![a-z0-9]){_CHAPTER_WORDS}\.?\s*[-_#:]?\s*{_NUM}", _FLAGS)
_VOLUME = re.compile(rf"(?<![a-z0-9]){_VOLUME_WORDS}\.?\s*[-_#:]?\s*{_NUM}", _FLAGS)
_BARE = re.compile(rf"\s*{_NUM}\s*", _FLAGS)
_SUFFIX = re.compile(
    rf"[\s\-_.,:]*(?<![a-z0-9])(?:{_VOLUME_WORDS}|{_CHAPTER_WORDS})"
    r"\.?\s*[-_#:]?\s*[0-9]{1,6}(?:\.[0-9]{1,3})?\s*$",
    _FLAGS,
)
_SEPARATORS = " -_.,:"


def _entry_name(rel_path: str, is_dir: bool) -> str:
    name = posixpath.basename(rel_path.rstrip("/"))
    if not is_dir:
        name = posixpath.splitext(name)[0]
    return name[:MAX_NAME_LENGTH]


def parse_chapter_number(name: str) -> float | None:
    """Chapter/volume number found in a file or folder name (no extension), else None.

    Recognizes `Capitulo - 100`, `Cap 12`, `Chapter 7.5`, `c012`, `Vol 03`, `Berserk v03` and a
    name that is only a number. A chapter marker wins over a volume marker.
    """
    text = name[:MAX_NAME_LENGTH]
    for pattern in (_CHAPTER, _VOLUME):
        match = pattern.search(text)
        if match is not None:
            return float(match.group(1))
    bare = _BARE.fullmatch(text)
    return None if bare is None else float(bare.group(1))


def _standalone_title(stem: str) -> str:
    """Title of a loose file: the name without a trailing volume/chapter marker, when safe."""
    stem = stem[:MAX_NAME_LENGTH]
    match = _SUFFIX.search(stem)
    if match is not None:
        base = stem[: match.start()].strip(_SEPARATORS)
        if base:
            return sanitize_title(base)
    return sanitize_title(stem)


def group_entry(rel_path: str, is_dir: bool) -> Grouping:
    """Series and chapter number of a library entry from its library-relative POSIX path.

    The series is the immediate parent folder; an entry directly in the root is a standalone
    series of one chapter. A folder that is itself an item (image folder) is a chapter of its
    parent folder's series.
    """
    clean = rel_path.rstrip("/")
    parent = posixpath.dirname(clean)
    name = _entry_name(clean, is_dir)
    number = parse_chapter_number(name)
    if parent:
        return Grouping(parent, sanitize_title(posixpath.basename(parent)), number)
    return Grouping(None, _standalone_title(name), number)


def series_kind(types: Iterable[str]) -> str:
    """ "manga" or "book" when every active item has that type, else "mixed" (also for PDF and
    for no items)."""
    distinct = set(types)
    if distinct == {"manga"}:
        return "manga"
    if distinct == {"book"}:
        return "book"
    return "mixed"


def sort_title(title: str) -> str:
    """Case-insensitive key with digit runs zero-padded, so SQL `ORDER BY` is a natural sort."""
    parts = re.split(rf"([0-9]{{1,{_PAD}}})", title.casefold())
    key = "".join(p.zfill(_PAD) if i % 2 == 1 else p for i, p in enumerate(parts))
    return key[:SORT_TITLE_MAX]


def _format_number(number: float) -> str:
    return f"{number:.3f}".rstrip("0").rstrip(".")


def chapter_title(number: float | None, fallback: str) -> str:
    """Displayed chapter title: `Capitulo 100` from the number when there is one."""
    return fallback if number is None else f"Capitulo {_format_number(number)}"


def chapter_sort_key(chapter: Item) -> tuple[int, float, tuple[tuple[int, int, str], ...], str]:
    """Number first (no number last), then natural order of the name, then id (stable)."""
    number = chapter.chapter_number
    return (
        1 if number is None else 0,
        0.0 if number is None else number,
        natural_key(chapter.title),
        chapter.id,
    )


def sort_chapters(chapters: Sequence[Item]) -> list[Item]:
    return sorted(chapters, key=chapter_sort_key)


def short_description(text: str | None) -> str | None:
    """List preview of a description: at most MAX_DESCRIPTION_PREVIEW characters."""
    if text is None:
        return None
    if len(text) <= MAX_DESCRIPTION_PREVIEW:
        return text
    return text[: MAX_DESCRIPTION_PREVIEW - 1].rstrip() + "…"


def pick_continue(
    chapters: Sequence[Item], progress: Mapping[str, Progress]
) -> ContinuePoint | None:
    """Where the user should resume in a series (`chapters` already in reading order).

    The most recently touched unfinished chapter; if everything started is finished, the first
    chapter without progress after the last finished one; None if never read (or nothing left).
    """
    started = [p for c in chapters if (p := progress.get(c.id)) is not None]
    if not started:
        return None
    ongoing = [p for p in started if not p.finished]
    if ongoing:
        latest = max(ongoing, key=lambda p: p.updated_at)
        return ContinuePoint(latest.item_id, latest.locator)
    last_done = max(i for i, c in enumerate(chapters) if c.id in progress)
    for chapter in chapters[last_done + 1 :]:
        if chapter.id not in progress:
            return ContinuePoint(chapter.id, 0)
    return None
