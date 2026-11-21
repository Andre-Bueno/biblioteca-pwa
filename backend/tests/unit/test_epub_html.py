"""Sanitizer battery: whatever the chapter contains, the OUTPUT (parsed again, independently) has no
script, handler, dangerous URL or external resource."""

import re
from html.parser import HTMLParser

import pytest
from app.adapters.extractors._epub_html import (
    ALLOWED_TAGS,
    SanitizeContext,
    build_document,
    sanitize_chapter,
)
from app.domain.errors import ArchiveLimitExceeded

RES = "/api/v1/items/00000000-0000-4000-8000-000000000000/book/res/"
ALLOWED_ATTRS = {
    "id",
    "class",
    "title",
    "lang",
    "dir",
    "style",
    "colspan",
    "rowspan",
    "alt",
    "width",
    "height",
    "href",
    "src",
    "data-goto",
}


def context(
    *,
    images: dict[str, int] | None = None,
    chapters: dict[str, int] | None = None,
    sheets: dict[str, str] | None = None,
) -> SanitizeContext:
    images = images or {"pic.png": 0, "../images/pic.png": 0}
    chapters = chapters or {"ch2.xhtml": 2}
    sheets = sheets or {}

    def chapter_of(href: str) -> tuple[int, str | None] | None:
        name, _, frag = href.partition("#")
        return (chapters[name], frag or None) if name in chapters else None

    return SanitizeContext(
        image_rid=images.get,
        chapter_of=chapter_of,
        load_css=sheets.get,
        resource_url=lambda rid: f"{RES}{rid}",
    )


