"""Primitives for hostile EPUB input: href resolution, XML parsing, text decoding, CSS reduction."""

import contextlib

import pytest
from app.adapters.extractors._epub_css import sanitize_css, sanitize_declarations, theme_css
from app.adapters.extractors._epub_safe import decode_text, parse_xml, resolve_href, safe_fragment
from app.domain.errors import CorruptArchive

# ---------------------------------------------------------------- resolve_href


@pytest.mark.parametrize(
    ("base", "href", "expected"),
    [
        ("OEBPS/text", "ch1.xhtml", ("OEBPS/text/ch1.xhtml", None)),
        ("OEBPS/text", "../images/a.png", ("OEBPS/images/a.png", None)),
        ("OEBPS/text", "ch1.xhtml#sec_1", ("OEBPS/text/ch1.xhtml", "sec_1")),
        ("OEBPS/text", "./a/../b.xhtml", ("OEBPS/text/b.xhtml", None)),
        ("", "a%20b.xhtml", ("a b.xhtml", None)),
        ("OEBPS", "caf%C3%A9.xhtml", ("OEBPS/café.xhtml", None)),
        ("OEBPS", "ch1.xhtml#bad frag", ("OEBPS/ch1.xhtml", None)),
        ("OEBPS", " \tch1.xhtml\n", ("OEBPS/ch1.xhtml", None)),
    ],
)
def test_good_hrefs_resolve_inside_the_root(
    base: str, href: str, expected: tuple[str, str | None]
) -> None:
    assert resolve_href(base, href) == expected


@pytest.mark.parametrize(
    ("base", "href"),
    [
        ("OEBPS", "../../etc/passwd"),
        ("", "../x"),
        ("", ".."),
        ("OEBPS", "../.."),
        ("OEBPS", "a/../../../x"),
        ("OEBPS", "/etc/passwd"),
        ("OEBPS", "//evil.example/x.png"),
        ("OEBPS", "C:/windows/x"),
        ("OEBPS", "c:\\windows\\x"),
        ("OEBPS", "..\\..\\x"),
        ("OEBPS", "a\\b.xhtml"),
        ("OEBPS", "http://evil.example/x"),
        ("OEBPS", "https://evil.example/x"),
        ("OEBPS", "javascript:alert(1)"),
        ("OEBPS", "java\nscript:alert(1)"),
        ("OEBPS", "jav\tascript:alert(1)"),
        ("OEBPS", "data:image/png;base64,AAAA"),
        ("OEBPS", "mailto:a@b.c"),
        ("OEBPS", "file:///etc/passwd"),
        ("OEBPS", "ch1.xhtml?x=1"),
        ("OEBPS", "?goto=1"),
        ("OEBPS", "%2e%2e/%2e%2e/etc/passwd"),  # decodes to ../..: still refused
        ("OEBPS", "%252e%252e/x"),  # double encoding
        ("OEBPS", "a%2500b"),
        ("OEBPS", "a%00b"),
        ("OEBPS", "%2Fetc%2Fpasswd"),
        ("OEBPS", "%5Cwindows"),
        ("OEBPS", "%ff.xhtml"),  # invalid UTF-8
        ("OEBPS", "a\x00b"),
        ("OEBPS", ""),
        ("OEBPS", "#only-fragment"),
        ("OEBPS", "x" * 3000),
    ],
)
def test_hostile_hrefs_are_refused(base: str, href: str) -> None:
    assert resolve_href(base, href) is None


def test_safe_fragment() -> None:
    assert safe_fragment("a-b_c.d:e") == "a-b_c.d:e"
    for bad in ("", "a b", "a/b", "x" * 129, "é", "a\n", '"><'):
        assert safe_fragment(bad) is None


# ---------------------------------------------------------------- XML


def test_plain_xml_parses() -> None:
    root = parse_xml(b'<?xml version="1.0"?><a><b>x</b></a>')
    assert root.tag == "a"


@pytest.mark.parametrize(
    "xml",
    [
        b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>',
        b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>',
        b'<!DOCTYPE a SYSTEM "http://evil.example/x.dtd" [<!ENTITY % p SYSTEM "http://evil/">%p;]><a/>',
        b'<!doctype a [ <!entity x "y"> ]><a>&x;</a>',
        b"<!DOCTYPE a [<!ELEMENT a ANY>]><a/>",
        b'<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">]>'
        b"<lolz>&lol2;</lolz>",
        b'<!DOCTYPE a SYSTEM "x>y" [<!ENTITY z "q">]><a>&z;</a>',
        "\ufeff<!DOCTYPE a [<!ENTITY x 'y'>]><a>&x;</a>".encode("utf-16"),
        b"<a><b></a>",
        b"",
        b"not xml",
        b"<a>&undefined;</a>",
    ],
)
def test_entities_and_broken_xml_are_a_generic_corrupt_archive(xml: bytes) -> None:
    with pytest.raises(CorruptArchive):
        parse_xml(xml)


def test_doctype_without_internal_subset_is_tolerated_and_removed() -> None:
    root = parse_xml(
        b'<?xml version="1.0"?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
        b'"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd"><html><body>x</body></html>'
    )
    assert root.tag == "html"


def test_deeply_nested_xml_is_not_a_crash() -> None:
    xml = b"<a>" * 5000 + b"</a>" * 5000
    with contextlib.suppress(CorruptArchive):  # either parsed or a generic error: never a crash
        parse_xml(xml)


# ---------------------------------------------------------------- text decoding


