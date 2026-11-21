"""CSS reduction for EPUB chapters (allowlist) and the server-owned theme stylesheet.

The author's CSS is untrusted. It is not "filtered": it is rebuilt. Only rules whose selectors
match a tiny grammar and only declarations whose property and value pass a per-property validator
survive; everything is re-serialized by this module. At-rules (`@import`, `@font-face`,
`@media`...), `url()`, `expression`, escapes, `var()`, comments and anything unknown are dropped.
No text from a request ever enters the CSS (`theme_css` takes a validated theme name and an
integer).
"""

import re
from collections.abc import Callable

from app.domain.book import BOOK_THEMES, MAX_FONT_SCALE, MIN_FONT_SCALE

MAX_RULES = 4000
MAX_OUTPUT_BYTES = 256 * 1024
MAX_SELECTOR_LENGTH = 512
MAX_PRELUDE_LENGTH = 2048
MAX_SELECTORS_PER_RULE = 32
MAX_VALUE_LENGTH = 200

_COMMENT = re.compile(r"/\*.*?(?:\*/|\Z)", re.S)
_FORBIDDEN_IN_VALUE = ("url", "expression", "javascript", "behavior", "binding", "import", "attr")
_VALUE_CHARS = re.compile(r"[a-z0-9 .,#%()+\-]*")
_TOKENS = re.compile(r"[a-z\-]+\([^)]*\)|\S+")
_NUMBER = re.compile(r"(-?)(\d{1,4}(?:\.\d{1,3})?|\.\d{1,3})(px|em|rem|ex|pt|%)?")
_HEX_COLOR = re.compile(r"#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})")
_FUNC_COLOR = re.compile(r"(?:rgb|rgba|hsl|hsla)\([0-9 .,%]{1,60}\)")
_NAMED_COLOR = re.compile(r"[a-z]{3,24}")
_CLASS_ID = r"[A-Za-z_][A-Za-z0-9_\-]{0,127}"
_TAGS = (
    "p|div|span|h1|h2|h3|h4|h5|h6|a|img|ul|ol|li|dl|dt|dd|table|thead|tbody|tfoot|tr|td|th|"
    "caption|blockquote|em|strong|i|b|u|s|sub|sup|small|br|hr|pre|code|figure|figcaption|ruby|"
    "rt|rp|section|article|aside|nav|header|footer|cite|abbr|mark|del|ins|q|body"
)
_PSEUDO = r"(?::{1,2}(?:first-child|last-child|first-letter|first-line|first-of-type|last-of-type))"
_COMPOUND = rf"(?:(?:{_TAGS})(?:[.#]{_CLASS_ID}|{_PSEUDO})*|(?:[.#]{_CLASS_ID}|{_PSEUDO})+)"
_SELECTOR = re.compile(rf"{_COMPOUND}(?:\s*[>+~]\s*{_COMPOUND}|\s+{_COMPOUND})*")
_ALLOWED_TAG_NAMES = frozenset(_TAGS.split("|"))

Validator = Callable[[str], str | None]

_LIMITS = {"px": 2000.0, "em": 40.0, "rem": 40.0, "ex": 40.0, "pt": 1500.0, "%": 1000.0}


def _length(
    token: str, *, negative: bool = False, percent: bool = True, unitless_zero: bool = True
) -> str | None:
    """A bounded CSS length (`12px`, `1.5em`, `50%`, `0`), or None."""
    match = _NUMBER.fullmatch(token)
    if match is None:
        return None
    sign, number, unit = match.groups()
    value = float(number)
    is_negative = bool(sign) and value != 0
    if is_negative and not negative:
        return None
    if unit is None:
        return "0" if value == 0 and unitless_zero else None
    if unit == "%" and not percent:
        return None
    limit = _LIMITS[unit] / 8 if is_negative else _LIMITS[unit]
    if value > limit:
        return None
    return f"{'-' if is_negative else ''}{number}{unit}"


def _bounded(value: str, caps: dict[str, float]) -> str | None:
    """A strictly positive length with a unit, no larger than `caps[unit]`."""
    match = _NUMBER.fullmatch(value)
    if match is None or match.group(1) or match.group(3) is None:
        return None
    number = float(match.group(2))
    if not 0 < number <= caps[match.group(3)]:
        return None
    return f"{match.group(2)}{match.group(3)}"