class _Collector(HTMLParser):
    """Independent re-parse of the output: records every tag, attribute and text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str, str | None]] = []
        self.text = ""
        self.comments = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs.extend((tag, k, v) for k, v in attrs)

    def handle_data(self, data: str) -> None:
        self.text += data

    def handle_comment(self, data: str) -> None:
        self.comments += 1


def parse(output: str) -> _Collector:
    collector = _Collector()
    collector.feed(output)
    collector.close()
    return collector


def assert_clean(output: str) -> _Collector:
    """The invariants of every sanitized chapter."""
    found = parse(output)
    assert set(found.tags) <= ALLOWED_TAGS, set(found.tags) - ALLOWED_TAGS
    assert found.comments == 0
    for tag, name, value in found.attrs:
        assert name in ALLOWED_ATTRS, (tag, name)
        assert not name.startswith("on")
        if name == "href":
            assert tag == "a" and value is not None
            assert value.startswith(("#", "?goto=")), value
        if name == "src":
            assert tag == "img" and value is not None and value.startswith(RES), value
        if name == "style":
            assert value is not None
            for bad in ("url", "expression", "javascript", "behavior", "@import", "binding"):
                assert bad not in value.lower()
    lowered = output.lower()
    for bad in ("<script", "javascript:", "<iframe", "<svg", "<math", "<base", "<form", "<object"):
        assert bad not in lowered, bad
    return found


def clean(source: str, ctx: SanitizeContext | None = None) -> tuple[str, str]:
    body, css = sanitize_chapter(source, ctx or context())
    assert_clean(body)
    return body, css


# ---------------------------------------------------------------- allowed content survives


def test_allowed_markup_is_kept_and_reserialized() -> None:
    body, _ = clean(
        '<h1 id="t" class="a b">Title</h1><p lang="pt-BR" dir="rtl">x <em>y</em> &amp; z</p>'
        "<table><tr><td colspan='2'>c</td></tr></table><br/><hr/>"
    )
    assert body.startswith('<h1 id="t" class="a b">Title</h1>')
    assert '<p lang="pt-BR" dir="rtl">x <em>y</em> &amp; z</p>' in body
    assert '<td colspan="2">c</td>' in body
    assert "<br>" in body and "<hr>" in body


def test_text_is_escaped_never_passed_through() -> None:
    body, _ = clean("<p>&lt;script&gt;alert(1)&lt;/script&gt; 1 < 2 & 3 > 2</p>")
    assert "<script" not in body
    assert "&lt;script&gt;" in body


def test_unclosed_tags_are_closed_in_order() -> None:
    body, _ = clean("<div><p>one<p>two<b>bold")
    assert body == "<div><p>one</p><p>two<b>bold</b></p></div>"


def test_stray_end_tags_are_ignored() -> None:
    body, _ = clean("</div></p><p>ok</span></p>")
    assert body == "<p>ok</p>"


def test_unknown_elements_are_unwrapped_and_their_text_kept() -> None:
    # `o:p` (Word) is judged by its local name `p`; unknown elements keep only their text.
    body, _ = clean("<foo:bar><o:p>word</o:p></foo:bar><center>mid</center>")
    assert body == "<p>word</p>mid"


# ---------------------------------------------------------------- dropped with content


@pytest.mark.parametrize(
    "markup",
    [
        "<script>alert(1)</script>",
        "<SCRIPT SRC=//evil/x.js></SCRIPT>",
        "<iframe src='http://evil'>fallback</iframe>",
        "<object data='x'>fallback</object>",
        "<embed src='x'>",
        "<form action='http://evil'><input name=a><button>go</button></form>",
        "<select><option>a</option></select>",
        "<textarea>text</textarea>",
        "<svg><script>alert(1)</script></svg>",
        "<svg onload=alert(1)><circle/></svg>",
        "<svg><foreignObject><p>x</p></foreignObject></svg>",
        "<math><mi xlink:href='javascript:alert(1)'>x</mi></math>",
        "<template><script>alert(1)</script></template>",
        "<noscript><p>x</p></noscript>",
        "<style>p{color:red}</style>",
        "<audio src=x></audio><video src=x></video>",
        "<title>t</title>",
    ],
)
def test_dangerous_elements_are_removed_with_their_content(markup: str) -> None:
    body, _ = clean(f"<p>before</p>{markup}<p>after</p>")
    text = parse(body).text
    assert "before" in text and "after" in text
    for leaked in ("alert", "fallback", "text", "evil", "go", "foreignObject"):
        assert leaked not in text, leaked


@pytest.mark.parametrize(
    "markup",
    [
        "<link rel=stylesheet href=http://evil/x.css>",
        "<meta http-equiv=refresh content='0;url=http://evil'>",
        "<base href='http://evil/'>",
        "<input type=hidden name=x>",
        "<source src=x><track src=x><param name=a value=b>",
    ],
)
def test_void_dangerous_elements_vanish(markup: str) -> None:
    body, css = clean(f"<p>a</p>{markup}<p>b</p>")
    assert body == "<p>a</p><p>b</p>"
    assert css == ""


def test_self_closing_dangerous_tags_do_not_eat_the_rest_of_the_chapter() -> None:
    body, _ = clean("<p>a</p><script src='x'/><p>b</p><svg/><p>c</p>")
    assert body == "<p>a</p><p>b</p><p>c</p>"


def test_namespace_confusion_is_judged_by_local_name() -> None:
    body, _ = clean(
        "<p>x</p><svg:script>alert(1)</svg:script><p>y</p><x:svg><x:script>1</x:script></x:svg>"
    )
    assert "alert" not in body and "1" not in parse(body).text.replace("x", "")


def test_nested_dropped_elements_need_the_matching_end_tag() -> None:
    body, _ = clean("<svg><svg><circle/></svg><p>still hidden</p></svg><p>visible</p>")
    assert "hidden" not in body and "visible" in body


def test_unclosed_dropped_element_hides_only_the_rest() -> None:
    body, _ = clean("<p>keep</p><script>alert(1)")
    assert body == "<p>keep</p>"


# ---------------------------------------------------------------- mXSS / parser tricks


@pytest.mark.parametrize(
    "markup",
    [
        "<img src=x onerror=alert(1)>",
        "<p onclick='alert(1)'>x</p>",
        '<a href="java&#x73;cript:alert(1)">x</a>',
        '<a href="jav&#x09;ascript:alert(1)">x</a>',
        "<a href=' javascript:alert(1)'>x</a>",
        '<a href="JaVaScRiPt:alert(1)">x</a>',
        "<a href='data:text/html,<script>alert(1)</script>'>x</a>",
        "<a href='vbscript:x'>x</a>",
        "<a href='//evil.example/x'>x</a>",
        "<a href='http://evil.example'>x</a>",
        "<a href='mailto:a@b.c'>x</a>",
        "<img src='http://evil/x.png'>",
        "<img src='data:image/png;base64,AAAA'>",
        "<img src=x srcset='http://evil/a.png 2x' sizes='100vw' loading=lazy>",
        "<p style='background:url(http://evil/x)'>x</p>",
        "<p style='width:expression(alert(1))'>x</p>",
        "<p style='behavior:url(x.htc)'>x</p>",
        "<p style='-moz-binding:url(x)'>x</p>",
        "<p style='@import \"http://evil/x.css\"'>x</p>",
        '<p style="background:u\\72l(http://evil)">x</p>',
        "<!--[if IE]><script>alert(1)</script><![endif]-->",
        "<![if IE]><script>alert(1)</script><![endif]>",
        "<!--><script>alert(1)</script>-->",
        "<![CDATA[<script>alert(1)</script>]]>",
        "<?php echo 1; ?>",
        "<!DOCTYPE html><html><body onload=alert(1)>",
        "<p>\x00<scr\x00ipt>alert(1)</scr\x00ipt></p>",
        "<p>&#0;&#x110000;&#xD800;&#999999999;&#xZZ;</p>",
        "<noscript><p title='</noscript><img src=x onerror=alert(1)>'></noscript>",
        "<math><mtext><table><mglyph><style><!--</style>"
        "<img title='--&gt;&lt;img src=1 onerror=alert(1)&gt;'>",
        "<svg><style><img src=x onerror=alert(1)></style></svg>",
        '<a href="#" onmouseover="alert(1)" style="x:y">x</a>',
        "<img/src=x/onerror=alert(1)>",
        '<p title="" onfocus=alert(1) autofocus tabindex=0>x</p>',
        "<table background='javascript:alert(1)'><tr><td>x</td></tr></table>",
        '<p class="a\\"onmouseover=\\"alert(1)">x</p>',
        "<p id='x\" onmouseover=\"alert(1)'>x</p>",
    ],
)
def test_adversarial_markup_leaves_nothing_executable(markup: str) -> None:
    body, _ = clean(f"<p>keep</p>{markup}")
    assert "keep" in body


def test_external_links_keep_their_text_and_lose_the_link() -> None:
    body, _ = clean('<p><a href="http://evil.example/x">read <b>this</b></a></p>')
    assert body == "<p><a>read <b>this</b></a></p>"


def test_anchors_and_chapter_links_are_rewritten_for_the_reader() -> None:
    body, _ = clean('<a href="#note-1">n</a><a href="ch2.xhtml#p3">c</a><a href="ch2.xhtml">d</a>')
    assert '<a href="#note-1">n</a>' in body
    assert '<a href="?goto=2#p3" data-goto="2">c</a>' in body
    assert '<a href="?goto=2" data-goto="2">d</a>' in body


def test_unsafe_fragments_and_ids_are_dropped() -> None:
    body, _ = clean(
        '<a href="#a b">x</a><a href="#ok_1">y</a><p id="bad id">z</p><p id="a/b">w</p>'
    )
    assert body.count("href=") == 1 and "#ok_1" in body
    assert " id=" not in body


def test_old_style_named_anchors_become_ids() -> None:
    body, _ = clean('<a name="sec1">x</a>')
    assert body == '<a id="sec1">x</a>'


def test_images_only_when_they_are_manifest_images() -> None:
    body, _ = clean(
        '<img src="pic.png" alt="a &amp; b" width="10" height="x" onerror="x">'
        '<img src="other.png"><img src="http://evil/p.png"><img src="pic.png?x=1">'
    )
    assert body == f'<img src="{RES}0" alt="a &amp; b" width="10">'


def test_svg_image_of_the_manifest_becomes_an_img_and_others_vanish() -> None:
    body, _ = clean(
        '<svg xmlns:xlink="x"><image xlink:href="pic.png"/></svg>'
        '<svg><image href="http://evil/x.png"/></svg><svg><image xlink:href="other.svg"/></svg>'
    )
    assert body == f'<img src="{RES}0" alt="">'


def test_duplicate_attributes_first_wins() -> None:
    body, _ = clean('<p id="a" id="b" class="x" class="y">z</p>')
    assert body == '<p id="a" class="x">z</p>'


def test_class_tokens_are_checked_one_by_one() -> None:
    body, _ = clean('<p class="ok bad&quot;x a.b c:d e/f">z</p>')
    assert 'class="ok a.b c:d"' in body


def test_attributes_of_other_tags_are_not_borrowed() -> None:
    body, _ = clean('<p colspan="2" alt="x" width="3" href="#a">z</p>')
    assert body == "<p>z</p>"


def test_invalid_numeric_attributes_are_dropped() -> None:
    body, _ = clean(
        '<table><tr><td colspan="-1" rowspan="99999">a</td><td colspan="3">b</td></tr></table>'
    )
    assert body.count("colspan") == 1 and 'colspan="3"' in body and "rowspan" not in body


def test_dir_and_lang_are_closed_sets() -> None:
    body, _ = clean('<p dir="sideways" lang="x y">a</p><p dir="RTL" xml:lang="fr">b</p>')
    assert "<p>a</p>" in body and '<p dir="rtl" lang="fr">b</p>' in body


def test_giant_attributes_are_dropped_not_truncated() -> None:
    body, _ = clean(f'<p title="{"a" * 5000}" id="ok">x</p><a href="{"b" * 5000}">y</a>')
    assert body == '<p id="ok">x</p><a>y</a>'


# ---------------------------------------------------------------- limits


def test_deep_nesting_is_refused_without_recursion() -> None:
    with pytest.raises(ArchiveLimitExceeded):
        sanitize_chapter("<div>" * 101 + "x", context())
    sanitize_chapter("<div>" * 100 + "x", context())  # exactly at the limit is fine


def test_a_million_unclosed_tags_do_not_blow_the_stack() -> None:
    with pytest.raises(ArchiveLimitExceeded):
        sanitize_chapter("<b>" * 1_000_000, context())


def test_many_end_tags_stay_fast() -> None:
    body, _ = sanitize_chapter("<div>" + "</i>" * 300_000 + "x</div>", context())
    assert body == "<div>x</div>"


def test_output_size_is_capped() -> None:
    src = '<img src="pic.png">' * 300_000
    with pytest.raises(ArchiveLimitExceeded):
        sanitize_chapter(src, context())


def test_optional_end_tags_do_not_count_as_depth() -> None:
    body, _ = sanitize_chapter("<p>a" * 5000, context())
    assert body.count("<p>") == 5000


def test_control_characters_never_reach_the_output() -> None:
    body, _ = clean("<p>a\x01b\x7fc\x85d￾e\x00f</p>")
    assert body == "<p>abcdef</p>"


# ---------------------------------------------------------------- stylesheets


def test_style_and_link_css_are_rebuilt_from_the_allowlist() -> None:
    sheets = {"s.css": "p { color: #ff0000; position: fixed; background: url(http://evil/x); }"}
    body, css = clean(
        '<link rel="stylesheet" href="s.css"/><style>h1 { font-weight: bold; }</style><p>x</p>',
        context(sheets=sheets),
    )
    assert "color:#ff0000" in css and "font-weight:bold" in css
    assert "position" not in css and "url" not in css and "evil" not in css
    assert "<style" not in body and "<link" not in body


def test_unreadable_or_unknown_stylesheets_are_ignored() -> None:
    body, css = clean(
        '<link rel="stylesheet" href="http://evil/x.css"><link rel="icon" href="s.css"><p>x</p>'
    )
    assert css == "" and body == "<p>x</p>"


def test_style_attribute_is_reduced_not_copied() -> None:
    body, _ = clean('<p style="color:red; position:fixed; margin:1em">x</p>')
    assert body == '<p style="color:red;margin:1em">x</p>'
    body, _ = clean('<p style="position:fixed">x</p>')
    assert body == "<p>x</p>"


def test_an_unclosed_style_still_counts() -> None:
    _, css = clean("<style>p{color:red}")
    assert css == "p{color:red}"


# ---------------------------------------------------------------- whole document


def test_document_has_server_theme_last_and_no_query_text() -> None:
    body, css = clean("<p>x</p>")
    doc = build_document(body, css, "en", "dark", 120)
    assert doc.startswith('<!DOCTYPE html><html lang="en">')
    assert doc.count("<style>") == 2 and doc.index("font-size:120%") > doc.index("<style>")
    assert "<script" not in doc.lower()
    found = parse(doc)
    assert set(found.tags) <= ALLOWED_TAGS | {"html", "head", "meta", "style", "body"}


@pytest.mark.parametrize("theme", ["auto", "light", "dark", "sepia"])
def test_every_theme_builds(theme: str) -> None:
    doc = build_document("<p>x</p>", "", None, theme, 100)
    assert "html,body{background:" in doc
    assert ("prefers-color-scheme" in doc) is (theme == "auto")


@pytest.mark.parametrize(
    ("theme", "size"),
    [("neon", 100), ("dark", 79), ("dark", 201), ("</style><script>", 100), ("dark", True)],
)
def test_theme_and_size_are_validated_again_at_build_time(theme: str, size: int) -> None:
    with pytest.raises(ValueError):
        build_document("", "", None, theme, size)


def test_language_with_markup_is_not_written() -> None:
    doc = build_document("", "", 'en"><script>', "auto", 100)
    assert "<script" not in doc and "lang=" not in doc


def test_no_external_reference_anywhere_in_the_output() -> None:
    body, css = clean(
        '<p style="background:url(http://e/x)"><img src="http://e/a.png"><a href="https://e/">x</a></p>'
    )
    doc = build_document(body, css, "en", "auto", 100)
    assert not re.search(r"https?:|//[a-z]", doc)
