"""Metadata from public sources: candidates, matching and text sanitizing. Pure rules, no I/O.

Everything that comes from the network is untrusted text: titles and descriptions only reach
storage or a response after `sanitize_description` / `sanitize_title`, always as plain text.
"""

import difflib
import html
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.library import sanitize_title

MAX_DESCRIPTION_LENGTH = 4000
MAX_RAW_DESCRIPTION = 20_000  # cut before any regex runs on it
MAX_ALT_TITLES = 30
MAX_QUERY_LENGTH = 100
MATCH_THRESHOLD = 0.85  # conservative: below it the series is `not_found` (admin decides)
MATCH_MARGIN = 0.02  # the best candidate must beat the runner-up by this much
EXACT_TITLE = 1.0
EXACT_ALT_TITLE = 0.97
FUZZY_CAP = 0.95  # a fuzzy match never ties an exact one

STRONG_THRESHOLD = 0.9  # description-only sources (encyclopedia, book catalog): stricter
EDITION_PENALTY = 0.2  # "Book Version", "(Doujinshi)"... when the searched title lacks it
MAX_TRANSLATE_CHARS = 1500  # synopsis sent to the translation service (keeps the daily quota)
MAX_CHUNK_BYTES = 400  # per translation request (the service takes ~500 bytes)

PROVIDER_LABELS = {
    "mangadex": "MangaDex",
    "anilist": "AniList",
    "wikipedia": "Wikipédia",
    "googlebooks": "Google Livros",
}
# Sources that give a description only (no cover, no work identity): they never decide the title
# or the cover, and are only used with a STRONG match.
DESCRIPTION_ONLY = frozenset({"wikipedia", "googlebooks"})


@dataclass(frozen=True, slots=True)
class MetadataCandidate:
    """One possible match from a public source. `cover_url` is fetched only through the gateway
    allowlist; `source_url` is built by the provider from the external id, not from a response."""

    provider: str
    external_id: str
    title: str
    alt_titles: tuple[str, ...] = ()
    descriptions: Mapping[str, str] = field(default_factory=dict)  # language -> raw text
    cover_url: str | None = None
    source_url: str | None = None
    year: int | None = None


@dataclass(frozen=True, slots=True)
class ResolvedDescription:
    """The description chosen for a series and where it comes from (shown to the reader).

    `origin`: "source" (written by the source in that language), "translated" (automatic
    translation of `source_name`'s English text) or "manual". `source_url` is https or None.
    """

    text: str
    lang: str
    origin: str
    source_name: str | None
    source_url: str | None


@dataclass(frozen=True, slots=True)
class FetchedImage:
    """An image that passed size, content-type and magic-byte checks. `ext` comes from the magic
    bytes (never from a URL or header)."""

    data: bytes
    media_type: str
    ext: str  # "jpg" | "png" | "webp"


@dataclass(frozen=True, slots=True)
class StagedCover:
    """A cover written to a temporary file, waiting for `CoverStore.commit`."""

    series_id: str
    rel_path: str  # final name relative to the covers folder: "<series uuid>.<ext>"
    token: str  # opaque id of the temporary file


@dataclass(frozen=True, slots=True)
class MetadataUpdate:
    """New metadata of a series (every field is written; `title=None` keeps the current title)."""

    state: str
    description: str | None = None
    description_lang: str | None = None
    source: str | None = None
    external_id: str | None = None
    source_url: str | None = None
    title_original: str | None = None
    cover_path: str | None = None
    checked_at: datetime | None = None
    title: str | None = None
    description_origin: str | None = None
    description_source_name: str | None = None
    description_source_url: str | None = None


@dataclass(slots=True)
class EnrichReport:
    matched: int = 0
    not_found: int = 0
    skipped: int = 0
    errors: int = 0


# ---------------------------------------------------------------- image check

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_END = b"\x00\x00\x00\x00IEND"


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """(media type, extension) of a jpeg/png/webp judged by its bytes and shape, else None.

    Not just the first bytes: the file must also END like that format (a JPEG with its EOI marker,
    a PNG with its IEND chunk, a WebP whose RIFF size matches), which rejects the common polyglots
    (an image header glued to HTML or script). The name, URL and headers are never consulted.
    """
    if data[:3] == b"\xff\xd8\xff" and data.rstrip(b"\x00")[-2:] == b"\xff\xd9":
        return "image/jpeg", "jpg"
    if data[:8] == _PNG_SIGNATURE and data[12:16] == b"IHDR" and data[-12:-4] == _PNG_END:
        return "image/png", "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        size = int.from_bytes(data[4:8], "little")
        if size + 8 <= len(data) <= size + 9:
            return "image/webp", "webp"
    return None


# ---------------------------------------------------------------- text sanitizing

