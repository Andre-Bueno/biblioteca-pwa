"""Hostile-input primitives for the EPUB reader: text decoding, XML parsing without entities,
href resolution inside the zip root and safe identifiers. Standard library only."""

import codecs
import posixpath
import re
import unicodedata

# DTD and entities are refused before the parser ever sees the text (see `parse_xml`).
import xml.etree.ElementTree as ET  # noqa: S405  # nosec B405
from urllib.parse import unquote

from app.domain.errors import CorruptArchive

MAX_HREF_LENGTH = 2048
MAX_IDENT_LENGTH = 128

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_DOUBLE_ENCODED = re.compile(r"%[0-9A-Fa-f]{2}")
_IDENT = re.compile(r"[A-Za-z0-9_:.\-]{1,128}")
_XML_DECL = re.compile(rb"^\s*<\?xml[^>]{0,200}?encoding\s*=\s*[\"']([A-Za-z0-9._\-]{1,40})[\"']")
_META_CHARSET = re.compile(rb"<meta[^>]{0,300}?charset\s*=\s*[\"']?([A-Za-z0-9._\-]{1,40})", re.I)
_ENTITY_DECL = re.compile(r"<!\s*ENTITY", re.I)
# A `[` before the next `<` after DOCTYPE opens an internal subset (where entities live).
_DOCTYPE_SUBSET = re.compile(r"<!\s*DOCTYPE[^<]*\[", re.I | re.S)
_DOCTYPE = re.compile(r"<!\s*DOCTYPE(?:[^>\"']|\"[^\"]*\"|'[^']*')*>?", re.I)

# Text codecs we are willing to use for a declared encoding (canonical `codecs` names). Anything
# else (rot13, base64, unicode_escape, idna, ...) is ignored and UTF-8 is used.
_ALLOWED_ENCODINGS = frozenset(
    {
        "utf-8",
        "ascii",
        "iso8859-1",
        "iso8859-2",
        "iso8859-15",
        "cp1250",
        "cp1251",
        "cp1252",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "shift_jis",
        "euc_jp",
        "gbk",
        "gb2312",
        "big5",
        "euc_kr",
    }
)


def _declared_encoding(head: bytes) -> str | None:
    match = _XML_DECL.match(head[:300]) or _META_CHARSET.search(head[:1024])
    if match is None:
        return None
    try:
        name = codecs.lookup(match.group(1).decode("ascii")).name
    except (LookupError, UnicodeError):
        return None
    return name if name in _ALLOWED_ENCODINGS else None


def decode_text(data: bytes) -> str:
    """Bytes of an XML/HTML file to text: BOM first (UTF-8/16), then an XML or `<meta>` charset
    declaration from a short allowlist, else UTF-8. Never raises on bad bytes (they are replaced).
    NUL characters are removed."""
    if data.startswith(codecs.BOM_UTF8):
        text = data[len(codecs.BOM_UTF8) :].decode("utf-8", "replace")
    elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        text = data.decode("utf-16", "replace")
    elif data[:2] == b"<\x00":
        text = data.decode("utf-16-le", "replace")
    elif data[:2] == b"\x00<":
        text = data.decode("utf-16-be", "replace")
    else:
        encoding = _declared_encoding(data[:1100]) or "utf-8"
        if encoding.startswith("utf-16"):  # declared but not really UTF-16: do not trust it
            encoding = "utf-8"
        text = data.decode(encoding, "replace")
    return text.replace("\x00", "")


def parse_xml(data: bytes) -> ET.Element:
    """Parse untrusted XML. No entity can ever expand: any `<!ENTITY` and any DOCTYPE with an
    internal subset (`[`) is refused before the parser sees the text, and the DOCTYPE itself is
    removed. Failure is a generic `CorruptArchive`."""
    text = decode_text(data)
    if _ENTITY_DECL.search(text) or _DOCTYPE_SUBSET.search(text):
        raise CorruptArchive
    # The encoding declaration refers to the original bytes, not to this str.
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1)
    text = _DOCTYPE.sub("", text)
    try:
        # No DTD content reaches the parser (see above), so nothing can expand or be fetched.
        return ET.fromstring(text)  # noqa: S314  # nosec B314
    except (ET.ParseError, ValueError, RecursionError, MemoryError) as exc:
        raise CorruptArchive from exc


def local_name(tag: object) -> str:
    """Tag or attribute name without its namespace (`{ns}name` -> `name`)."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def attr(element: ET.Element, name: str) -> str | None:
    """Attribute by local name (namespace-insensitive)."""
    for key, value in element.attrib.items():
        if local_name(key) == name:
            return value
    return None


def text_of(element: ET.Element) -> str:
    return "".join(element.itertext())


def resolve_href(base_dir: str, href: str) -> tuple[str, str | None] | None:
    """Resolve `href` (relative to the directory `base_dir` of the referring file, both zip-style)
    to `(zip member name, fragment)`, or None when it is not a plain relative reference to a file
    inside the archive.

    Refused: empty, too long, control characters, NUL, backslash, absolute (`/x`, `//host`), any
    scheme (`http:`, `javascript:`, `data:`, `mailto:`...), a query, percent-encoding that is still
    encoded after one decoding (double encoding) and any `..` that climbs out of the root.
    """
    if not href or len(href) > MAX_HREF_LENGTH:
        return None
    # Browsers ignore tab/newline inside a URL and trim spaces around it: do the same BEFORE looking
    # for a scheme so `java\nscript:` cannot slip through.
    cleaned = href.strip().replace("\t", "").replace("\n", "").replace("\r", "")
    if not cleaned or _CONTROL.search(cleaned) or "\\" in cleaned:
        return None
    if cleaned.startswith(("/", "?")) or _SCHEME.match(cleaned):
        return None
    target, _, fragment = cleaned.partition("#")
    if "?" in target:
        return None
    try:
        decoded = unquote(target, errors="strict")
    except UnicodeDecodeError:
        return None
    if (
        _DOUBLE_ENCODED.search(decoded)
        or _CONTROL.search(decoded)
        or "\\" in decoded
        or decoded.startswith("/")
        or _SCHEME.match(decoded)
    ):
        return None
    if not decoded:
        return None
    joined = posixpath.normpath(posixpath.join(base_dir, decoded))
    if joined in (".", "") or joined == ".." or joined.startswith(("../", "/")):
        return None
    return joined, safe_fragment(fragment)


def safe_fragment(fragment: str) -> str | None:
    """A fragment/id only if it is plain ASCII `[A-Za-z0-9_:.-]` (max 128), else None."""
    if fragment and _IDENT.fullmatch(fragment):
        return fragment
    return None


def safe_ident(value: str) -> str | None:
    return safe_fragment(value)


def clean_text(value: str, limit: int = 4096) -> str:
    """Text for an attribute or a title: normalized, control/format characters removed."""
    text = unicodedata.normalize("NFC", value[:limit])
    return "".join(" " if unicodedata.category(ch).startswith("C") else ch for ch in text).strip()