def test_decoding_utf8_utf16_and_declared_latin1() -> None:
    assert decode_text("ação".encode()) == "ação"
    assert decode_text(b"\xef\xbb\xbfa\xc3\xa7") == "aç"
    assert decode_text("<p>ação</p>".encode("utf-16")) == "<p>ação</p>"
    assert decode_text("<p>ação</p>".encode("utf-16-le")) == "<p>ação</p>"  # no BOM
    assert decode_text("<p>ação</p>".encode("utf-16-be")) == "<p>ação</p>"
    latin = b'<?xml version="1.0" encoding="ISO-8859-1"?><p>a\xe7\xe3o</p>'
    assert decode_text(latin).endswith("<p>ação</p>")
    html = b'<html><head><meta charset="windows-1252"></head><p>\x93q\x94</p></html>'
    assert "\u201cq\u201d" in decode_text(html)


def test_hostile_declared_encodings_fall_back_to_utf8() -> None:
    for name in ("rot13", "unicode_escape", "idna", "base64", "zlib_codec", "bogus", "utf-7"):
        data = f'<?xml version="1.0" encoding="{name}"?><p>abc</p>'.encode()
        assert decode_text(data).endswith("<p>abc</p>")


def test_nulls_and_bad_bytes_never_raise() -> None:
    assert decode_text(b"a\x00b\xff\xfe").startswith("ab")
    assert decode_text(b"\xff\xfe\x00") != ""  # truncated utf-16 with BOM: replaced, not raised


# ---------------------------------------------------------------- CSS


def test_css_keeps_only_allowlisted_properties_and_values() -> None:
    css = sanitize_css(
        "p { color: #333; text-align: justify; margin: 0 auto; font-size: 1.2em; "
        "line-height: 1.5; text-indent: 1.5em; border: 1px solid #ccc; float: left; "
        "width: 50%; page-break-after: always; font-family: 'Georgia', serif; }"
    )
    for kept in (
        "color:#333",
        "text-align:justify",
        "margin:0 auto",
        "font-size:1.2em",
        "line-height:1.5",
        "text-indent:1.5em",
        "border:1px solid #ccc",
        "float:left",
        "width:50%",
        "page-break-after:always",
        "font-family:serif",
    ):
        assert kept in css, kept


@pytest.mark.parametrize(
    "css",
    [
        "@import url(http://evil/x.css); p{color:red}",
        "@import 'x.css';",
        "@font-face{font-family:x;src:url(http://evil/x.woff)}",
        "@charset 'utf-8'; @namespace x url(y);",
        "@media screen{p{background:url(x)}}",
        "@keyframes x{from{color:red}}",
        "@supports (display:grid){p{color:red}}",
        "p{background:url(http://evil/x.png)}",
        "p{background-image:url(x)}",
        "p{background-color:url(x)}",
        "p{color:expression(alert(1))}",
        "p{width:expression(alert(1))}",
        "p{behavior:url(x.htc)}",
        "p{-moz-binding:url(x)}",
        "p{color:red;position:fixed;top:0;left:0;z-index:99999}",
        "p{content:'x';cursor:url(x),auto}",
        "p{color:\\72ed}",
        "p{background:u\\72l(http://evil)}",
        "p{color:javascript:alert(1)}",
        "p{list-style:url(x)}",
        "p{margin:var(--x)}",
        "p{width:calc(100% - 1px)}",
        "p{font-size:1000em}",
        "p{margin:99999px}",
        "p{display:flex}",
        "p{float:inline-start}",
        "*{color:red}",
        "body *{color:red}",
        "html{background:red}",
        ":root{color:red}",
        "a:hover{color:red}",
        "p::before{color:red}",
        "p[href^='http']{color:red}",
        "p:not(.x){color:red}",
        "p{color:red",  # unterminated: nothing comes out as a closed rule with junk
    ],
)
def test_css_hostile_input_never_survives(css: str) -> None:
    out = sanitize_css(css)
    lowered = out.lower()
    for bad in (
        "url",
        "import",
        "expression",
        "behavior",
        "binding",
        "javascript",
        "@",
        "\\",
        "position",
        "flex",
        "*",
        ":hover",
        "z-index",
        "var(",
        "calc",
    ):
        assert bad not in lowered, (bad, css)
    assert "99999" not in lowered and "1000em" not in lowered


def test_css_comments_cannot_smuggle_values() -> None:
    assert "url" not in sanitize_css("p{background:ur/**/l(http://evil)}")
    assert sanitize_css("/* p{color:red} */ q{color:blue}") == "q{color:blue}"
    assert sanitize_css("p{color:red} /* unterminated") == "p{color:red}"


def test_css_limits_do_not_hang() -> None:
    assert sanitize_css("p{color:red}" * 100_000).count("{") <= 4000
    assert sanitize_css("{" * 100_000) == ""
    assert sanitize_css("@media{" * 50_000) == ""
    assert sanitize_css("p," * 100_000 + "q{color:red}") == ""  # too many selectors in one rule


def test_css_important_is_never_kept() -> None:
    assert sanitize_declarations("color: red !important") == "color:red"
    assert "important" not in sanitize_css("p{margin:0 !important}")


def test_css_selectors_are_validated_one_by_one() -> None:
    out = sanitize_css("h1, .a#b > p.c + em, *, a:hover {color: red}")
    assert out == ""  # one bad selector in the list invalidates the whole rule
    assert sanitize_css("h1, .a#b > p.c + em:first-child {color: red}") == (
        "h1,.a#b > p.c + em:first-child{color:red}"
    )


def test_theme_css_only_from_validated_values() -> None:
    assert "font-size:130%" in theme_css("sepia", 130)
    for theme, size in (("x", 100), ("dark", 10), ("dark", 500), ("dark", "120")):
        with pytest.raises(ValueError):
            theme_css(theme, size)  # type: ignore[arg-type]
