"""HTML sanitizer for EPUB chapters: allowlist, `html.parser`, and OUR OWN re-serialization.

The original markup is never passed through. The input is only used to decide which allowed tags
and attributes to write; every text and attribute value is escaped by this module and every tag it
writes is closed in the right order, so what a browser parses is exactly what was decided here (no
mutation XSS, no namespace confusion: svg/math and every unknown element are removed). Scripts,
styles (rebuilt separately from an allowlist), frames, forms, embeds, links to the outside and every
`on*` attribute never reach the output.
"""

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser

from app.adapters.extractors._epub_css import sanitize_css, sanitize_declarations, theme_css
from app.adapters.extractors._epub_safe import safe_fragment, safe_ident
from app.domain.errors import ArchiveLimitExceeded, CorruptArchive

MAX_DEPTH = 100
MAX_ATTRIBUTE_LENGTH = 4096
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_STYLESHEETS = 16
MAX_CSS_BYTES = 512 * 1024


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


ALLOWED_TAGS = _words(
    "p div span h1 h2 h3 h4 h5 h6 a img ul ol li dl dt dd table thead tbody tfoot tr td th "
    "caption blockquote em strong i b u s sub sup small br hr pre code figure figcaption ruby "
    "rt rp section article aside nav header footer cite abbr mark del ins q"
)
VOID_TAGS = frozenset({"img", "br", "hr"})
# Removed together with everything inside them.
DROP_WITH_CONTENT = _words(
    "script style iframe object form button select textarea svg math template noscript title "
    "applet frameset noframes audio video canvas datalist dialog"
)
# Void elements that are simply removed (nothing inside to drop).
DROP_VOID = _words("link meta base input embed source track param area col frame wbr")

# Optional end tags: opening one of these closes a still-open sibling (`<p>a<p>b`).
_AUTO_CLOSE = {
    "p": frozenset({"p"}),
    "li": frozenset({"li"}),
    "dt": frozenset({"dt", "dd"}),
    "dd": frozenset({"dt", "dd"}),
    "tr": frozenset({"td", "th", "tr"}),
    "td": frozenset({"td", "th"}),
    "th": frozenset({"td", "th"}),
    "thead": frozenset({"td", "th", "tr", "thead", "tbody", "tfoot"}),
    "tbody": frozenset({"td", "th", "tr", "thead", "tbody", "tfoot"}),
    "tfoot": frozenset({"td", "th", "tr", "thead", "tbody", "tfoot"}),
}

_CLASS_TOKEN = re.compile(r"[A-Za-z0-9_:.\-]{1,128}")
_LANG = re.compile(r"[A-Za-z0-9\-]{1,35}")
_DIGITS = re.compile(r"[0-9]{1,5}")
_CONTROL_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f￾￿]")


@dataclass(frozen=True, slots=True)
class SanitizeContext:
    """What the sanitizer needs to know about the book (supplied by the EPUB reader).

    `image_rid(src)`: opaque id of a manifest image the reference points at, else None.
    `chapter_of(href)`: `(spine index, fragment)` of a link to another chapter, else None
    (this includes every external, absolute, scripted or malformed link).
    `load_css(href)`: text of a manifest stylesheet, else None.
    `resource_url(rid)`: public URL for an image.
    """

    image_rid: Callable[[str], int | None]
    chapter_of: Callable[[str], tuple[int, str | None] | None]
    load_css: Callable[[str], str | None]
    resource_url: Callable[[int], str]


def _text(value: str) -> str:
    return html.escape(_CONTROL_TEXT.sub("", value), quote=False)


def _attribute(value: str) -> str:
    return html.escape(_CONTROL_TEXT.sub("", value), quote=True)


