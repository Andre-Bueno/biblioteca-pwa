"""EPUB: scan extractor (`Extractor`) and book reader (`BookReader`) in one adapter.

An EPUB is a zip of untrusted XML, HTML, CSS and images. Everything is read in memory and nothing
is extracted to disk. Chapters leave this module only as sanitized HTML (`_epub_html`), images only
after a magic-byte check, fonts and SVG are never served, and every reference inside the book is
resolved by `_epub_safe.resolve_href` (zip-root confined, no schemes, no double encoding).

Limits besides the shared zip ones (entries, total size, compression ratio, member size): XML 2 MiB,
chapter 2 MiB, stylesheet 512 KiB, image 10 MiB, spine 100 000 items, manifest 20 000 items,
HTML depth 100, attribute 4 096 characters.
"""

import posixpath

# Types only: every parse goes through `_epub_safe.parse_xml` (no DTD, no entities).
import xml.etree.ElementTree as ET  # noqa: S405  # nosec B405
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from html.parser import HTMLParser

from app.adapters.extractors._common import (
    HEADER_BYTES,
    PageIndexCache,
    default_read_gate,
    open_zip,
    sniff_image,
    validate_zip,
)
from app.adapters.extractors._epub_html import SanitizeContext, build_document, sanitize_chapter
from app.adapters.extractors._epub_safe import (
    attr,
    clean_text,
    decode_text,
    local_name,
    parse_xml,
    resolve_href,
    text_of,
)
from app.adapters.gate import BoundedGate
from app.domain.book import MAX_CHAPTERS, BookInfo, ChapterRef, TocEntry, validate_book_options
from app.domain.errors import (
    ArchiveLimitExceeded,
    CorruptArchive,
    DomainError,
    PageOutOfRange,
    UnsafePath,
    UnsupportedFormat,
)
from app.domain.item import ItemType
from app.domain.library import ExtractorLimits, ItemMetadata, Page, sanitize_title
from app.ports.storage import StorageBackend, StorageEntry

MAX_XML_BYTES = 2 * 1024 * 1024
MAX_CHAPTER_BYTES = 2 * 1024 * 1024
MAX_CSS_FILE_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_SPINE_ITEMS = MAX_CHAPTERS
MAX_MANIFEST_ITEMS = 20_000
MAX_TOC_ENTRIES = 10_000
MAX_AUTHORS = 20
BOOK_INDEX_CACHE_SIZE = 16

MIMETYPE = b"application/epub+zip"
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06")
HTML_TYPES = frozenset({"application/xhtml+xml", "text/html"})
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp", "image/avif"})
NCX_TYPE = "application/x-dtbncx+xml"
# The only encryption an EPUB may carry for us: font obfuscation (fonts are never served anyway).
FONT_OBFUSCATION = frozenset(
    {"http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC"}
)
_LANGUAGE_OK = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")


@dataclass(frozen=True, slots=True)
class _Item:
    path: str
    media_type: str
    properties: frozenset[str]


@dataclass(frozen=True, slots=True)
class _Book:
    """Validated structure of one file version (cached; contains no chapter content)."""

    title: str | None
    authors: tuple[str, ...]
    language: str | None
    spine: tuple[str, ...]  # member names in reading order
    images: tuple[str, ...]  # member names; the position is the public opaque `rid`
    cover: str | None  # member name of a verified cover image
    toc: tuple[TocEntry, ...]
    chapter_titles: tuple[str, ...]
    css: frozenset[str]
    obfuscated: frozenset[str]
    path_to_spine: dict[str, int] = field(default_factory=dict)
    path_to_rid: dict[str, int] = field(default_factory=dict)


