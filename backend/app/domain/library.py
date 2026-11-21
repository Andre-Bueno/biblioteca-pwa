"""Library value objects and pure helpers."""

import re
import unicodedata
from dataclasses import dataclass, field

MAX_TITLE_LENGTH = 200


@dataclass(frozen=True, slots=True)
class ExtractorLimits:
    """Safety limits for archive/folder readers. Injected; never read from app.core."""

    max_entries: int = 10_000
    max_total_uncompressed_bytes: int = 4 * 1024**3
    max_page_bytes: int = 64 * 1024**2
    max_compression_ratio: int = 100


@dataclass(frozen=True, slots=True)
class ItemMetadata:
    """Result of inspecting a file: what the extractor learned about it."""

    page_count: int
    # Display title found inside the file (EPUB: OPF `dc:title`), already sanitized; None = use
    # the file name. `authors` is informational (not stored).
    title: str | None = None
    authors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Page:
    """A page (or cover) payload."""

    data: bytes
    media_type: str


@dataclass(frozen=True, slots=True)
class ScanError:
    """A per-file scan failure. `reason` is an error class name, never a path or message."""

    rel_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class ScanProgress:
    processed: int
    total: int


@dataclass(slots=True)
class ScanReport:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    skipped: int = 0
    regrouped: int = 0  # unchanged files whose series or chapter number was fixed
    # Why nothing was marked missing even though the scan finished (fixed codes, never paths):
    # "walk_errors", "empty_library" or "data_access_errors". None = removal ran normally.
    removal_skipped: str | None = None
    errors: list[ScanError] = field(default_factory=list)


_SPACES = re.compile(r"\s+")
_DIGITS = re.compile(r"([0-9]{1,18})")  # bounded: int() on huge digit runs raises ValueError


def sanitize_title(raw: str) -> str:
    """Turn an untrusted file/folder name into a safe display title."""
    text = unicodedata.normalize("NFC", raw)
    # Unicode category C* = control, format (bidi/zero-width), surrogate, private, unassigned.
    text = "".join(" " if unicodedata.category(ch).startswith("C") else ch for ch in text)
    text = text.replace("<", " ").replace(">", " ")
    text = _SPACES.sub(" ", text).strip()
    if len(text) > MAX_TITLE_LENGTH:
        text = text[:MAX_TITLE_LENGTH].rstrip()
    return text or "Untitled"


def natural_key(name: str) -> tuple[tuple[int, int, str], ...]:
    """Sort key for natural ordering ("p2" < "p10"), case-insensitive."""
    parts = _DIGITS.split(name.casefold())
    key: list[tuple[int, int, str]] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            key.append((0, int(part), ""))
        elif part:
            key.append((1, 0, part))
    return tuple(key)