class _ChapterSanitizer(HTMLParser):
    def __init__(self, ctx: SanitizeContext) -> None:
        super().__init__(convert_charrefs=True)
        self._ctx = ctx
        self._out: list[str] = []
        self._size = 0
        self._stack: list[str] = []
        self._skip: str | None = None  # local name of the dropped element we are inside
        self._skip_depth = 0
        self._css: list[str] = []
        self._css_bytes = 0
        self._sheets = 0
        self._style_buffer = ""

    # -- output helpers --------------------------------------------------------------

    def _emit(self, chunk: str) -> None:
        self._size += len(chunk)
        if self._size > MAX_OUTPUT_BYTES:
            raise ArchiveLimitExceeded
        self._out.append(chunk)

    def _close_top(self) -> None:
        self._emit(f"</{self._stack.pop()}>")

    def result(self) -> tuple[str, str]:
        """`(body html, sanitized author css)`; closes anything still open."""
        if self._skip == "style":  # an unclosed <style> still counts
            self._flush_style()
        while self._stack:
            self._close_top()
        return "".join(self._out), "\n".join(self._css)

    # -- attributes -------------------------------------------------------------------

    def _attributes(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
        kept: list[tuple[str, str]] = []
        seen: set[str] = set()
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = raw_value or ""
            if len(value) > MAX_ATTRIBUTE_LENGTH or "\x00" in value:
                continue  # huge or NUL-bearing values are dropped, never truncated
            clean = self._one_attribute(tag, name, value.strip())
            if clean is not None and clean[0] not in seen:  # first one wins, like a browser
                seen.add(clean[0])
                kept.append(clean)
        return kept

    def _one_attribute(self, tag: str, name: str, value: str) -> tuple[str, str] | None:
        if name == "id" or (name == "name" and tag == "a"):
            ident = safe_ident(value)
            return ("id", ident) if ident else None
        if name == "class":
            tokens = [t for t in value.split() if _CLASS_TOKEN.fullmatch(t)]
            return ("class", " ".join(tokens)) if tokens else None
        if name == "title":
            return ("title", value) if value else None
        if name in ("lang", "xml:lang"):
            return ("lang", value) if _LANG.fullmatch(value) else None
        if name == "dir":
            return ("dir", value.lower()) if value.lower() in ("ltr", "rtl", "auto") else None
        if name == "style":
            declarations = sanitize_declarations(value)
            return ("style", declarations) if declarations else None
        if name in ("colspan", "rowspan") and tag in ("td", "th"):
            if _DIGITS.fullmatch(value) and 1 <= int(value) <= 1000:
                return (name, str(int(value)))
            return None
        if tag == "img" and name == "alt":
            return ("alt", value)
        if tag == "img" and name in ("width", "height"):
            return (name, value) if _DIGITS.fullmatch(value) and 0 < int(value) <= 20000 else None
        return None  # everything else, in particular `on*`, `srcset`, `sizes`, `loading`, `src`

    def _link_attributes(self, value: str) -> list[tuple[str, str]]:
        """`href` of an `<a>`: an anchor of this chapter or a link to another chapter of the book;
        everything else (external, scripted, malformed) yields no attribute at all."""
        if value.startswith("#"):
            fragment = safe_fragment(value[1:])
            return [("href", f"#{fragment}")] if fragment else []
        target = self._ctx.chapter_of(value)
        if target is None:
            return []
        index, fragment_part = target
        suffix = f"#{fragment_part}" if fragment_part else ""
        return [("href", f"?goto={index}{suffix}"), ("data-goto", str(index))]

    # -- element handling -----------------------------------------------------------------

    @staticmethod
    def _name(tag: str) -> str:
        return tag.rsplit(":", 1)[-1].lower()  # `svg:script` and `o:p` are judged by local name

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = self._name(tag)
        if self._skip is not None:
            self._in_skipped_start(name, attrs)
            return
        if name in DROP_WITH_CONTENT:
            self._skip, self._skip_depth = name, 1
            return
        if name == "link":
            self._link_stylesheet(attrs)
            return
        if name in DROP_VOID or name not in ALLOWED_TAGS:
            return  # unknown/foreign element: its children stay, the tag does not
        if name == "img":
            self._image(attrs)
            return
        self._open(name, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # A self-closing tag is an empty element (the book is XHTML); nothing after it is eaten.
        name = self._name(tag)
        if self._skip is not None:
            if self._skip == "svg" and name == "image":
                self._svg_image(attrs)
            return
        self.handle_starttag(tag, attrs)
        if name in DROP_WITH_CONTENT:
            self._skip = None
            self._skip_depth = 0
        elif name in ALLOWED_TAGS and name not in VOID_TAGS:
            self.handle_endtag(tag)

    def _in_skipped_start(self, name: str, attrs: list[tuple[str, str | None]]) -> None:
        if name == self._skip:
            self._skip_depth += 1
        elif self._skip == "svg" and name == "image":
            self._svg_image(attrs)

    def _open(self, name: str, attrs: list[tuple[str, str | None]]) -> None:
        closers = _AUTO_CLOSE.get(name)
        if closers is not None:
            while self._stack and self._stack[-1] in closers:
                self._close_top()
        if len(self._stack) >= MAX_DEPTH:
            raise ArchiveLimitExceeded
        pairs = self._attributes(name, attrs)
        if name == "a":
            href = next((v for k, v in attrs if k.lower() == "href" and v), None)
            if href is not None and len(href) <= MAX_ATTRIBUTE_LENGTH:
                pairs.extend(self._link_attributes(href.strip()))
        rendered = "".join(f' {k}="{_attribute(v)}"' for k, v in pairs)
        self._emit(f"<{name}{rendered}>")
        if name in VOID_TAGS:
            return
        self._stack.append(name)

    def _image(self, attrs: list[tuple[str, str | None]]) -> None:
        src = next((v for k, v in attrs if k.lower() == "src" and v), None)
        self._emit_image(src, attrs)

    def _svg_image(self, attrs: list[tuple[str, str | None]]) -> None:
        src = next((v for k, v in attrs if k.lower() in ("href", "xlink:href") and v), None)
        self._emit_image(src, [])

    def _emit_image(self, src: str | None, attrs: list[tuple[str, str | None]]) -> None:
        if src is None or len(src) > MAX_ATTRIBUTE_LENGTH:
            return
        rid = self._ctx.image_rid(src.strip())
        if rid is None:
            return  # not an image of this book (external, svg, data:...): nothing is written
        pairs = [("src", self._ctx.resource_url(rid))]
        pairs.extend(self._attributes("img", attrs))
        if not any(k == "alt" for k, _ in pairs):
            pairs.append(("alt", ""))
        rendered = "".join(f' {k}="{_attribute(v)}"' for k, v in pairs)
        self._emit(f"<img{rendered}>")

    def _link_stylesheet(self, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        if "stylesheet" not in values.get("rel", "").lower().split() or not values.get("href"):
            return
        if self._sheets >= MAX_STYLESHEETS or len(values["href"]) > MAX_ATTRIBUTE_LENGTH:
            return
        self._sheets += 1
        text = self._ctx.load_css(values["href"].strip())
        if text is not None:
            self._add_css(text)

    def _add_css(self, text: str) -> None:
        if self._css_bytes >= MAX_CSS_BYTES:
            return
        self._css_bytes += len(text)
        rebuilt = sanitize_css(text[:MAX_CSS_BYTES])
        if rebuilt:
            self._css.append(rebuilt)

    def handle_endtag(self, tag: str) -> None:
        name = self._name(tag)
        if self._skip is not None:
            if name == self._skip:
                self._skip_depth -= 1
                if self._skip_depth == 0:
                    if self._skip == "style":
                        self._flush_style()
                    self._skip = None
            return
        if name not in ALLOWED_TAGS or name in VOID_TAGS:
            return
        if name not in self._stack:
            return  # stray end tag
        while self._stack:
            top = self._stack[-1]
            self._close_top()
            if top == name:
                break

    def handle_data(self, data: str) -> None:
        if self._skip == "style":
            self._style_buffer += data
            if len(self._style_buffer) > MAX_CSS_BYTES:
                raise ArchiveLimitExceeded
            return
        if self._skip is not None:
            return
        self._emit(_text(data))

    def _flush_style(self) -> None:
        if self._style_buffer:
            self._add_css(self._style_buffer)
        self._style_buffer = ""

    # Comments (conditional ones included), DOCTYPE, processing instructions and CDATA/unknown
    # declarations are never written.
    def handle_comment(self, data: str) -> None:
        return

    def handle_decl(self, decl: str) -> None:
        return

    def handle_pi(self, data: str) -> None:
        return

    def unknown_decl(self, data: str) -> None:
        return


def sanitize_chapter(source: str, ctx: SanitizeContext) -> tuple[str, str]:
    """`(body html, author css)` for one chapter. Raises `CorruptArchive` if the parser fails and
    `ArchiveLimitExceeded` when the nesting or the output is beyond the limits."""
    parser = _ChapterSanitizer(ctx)
    try:
        parser.feed(source.replace("\x00", ""))
        parser.close()
    except (ArchiveLimitExceeded, CorruptArchive):
        raise
    except Exception as exc:  # the stdlib parser may raise anything on hostile input
        raise CorruptArchive from exc
    return parser.result()


def build_document(body: str, author_css: str, language: str | None, theme: str, size: int) -> str:
    """The complete HTML document served to the iframe. The server's own theme style comes last."""
    lang = f' lang="{_attribute(language)}"' if language and _LANG.fullmatch(language) else ""
    return (
        "<!DOCTYPE html>"
        f'<html{lang}><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<style>{author_css}</style><style>{theme_css(theme, size)}</style>"
        f"</head><body>{body}</body></html>"
    )