class _FirstImage(HTMLParser):
    """The first image a cover page shows (`<img>` or SVG `<image>`)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.src: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.src is not None:
            return
        name = tag.rsplit(":", 1)[-1].lower()
        wanted = ("src",) if name == "img" else ("href", "xlink:href") if name == "image" else ()
        for key, value in attrs:
            if key.lower() in wanted and value:
                self.src = value
                return


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if local_name(child.tag) == name]


def _first_text(parent: ET.Element | None, name: str) -> str | None:
    if parent is None:
        return None
    for child in _children(parent, name):
        text = text_of(child).strip()
        if text:
            return text
    return None


class EpubExtractor:
    format = "epub"
    item_type = ItemType.BOOK

    def __init__(
        self,
        storage: StorageBackend,
        limits: ExtractorLimits,
        *,
        index_cache_size: int = BOOK_INDEX_CACHE_SIZE,
        gate: BoundedGate | None = None,
    ) -> None:
        self._storage = storage
        self._limits = limits
        self._index: PageIndexCache[_Book] = PageIndexCache(index_cache_size)
        self._gate = gate or default_read_gate()

    @property
    def cached_books(self) -> int:
        return len(self._index)

    # -- Extractor (scan) ---------------------------------------------------------------

    def can_handle(self, entry: StorageEntry) -> bool:
        """Extension AND zip signature (a text file named `.epub` is not handled)."""
        if entry.is_dir or not entry.rel_path.lower().endswith(".epub"):
            return False
        try:
            with self._storage.open(entry.rel_path) as handle:
                return handle.read(4) in ZIP_SIGNATURES
        except (OSError, DomainError):
            return False

    def inspect(self, rel_path: str) -> ItemMetadata:
        with self._session(rel_path) as (_zf, book):
            return ItemMetadata(page_count=len(book.spine), title=book.title, authors=book.authors)

    def read_page(self, rel_path: str, index: int) -> Page:
        raise PageOutOfRange  # a book has chapters, not page images

    def read_cover(self, rel_path: str) -> Page:
        with self._session(rel_path) as (zf, book):
            if book.cover is None:
                raise PageOutOfRange
            return self._image(zf, book.cover)

    # -- BookReader ------------------------------------------------------------------------

    def read_book(self, rel_path: str) -> BookInfo:
        with self._session(rel_path) as (_zf, book):
            return BookInfo(
                title=book.title or "Untitled",
                authors=book.authors,
                language=book.language,
                chapters=tuple(ChapterRef(i, t) for i, t in enumerate(book.chapter_titles)),
                toc=book.toc,
                has_cover=book.cover is not None,
            )

    def read_chapter(
        self,
        rel_path: str,
        index: int,
        *,
        theme: str,
        size: int,
        resource_url: Callable[[int], str],
    ) -> str:
        validate_book_options(theme, size)
        with self._session(rel_path) as (zf, book):
            if isinstance(index, bool) or not 0 <= index < len(book.spine):
                raise PageOutOfRange
            path = book.spine[index]
            if path in book.obfuscated:
                raise UnsupportedFormat
            source = decode_text(self._read(zf, path, MAX_CHAPTER_BYTES))
            base = posixpath.dirname(path)

            def image_rid(src: str) -> int | None:
                resolved = resolve_href(base, src)
                return None if resolved is None else book.path_to_rid.get(resolved[0])

            def chapter_of(href: str) -> tuple[int, str | None] | None:
                resolved = resolve_href(base, href)
                if resolved is None:
                    return None
                target = book.path_to_spine.get(resolved[0])
                return None if target is None else (target, resolved[1])

            def load_css(href: str) -> str | None:
                resolved = resolve_href(base, href)
                if resolved is None or resolved[0] not in book.css:
                    return None
                try:
                    return decode_text(self._read(zf, resolved[0], MAX_CSS_FILE_BYTES))
                except ArchiveLimitExceeded:
                    return None

            body, css = sanitize_chapter(
                source, SanitizeContext(image_rid, chapter_of, load_css, resource_url)
            )
            return build_document(body, css, book.language, theme, size)

    def read_resource(self, rel_path: str, rid: int) -> Page:
        with self._session(rel_path) as (zf, book):
            if isinstance(rid, bool) or not 0 <= rid < len(book.images):
                raise PageOutOfRange
            return self._image(zf, book.images[rid])

    # -- zip access -----------------------------------------------------------------------

    def _validate(self, zf: zipfile.ZipFile) -> None:
        validate_zip(zf, self._limits, size_limited=lambda _name: True)

    @contextmanager
    def _session(self, rel_path: str) -> Iterator[tuple[zipfile.ZipFile, _Book]]:
        entry = self._storage.stat(rel_path)
        key = (rel_path, entry.size, entry.mtime_ns)
        with open_zip(self._storage, rel_path, self._validate) as zf:
            cached = self._index.get(key)
            if cached is None:
                book = self._parse(zf)
                self._index.put(key, (book,))
            else:
                book = cached[0]
            yield zf, book

    def _read(self, zf: zipfile.ZipFile, name: str, limit: int) -> bytes:
        try:
            info = zf.getinfo(name)
        except KeyError:
            raise CorruptArchive from None
        if info.file_size > limit:
            raise ArchiveLimitExceeded
        with self._gate.slot(), zf.open(info) as member:
            data = member.read(limit + 1)
        if len(data) > limit:
            raise ArchiveLimitExceeded
        return data

    def _image(self, zf: zipfile.ZipFile, name: str) -> Page:
        data = self._read(zf, name, MAX_IMAGE_BYTES)
        media_type = sniff_image(data[:HEADER_BYTES])
        if media_type is None:  # declared as an image but it is not (svg, html, ...): not served
            raise PageOutOfRange
        return Page(data=data, media_type=media_type)

    def _head(self, zf: zipfile.ZipFile, name: str) -> bytes:
        try:
            with zf.open(zf.getinfo(name)) as member:
                return member.read(HEADER_BYTES)
        except KeyError:
            raise CorruptArchive from None

    # -- parsing ---------------------------------------------------------------------------

    def _parse(self, zf: zipfile.ZipFile) -> _Book:
        names: dict[str, zipfile.ZipInfo] = {}
        for info in zf.infolist():
            if info.is_dir():
                continue
            if info.filename in names:
                raise CorruptArchive  # two members with one name: ambiguous, refuse
            names[info.filename] = info

        mimetype = names.get("mimetype")
        if mimetype is None or mimetype.file_size > 64:
            raise UnsupportedFormat
        if self._read(zf, "mimetype", 64).strip() != MIMETYPE:
            raise UnsupportedFormat
        if "META-INF/rights.xml" in names:
            raise UnsupportedFormat  # license/DRM descriptor
        obfuscated = self._obfuscated(zf, names)

        opf_path = self._opf_path(zf, names)
        opf = parse_xml(self._read(zf, opf_path, MAX_XML_BYTES))
        if local_name(opf.tag) != "package":
            raise CorruptArchive
        opf_dir = posixpath.dirname(opf_path)
        metadata = next(iter(_children(opf, "metadata")), None)
        manifest = next(iter(_children(opf, "manifest")), None)
        spine = next(iter(_children(opf, "spine")), None)
        guide = next(iter(_children(opf, "guide")), None)
        if manifest is None or spine is None:
            raise CorruptArchive

        items = self._manifest(manifest, opf_dir, names)
        spine_paths = self._spine(spine, items)
        path_to_spine: dict[str, int] = {}
        for position, path in enumerate(spine_paths):
            path_to_spine.setdefault(path, position)
        images: list[str] = []
        path_to_rid: dict[str, int] = {}
        for item in items.values():
            if item.media_type in IMAGE_TYPES and item.path not in path_to_rid:
                if item.path in obfuscated:
                    continue
                path_to_rid[item.path] = len(images)
                images.append(item.path)
        css = frozenset(i.path for i in items.values() if i.media_type == "text/css")

        cover = self._cover(zf, items, metadata, guide, opf_dir, path_to_rid, path_to_spine)
        toc = self._toc(zf, items, spine, path_to_spine)
        raw_title = _first_text(metadata, "title")
        return _Book(
            title=sanitize_title(raw_title) if raw_title else None,
            authors=self._authors(metadata),
            language=self._language(metadata),
            spine=tuple(spine_paths),
            images=tuple(images),
            cover=cover,
            toc=toc,
            chapter_titles=self._chapter_titles(len(spine_paths), toc),
            css=css,
            obfuscated=obfuscated,
            path_to_spine=path_to_spine,
            path_to_rid=path_to_rid,
        )

    def _obfuscated(self, zf: zipfile.ZipFile, names: dict[str, zipfile.ZipInfo]) -> frozenset[str]:
        """Members whose encryption is only font obfuscation. Any other encryption is DRM."""
        if "META-INF/encryption.xml" not in names:
            return frozenset()
        root = parse_xml(self._read(zf, "META-INF/encryption.xml", MAX_XML_BYTES))
        found: set[str] = set()
        for data in root.iter():
            if local_name(data.tag) != "EncryptedData":
                continue
            method = next((c for c in data.iter() if local_name(c.tag) == "EncryptionMethod"), None)
            algorithm = attr(method, "Algorithm") if method is not None else None
            if algorithm not in FONT_OBFUSCATION:
                raise UnsupportedFormat
            for ref in data.iter():
                uri = attr(ref, "URI") if local_name(ref.tag) == "CipherReference" else None
                resolved = resolve_href("", uri) if uri else None
                if resolved is not None:
                    found.add(resolved[0])
        return frozenset(found)

    def _opf_path(self, zf: zipfile.ZipFile, names: dict[str, zipfile.ZipInfo]) -> str:
        if "META-INF/container.xml" not in names:
            raise CorruptArchive
        container = parse_xml(self._read(zf, "META-INF/container.xml", MAX_XML_BYTES))
        full_path = next(
            (
                attr(rootfile, "full-path")
                for rootfile in container.iter()
                if local_name(rootfile.tag) == "rootfile" and attr(rootfile, "full-path")
            ),
            None,
        )
        if not full_path:
            raise CorruptArchive
        resolved = resolve_href("", full_path)
        if resolved is None:
            raise UnsafePath
        if resolved[0] not in names:
            raise CorruptArchive
        return resolved[0]

    def _manifest(
        self, manifest: ET.Element, opf_dir: str, names: dict[str, zipfile.ZipInfo]
    ) -> dict[str, _Item]:
        elements = list(manifest)
        if len(elements) > MAX_MANIFEST_ITEMS:
            raise ArchiveLimitExceeded
        items: dict[str, _Item] = {}
        for element in elements:
            ident, href = attr(element, "id"), attr(element, "href")
            if local_name(element.tag) != "item" or not ident or not href or ident in items:
                continue
            resolved = resolve_href(opf_dir, href)
            # An href that escapes the root, is absolute or points outside the zip is ignored:
            # its content can never be reached.
            if resolved is None or resolved[0] not in names:
                continue
            items[ident] = _Item(
                path=resolved[0],
                media_type=(attr(element, "media-type") or "").strip().lower(),
                properties=frozenset((attr(element, "properties") or "").split()),
            )
        return items

    def _spine(self, spine: ET.Element, items: dict[str, _Item]) -> list[str]:
        refs = list(spine)
        if len(refs) > MAX_SPINE_ITEMS:
            raise ArchiveLimitExceeded
        paths: list[str] = []
        for ref in refs:
            if local_name(ref.tag) != "itemref":
                continue
            item = items.get(attr(ref, "idref") or "")
            if item is not None and item.media_type in HTML_TYPES:
                paths.append(item.path)  # `linear="no"` items are chapters like the others
        if not paths:
            raise UnsupportedFormat
        return paths

    def _authors(self, metadata: ET.Element | None) -> tuple[str, ...]:
        if metadata is None:
            return ()
        authors: list[str] = []
        for child in _children(metadata, "creator"):
            text = text_of(child).strip()
            if not text:
                continue
            name = sanitize_title(text)
            if name not in authors:
                authors.append(name)
            if len(authors) >= MAX_AUTHORS:
                break
        return tuple(authors)

    def _language(self, metadata: ET.Element | None) -> str | None:
        raw = _first_text(metadata, "language")
        if raw is None or not 2 <= len(raw) <= 35 or not set(raw) <= _LANGUAGE_OK:
            return None
        return raw

    # -- cover -----------------------------------------------------------------------------

    def _cover(
        self,
        zf: zipfile.ZipFile,
        items: dict[str, _Item],
        metadata: ET.Element | None,
        guide: ET.Element | None,
        opf_dir: str,
        path_to_rid: dict[str, int],
        path_to_spine: dict[str, int],
    ) -> str | None:
        """The first valid cover among: EPUB3 `cover-image`, EPUB2 `<meta name="cover">`, the
        `<guide>` reference. The file must be a manifest image whose bytes look like an image."""
        candidates: list[str] = [i.path for i in items.values() if "cover-image" in i.properties]
        if metadata is not None:
            for meta in _children(metadata, "meta"):
                target = items.get(attr(meta, "content") or "")
                if attr(meta, "name") == "cover" and target is not None:
                    candidates.append(target.path)
        if guide is not None:
            for ref in _children(guide, "reference"):
                href = attr(ref, "href")
                resolved = resolve_href(opf_dir, href) if href else None
                if (attr(ref, "type") or "").lower() != "cover" or resolved is None:
                    continue
                if resolved[0] in path_to_rid:
                    candidates.append(resolved[0])
                elif resolved[0] in path_to_spine:  # a cover page: use the image it shows
                    shown = self._image_of_page(zf, resolved[0])
                    if shown is not None:
                        candidates.append(shown)
        for path in candidates:
            if path in path_to_rid and sniff_image(self._head(zf, path)) is not None:
                return path
        return None

    def _image_of_page(self, zf: zipfile.ZipFile, page_path: str) -> str | None:
        try:
            parser = _FirstImage()
            parser.feed(decode_text(self._read(zf, page_path, MAX_CHAPTER_BYTES)))
            parser.close()
        except Exception:  # a bad cover page only means "no cover"  # noqa: S110
            return None
        if parser.src is None:
            return None
        resolved = resolve_href(posixpath.dirname(page_path), parser.src)
        return None if resolved is None else resolved[0]

    # -- table of contents ---------------------------------------------------------------

    def _toc(
        self,
        zf: zipfile.ZipFile,
        items: dict[str, _Item],
        spine: ET.Element,
        path_to_spine: dict[str, int],
    ) -> tuple[TocEntry, ...]:
        nav = next(
            (i for i in items.values() if "nav" in i.properties and i.media_type in HTML_TYPES),
            None,
        )
        ncx = items.get(attr(spine, "toc") or "") or next(
            (i for i in items.values() if i.media_type == NCX_TYPE), None
        )
        for source, parse in ((nav, self._nav_entries), (ncx, self._ncx_entries)):
            if source is None:
                continue
            try:  # a broken table of contents never makes the book unreadable
                root = parse_xml(self._read(zf, source.path, MAX_XML_BYTES))
            except (CorruptArchive, ArchiveLimitExceeded):
                continue
            entries = parse(root, posixpath.dirname(source.path), path_to_spine)
            if entries:
                return tuple(entries[:MAX_TOC_ENTRIES])
        return ()

    @staticmethod
    def _entry(
        label: str, href: str | None, base: str, path_to_spine: dict[str, int]
    ) -> TocEntry | None:
        title = clean_text(label)
        resolved = resolve_href(base, href) if href else None
        if not title or resolved is None:
            return None
        index = path_to_spine.get(resolved[0])
        if index is None:
            return None
        return TocEntry(title=sanitize_title(title), index=index, anchor=resolved[1])

    def _nav_entries(
        self, root: ET.Element, base: str, path_to_spine: dict[str, int]
    ) -> list[TocEntry]:
        navs = [e for e in root.iter() if local_name(e.tag) == "nav"]
        chosen = next((n for n in navs if "toc" in (attr(n, "type") or "").split()), None)
        if chosen is None and navs:
            chosen = navs[0]
        entries: list[TocEntry] = []
        if chosen is None:
            return entries
        for link in chosen.iter():
            if local_name(link.tag) == "a":
                entry = self._entry(text_of(link), link.get("href"), base, path_to_spine)
                if entry is not None:
                    entries.append(entry)
        return entries

    def _ncx_entries(
        self, root: ET.Element, base: str, path_to_spine: dict[str, int]
    ) -> list[TocEntry]:
        entries: list[TocEntry] = []
        for point in root.iter():
            if local_name(point.tag) != "navPoint":
                continue
            label = next(
                (text_of(c) for c in point.iter() if local_name(c.tag) == "text"),
                "",
            )
            content = next((c for c in point.iter() if local_name(c.tag) == "content"), None)
            entry = self._entry(
                label, attr(content, "src") if content is not None else None, base, path_to_spine
            )
            if entry is not None:
                entries.append(entry)
        return entries

    @staticmethod
    def _chapter_titles(count: int, toc: tuple[TocEntry, ...]) -> tuple[str, ...]:
        titles: dict[int, str] = {}
        for entry in toc:  # a chapter's own entry (no anchor) wins over a section inside it
            if entry.anchor is None:
                titles.setdefault(entry.index, entry.title)
        for entry in toc:
            titles.setdefault(entry.index, entry.title)
        return tuple(titles.get(i, f"Capitulo {i + 1}") for i in range(count))