def _color(token: str) -> str | None:
    if _HEX_COLOR.fullmatch(token) or _FUNC_COLOR.fullmatch(token):
        return token
    if _NAMED_COLOR.fullmatch(token):
        return token
    return None


def _enum(*words: str) -> Validator:
    allowed = frozenset(words)

    def check(value: str) -> str | None:
        return value if value in allowed else None

    return check


def _enum_list(words: tuple[str, ...], max_items: int) -> Validator:
    allowed = frozenset(words)

    def check(value: str) -> str | None:
        parts = value.split()
        if 1 <= len(parts) <= max_items and all(p in allowed for p in parts):
            return " ".join(parts)
        return None

    return check


def _box(*, negative: bool, auto: bool) -> Validator:
    """1 to 4 lengths (margin may also be `auto`)."""

    def check(value: str) -> str | None:
        parts = _TOKENS.findall(value)
        if not 1 <= len(parts) <= 4:
            return None
        out: list[str] = []
        for part in parts:
            if auto and part == "auto":
                out.append(part)
                continue
            length = _length(part, negative=negative)
            if length is None:
                return None
            out.append(length)
        return " ".join(out)

    return check


def _single_length(
    *, negative: bool = False, percent: bool = True, words: tuple[str, ...] = ()
) -> Validator:
    allowed = frozenset(words)

    def check(value: str) -> str | None:
        if value in allowed:
            return value
        return _length(value, negative=negative, percent=percent)

    return check


def _color_value(value: str) -> str | None:
    tokens = _TOKENS.findall(value)
    return _color(tokens[0]) if len(tokens) == 1 else None


def _font_family(value: str) -> str | None:
    generic = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"}
    parts = [p.strip() for p in value.split(",")]
    kept = [p for p in parts if p in generic]
    return ", ".join(kept) if kept else None


_FONT_SIZE_WORDS = (
    "xx-small",
    "x-small",
    "small",
    "medium",
    "large",
    "x-large",
    "xx-large",
    "smaller",
    "larger",
)


def _font_size(value: str) -> str | None:
    if value in _FONT_SIZE_WORDS:
        return value
    return _bounded(value, {"em": 8.0, "rem": 8.0, "ex": 16.0, "px": 128.0, "pt": 96.0, "%": 500.0})


def _font_weight(value: str) -> str | None:
    if value in ("normal", "bold", "bolder", "lighter"):
        return value
    return value if re.fullmatch(r"[1-9]00", value) else None


def _line_height(value: str) -> str | None:
    if value == "normal":
        return value
    if re.fullmatch(r"\d(?:\.\d{1,3})?", value) and 0 < float(value) <= 5:
        return value
    return _bounded(
        value, {"em": 5.0, "rem": 5.0, "ex": 10.0, "px": 200.0, "pt": 150.0, "%": 500.0}
    )


def _border_part(value: str) -> str | None:
    """`border`: up to three tokens, each a width, a style or a color."""
    styles = {"none", "solid", "dashed", "dotted", "double", "groove", "ridge", "inset", "outset"}
    parts = _TOKENS.findall(value)
    if not 1 <= len(parts) <= 3:
        return None
    out: list[str] = []
    for part in parts:
        ok = (
            part
            if part in styles or part in ("thin", "medium", "thick")
            else (_length(part) if _NUMBER.fullmatch(part) else _color(part))
        )
        if ok is None:
            return None
        out.append(ok)
    return " ".join(out)


def _border_width(value: str) -> str | None:
    parts = _TOKENS.findall(value)
    if not 1 <= len(parts) <= 4:
        return None
    out = [p if p in ("thin", "medium", "thick") else _length(p) for p in parts]
    return None if any(o is None for o in out) else " ".join(o for o in out if o)


def _border_style(value: str) -> str | None:
    return _enum_list(
        ("none", "solid", "dashed", "dotted", "double", "groove", "ridge", "inset", "outset"), 4
    )(value)


def _border_color(value: str) -> str | None:
    parts = _TOKENS.findall(value)
    if not 1 <= len(parts) <= 4:
        return None
    out = [_color(p) for p in parts]
    return None if any(o is None for o in out) else " ".join(o for o in out if o)