_SCRIPT_BLOCK = re.compile(r"<\s*(script|style)\b.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)
_BREAKS = re.compile(r"<\s*(?:br|/p|/div|/li)\b[^>]{0,100}>", re.IGNORECASE)
_TAG = re.compile(r"<[^<>]{0,2000}>")
_MD_TARGET = r"\((?:[^()\n]|\([^()\n]{0,200}\)){0,2000}\)"  # one level of nested parentheses
_MD_IMAGE = re.compile(rf"!\[([^\]\n]{{0,300}})\]{_MD_TARGET}")
_MD_LINK = re.compile(rf"\[([^\]\n]{{1,300}})\]{_MD_TARGET}")
_MD_MARKS = re.compile(r"\*\*|__|~~|~!|!~|`")
_MD_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_BLANK_RUN = re.compile(r"\n{3,}")
_SPACES = re.compile(r"[ \t ]+")


def sanitize_description(raw: str, limit: int = MAX_DESCRIPTION_LENGTH) -> str:
    """Plain text from an untrusted description: no HTML, no markdown links/images/bold, no
    control or bidi characters, tidy blank lines, at most `limit` characters. May be empty."""
    text = raw[:MAX_RAW_DESCRIPTION]
    text = _SCRIPT_BLOCK.sub(" ", text)
    text = _BREAKS.sub("\n", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = _SCRIPT_BLOCK.sub(" ", text)  # entities may have rebuilt a tag: remove again
    text = _TAG.sub("", text)
    text = text.replace("<", "").replace(">", "")  # never leave a half tag
    text = _MD_IMAGE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_MARKS.sub("", text)
    text = _MD_HEADING.sub("", text)
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        " " if ch == "\t" else ch
        for ch in text
        if ch in "\n\t" or not unicodedata.category(ch).startswith("C")
    )
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    text = _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip()
    if len(text) > limit:
        text = text[:limit].rstrip()
    return text


def clean_title(raw: str) -> str:
    """Display-safe title from the network (same rule as a folder name)."""
    return sanitize_title(raw)


def normalize_language(lang: str) -> str:
    return lang.strip().lower().replace("_", "-")


def pick_description(
    descriptions: Mapping[str, str], languages: Sequence[str]
) -> tuple[str, str] | None:
    """(sanitized text, real language) of the first preferred language that has text."""
    by_lang = {normalize_language(k): v for k, v in descriptions.items()}
    for lang in languages:
        key = normalize_language(lang)
        raw = by_lang.get(key)
        if raw is None:
            continue
        text = sanitize_description(raw)
        if text:
            return text, key
    return None


# ---------------------------------------------------------------- title matching

_TRAILING_MARKER = re.compile(
    r"\s(?:volume|vol|v|capitulo|chapter|chap|cap|ch|c)\.?\s*[0-9]{1,6}(?:\.[0-9]{1,3})?$"
)
_DROPPED = re.compile(r"['’`´]")


def normalize_title(title: str) -> str:
    """Casefolded, accent-free, punctuation-free title without a trailing volume/chapter marker."""
    text = unicodedata.normalize("NFKD", title[:300]).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _DROPPED.sub("", text)
    text = "".join(ch if ch.isalnum() else " " for ch in text)
    text = " ".join(text.split())
    stripped = _TRAILING_MARKER.sub("", text)
    return stripped or text


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / len(ta | tb)
    return min(FUZZY_CAP, (ratio + jaccard) / 2)


def title_similarity(a: str, b: str) -> float:
    """0..1 similarity of two titles after normalizing (1.0 = same title)."""
    na, nb = normalize_title(a), normalize_title(b)
    if na and na == nb:
        return 1.0
    return _similarity(na, nb)


_EDITION = re.compile(
    r"\b(?:doujinshi|doujin|book version|fan ?book|anthology|light novel|novel|art ?book)\b"
)
_COMIC_EVIDENCE = re.compile(
    r"mang[aá]|manhwa|manhua|webtoon|quadrinho|web ?novel|light novel|graphic novel|comics?\b",
    re.IGNORECASE,
)


def has_comic_evidence(text: str) -> bool:
    """True when the text says the work is a manga/manhwa/webtoon/comic (or its novel)."""
    return _COMIC_EVIDENCE.search(text[:2000]) is not None


def _score_one(wanted: str, candidate: MetadataCandidate) -> float:
    if not wanted:
        return 0.0
    main = normalize_title(candidate.title)
    alts = [normalize_title(t) for t in candidate.alt_titles[:MAX_ALT_TITLES]]
    if main == wanted:
        score = EXACT_TITLE
    elif wanted in alts:
        score = EXACT_ALT_TITLE
    else:
        score = max((_similarity(wanted, n) for n in [main, *alts]), default=0.0)
    # An edition ("Book Version", "(Doujinshi)", "Anthology"...) is not the work itself, unless
    # the title we are looking for says so too.
    marker = _EDITION.search(main)
    if marker is not None and marker.group(0) not in wanted:
        score -= EDITION_PENALTY
    return max(0.0, score)


def score_candidate(query: str | Sequence[str], candidate: MetadataCandidate) -> float:
    """0..1: 1.0 same title, 0.97 same alternative title, otherwise a capped fuzzy score, lowered
    for editions. `query` may be several names of the same work (the best one counts)."""
    names = [query] if isinstance(query, str) else list(query)
    return max((_score_one(normalize_title(n), candidate) for n in names), default=0.0)


def pick_best(
    query: str | Sequence[str],
    candidates: Sequence[MetadataCandidate],
    *,
    threshold: float = MATCH_THRESHOLD,
    tiebreak: bool = True,
    work_year: int | None = None,
) -> MetadataCandidate | None:
    """The candidate to trust, or None when nothing is close enough.

    Near ties (different works within MATCH_MARGIN): with `tiebreak` the oldest year wins, then the
    source's own relevance order; without it (strict, description-only sources) it is "unsure",
    so None. With `work_year`, a candidate more than a year OLDER than the work is incoherent and
    dropped (an edition cannot predate the work).
    """
    pool = [c for c in candidates if work_year is None or c.year is None or c.year >= work_year - 1]
    scored = sorted(((score_candidate(query, c), c) for c in pool), key=lambda pair: -pair[0])
    if not scored or scored[0][0] < threshold:
        return None
    best = scored[0][0]
    close = [c for score, c in scored if best - score < MATCH_MARGIN]
    if len({c.external_id for c in close}) == 1:
        return close[0]
    if not tiebreak:
        return None
    return sorted(close, key=lambda c: (c.year is None, c.year or 0))[0]


# ---------------------------------------------------------------- translation helpers

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def truncate_for_translation(text: str, limit: int = MAX_TRANSLATE_CHARS) -> str:
    """At most `limit` characters, cut at a sentence end when there is one."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    ends = [m.start() for m in _SENTENCE_END.finditer(cut)]
    return cut[: ends[-1]].rstrip() if ends else cut.rstrip()


def _hard_split(sentence: str, max_bytes: int) -> list[str]:
    if len(sentence.encode()) <= max_bytes:
        return [sentence]
    pieces: list[str] = []
    current = ""
    for word in sentence.split(" "):
        candidate = f"{current} {word}" if current else word
        if len(candidate.encode()) > max_bytes:
            if current:
                pieces.append(current)
            current = word.encode()[:max_bytes].decode(errors="ignore")  # absurd word: cut
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_for_translation(text: str, max_bytes: int = MAX_CHUNK_BYTES) -> list[str]:
    """Pieces of at most `max_bytes` UTF-8 bytes, split by paragraph, then sentence, then word."""
    chunks: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for sentence in _SENTENCE_END.split(paragraph):
            for piece in _hard_split(sentence.strip(), max_bytes):
                joined = f"{current} {piece}" if current else piece
                if len(joined.encode()) > max_bytes:
                    if current.strip():
                        chunks.append(current.strip())
                    current = piece
                else:
                    current = joined
        if current.strip():
            chunks.append(current.strip())
    return chunks


def valid_translation(original: str, translated: str) -> bool:
    """A translation is accepted only if it is non-empty, different from the original and of a
    coherent size (not a warning message, not an echo, not a runaway text)."""
    o, t = original.strip(), translated.strip()
    if not t or t.casefold() == o.casefold():
        return False
    return 0.4 <= len(t) / max(1, len(o)) <= 3.0


# ---------------------------------------------------------------- translation post-processing

_UPPER = "A-ZÀ-ÖØ-Þ"
_MISSING_SPACE = re.compile(rf"([a-zà-öø-ÿ\"”»])([.!?])([\"”»'’)]*)(?=[{_UPPER}])")


def fix_missing_sentence_space(text: str) -> str:
    """Insert ONE space after a sentence end (`.`, `!`, `?`, plus closing quotes/parenthesis) that
    is glued to a capital letter, a flaw of the translation service (`Apocalipse".Mas`).

    Applied only when the character before the mark is a lowercase letter or a closing quote and
    the next one is an uppercase letter (accented ones included). So these stay as they are:
    decimals (3.5), acronyms (U.S.A.), ellipses (`...Mas`), domains and file names (site.com,
    `a.Mas` inside a URL or e-mail token). Decision: an abbreviation glued to a capital
    (`Sr.Silva`, `etc.Mas`) DOES get its space: for text coming glued from the service that is
    the more likely reading, and the cost of a wrong space is tiny.
    """

    def fix(match: re.Match[str]) -> str:
        source = match.string
        start = max(source.rfind(" ", 0, match.start()), source.rfind("\n", 0, match.start())) + 1
        ends = [
            i for i in (source.find(" ", match.end()), source.find("\n", match.end())) if i >= 0
        ]
        token = source[start : min(ends) if ends else len(source)]
        if "@" in token or "://" in token or token.lower().startswith("www."):
            return match.group(0)
        return f"{match.group(1)}{match.group(2)}{match.group(3)} "

    return _MISSING_SPACE.sub(fix, text)