def _list_style(value: str) -> str | None:
    kinds = (
        "none",
        "disc",
        "circle",
        "square",
        "decimal",
        "decimal-leading-zero",
        "lower-roman",
        "upper-roman",
        "lower-alpha",
        "upper-alpha",
        "lower-latin",
        "upper-latin",
        "lower-greek",
        "inside",
        "outside",
    )
    return _enum_list(kinds, 2)(value)


def _break(value: str) -> str | None:
    return _enum("auto", "always", "avoid", "left", "right", "page", "column", "avoid-page")(value)


def _integer_small(value: str) -> str | None:
    return value if re.fullmatch(r"[0-9]{1,2}", value) else None


_PROPERTIES: dict[str, Validator] = {
    "color": _color_value,
    "background-color": _color_value,
    "font-family": _font_family,
    "font-size": _font_size,
    "font-style": _enum("normal", "italic", "oblique"),
    "font-weight": _font_weight,
    "font-variant": _enum("normal", "small-caps"),
    "text-align": _enum("left", "right", "center", "justify", "start", "end"),
    "text-decoration": _enum_list(("none", "underline", "overline", "line-through"), 3),
    "text-transform": _enum("none", "uppercase", "lowercase", "capitalize"),
    "text-indent": _single_length(negative=True),
    "line-height": _line_height,
    "vertical-align": _enum(
        "baseline", "sub", "super", "top", "middle", "bottom", "text-top", "text-bottom"
    ),
    "white-space": _enum("normal", "nowrap", "pre", "pre-wrap", "pre-line"),
    "word-break": _enum("normal", "break-all", "keep-all", "break-word"),
    "overflow-wrap": _enum("normal", "break-word", "anywhere"),
    "direction": _enum("ltr", "rtl"),
    "writing-mode": _enum("horizontal-tb", "vertical-rl", "vertical-lr"),
    "display": _enum(
        "block",
        "inline",
        "inline-block",
        "none",
        "list-item",
        "table",
        "table-row",
        "table-cell",
        "table-caption",
        "table-row-group",
        "table-header-group",
        "table-footer-group",
    ),
    "float": _enum("left", "right", "none"),
    "clear": _enum("left", "right", "both", "none"),
    "width": _single_length(words=("auto",)),
    "height": _single_length(words=("auto",)),
    "max-width": _single_length(words=("none",)),
    "min-width": _single_length(),
    "max-height": _single_length(words=("none",)),
    "min-height": _single_length(),
    "margin": _box(negative=True, auto=True),
    "padding": _box(negative=False, auto=False),
    "border": _border_part,
    "border-width": _border_width,
    "border-style": _border_style,
    "border-color": _border_color,
    "border-collapse": _enum("collapse", "separate"),
    "border-spacing": _box(negative=False, auto=False),
    "list-style": _list_style,
    "list-style-type": _list_style,
    "list-style-position": _enum("inside", "outside"),
    "page-break-before": _break,
    "page-break-after": _break,
    "page-break-inside": _enum("auto", "avoid"),
    "break-before": _break,
    "break-after": _break,
    "break-inside": _enum("auto", "avoid", "avoid-page"),
    "orphans": _integer_small,
    "widows": _integer_small,
}
for _side in ("top", "right", "bottom", "left"):
    _PROPERTIES[f"margin-{_side}"] = _single_length(negative=True, words=("auto",))
    _PROPERTIES[f"padding-{_side}"] = _single_length()
    _PROPERTIES[f"border-{_side}"] = _border_part
    _PROPERTIES[f"border-{_side}-width"] = _border_width
    _PROPERTIES[f"border-{_side}-style"] = _border_style
    _PROPERTIES[f"border-{_side}-color"] = _border_color


def _clean_value(raw: str) -> str | None:
    value = raw.strip().lower()
    if value.endswith("!important"):  # authors never get `!important`: the theme wins
        value = value[: -len("!important")].strip()
    if not value or len(value) > MAX_VALUE_LENGTH:
        return None
    if any(word in value for word in _FORBIDDEN_IN_VALUE) or not _VALUE_CHARS.fullmatch(value):
        return None
    return " ".join(value.split())


def sanitize_declarations(block: str) -> str:
    """`prop: value; ...` (a rule body or a `style` attribute) reduced to the allowlist, as
    `prop:value;prop:value`. Every piece between `;` is judged on its own."""
    out: list[str] = []
    for piece in block.split(";"):
        name, sep, raw_value = piece.partition(":")
        name = name.strip().lower()
        validator = _PROPERTIES.get(name)
        if not sep or validator is None:
            continue
        if name == "font-family":  # quoted family names are legal; only generic families are kept
            raw_value = raw_value.replace('"', "").replace("'", "")
        value = _clean_value(raw_value)
        if value is None:
            continue
        checked = validator(value)
        if checked:
            out.append(f"{name}:{checked}")
    return ";".join(out)


def _selector_ok(selector: str) -> bool:
    return (
        0 < len(selector) <= MAX_SELECTOR_LENGTH
        and "*" not in selector
        and _SELECTOR.fullmatch(selector) is not None
    )


def _skip_at_rule(text: str, start: int) -> int:
    """Index just after the at-rule that begins at `start` (up to `;` or the matching `}`)."""
    length = len(text)
    i = start
    while i < length and text[i] not in ";{":
        i += 1
    if i >= length:
        return length
    if text[i] == ";":
        return i + 1
    depth = 0
    while i < length:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return length


def sanitize_css(source: str) -> str:
    """Rebuild a stylesheet from the allowlist. Never raises; unusable input gives ''."""
    text = _COMMENT.sub(" ", source.replace("\x00", ""))
    rules: list[str] = []
    size = 0
    i = 0
    length = len(text)
    while i < length and len(rules) < MAX_RULES and size < MAX_OUTPUT_BYTES:
        while i < length and text[i] in " \t\r\n}":
            i += 1
        if i >= length:
            break
        if text[i] == "@":
            i = _skip_at_rule(text, i)
            continue
        brace = text.find("{", i)
        if brace == -1:
            break
        end = text.find("}", brace)
        if end == -1:
            end = length
        prelude, body = text[i:brace], text[brace + 1 : end]
        i = end + 1
        if "@" in body or "{" in body:  # something nested we do not understand: drop the rule
            continue
        if len(prelude) > MAX_PRELUDE_LENGTH or prelude.count(",") >= MAX_SELECTORS_PER_RULE:
            continue
        selectors = [s.strip() for s in prelude.split(",")]
        if not selectors or not all(_selector_ok(s) for s in selectors):
            continue
        declarations = sanitize_declarations(body)
        if declarations:
            rule = f"{','.join(selectors)}{{{declarations}}}"
            rules.append(rule)
            size += len(rule)
    return "\n".join(rules)


# ---------------------------------------------------------------------------------- theme

_PALETTE = {
    "light": ("#ffffff", "#1b1b1b", "#0b57d0"),
    "dark": ("#121212", "#e4e4e4", "#8ab4f8"),
    "sepia": ("#f4ecd8", "#4b3621", "#7a4b12"),
}


def _colors(name: str, *, force_descendants: bool) -> str:
    bg, fg, link = _PALETTE[name]
    css = f"html,body{{background:{bg} !important;color:{fg} !important}}"
    if force_descendants:
        # Author colors are not trusted to keep contrast on a dark/sepia page.
        css += "body *{color:inherit !important;background-color:transparent !important}"
    return css + f"body a{{color:{link} !important}}"


def theme_css(theme: str, size: int) -> str:
    """The server's final stylesheet. Built only from a validated theme name and an integer."""
    if theme not in BOOK_THEMES or isinstance(size, bool) or not isinstance(size, int):
        raise ValueError("invalid theme")
    if not MIN_FONT_SCALE <= size <= MAX_FONT_SCALE:
        raise ValueError("invalid size")
    base = (
        f"html{{font-size:{size}%;-webkit-text-size-adjust:100%}}"
        "body{margin:0 auto;padding:1.25em 1em 3em;max-width:46em;line-height:1.65;"
        "font-family:Georgia,'Times New Roman',serif;overflow-wrap:anywhere}"
        "img{max-width:100%;height:auto}table{max-width:100%}pre{white-space:pre-wrap}"
    )
    if theme == "auto":
        light = _colors("light", force_descendants=False)
        dark = _colors("dark", force_descendants=True)
        return f"{base}{light}@media (prefers-color-scheme:dark){{{dark}}}"
    return base + _colors(theme, force_descendants=theme != "light")
