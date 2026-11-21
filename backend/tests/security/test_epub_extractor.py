"""EPUB extractor/reader against well-formed and hostile files (generated in code)."""

import os
import unicodedata
import warnings
from pathlib import Path

import pytest
from app.adapters.extractors.epub import EpubExtractor
from app.domain.errors import (
    ArchiveLimitExceeded,
    CorruptArchive,
    PageOutOfRange,
    UnsafePath,
    UnsupportedFormat,
)
from app.domain.item import ItemType
from app.domain.library import ExtractorLimits
from app.ports.storage import StorageEntry

from epub_fixtures import CONTAINER, OPF, epub_members, make_epub, noise, xhtml, zip_bytes
from fakes import FakeStorage, png

BOOK = "b.epub"
PNG = png(1)


def extractor(
    data: bytes, limits: ExtractorLimits | None = None, name: str = BOOK
) -> EpubExtractor:
    return EpubExtractor(FakeStorage({name: data}), limits or ExtractorLimits())


def read(ext: EpubExtractor, index: int = 0, theme: str = "auto", size: int = 100) -> str:
    return ext.read_chapter(
        BOOK, index, theme=theme, size=size, resource_url=lambda rid: f"/res/{rid}"
    )


def entry(rel: str, *, is_dir: bool = False) -> StorageEntry:
    return StorageEntry(rel, is_dir, 10, 1)


# ---------------------------------------------------------------- happy paths


def test_epub3_with_nav() -> None:
    ext = extractor(make_epub())
    meta = ext.inspect(BOOK)
    assert (meta.page_count, meta.title, meta.authors) == (3, "Sample Book", ("Ann Author",))
    assert ext.format == "epub" and ext.item_type is ItemType.BOOK
    book = ext.read_book(BOOK)
    assert [c.title for c in book.chapters] == ["First", "Second", "Third"]
    assert [(t.title, t.index, t.anchor) for t in book.toc] == [
        ("First", 0, None),
        ("Second", 1, None),
        ("Third", 2, None),
    ]
    assert book.language == "en" and book.has_cover is False


def test_epub2_with_ncx() -> None:
    ext = extractor(make_epub(version=2))
    book = ext.read_book(BOOK)
    assert [c.title for c in book.chapters] == ["First", "Second", "Third"]
    assert len(book.toc) == 3


def test_without_toc_chapters_are_numbered() -> None:
    book = extractor(make_epub(toc=False)).read_book(BOOK)
    assert [c.title for c in book.chapters] == ["Capitulo 1", "Capitulo 2", "Capitulo 3"]
    assert book.toc == ()


def test_toc_with_anchors_and_partial_coverage() -> None:
    members = epub_members()
    members["OEBPS/nav.xhtml"] = (
        b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        b'<body><nav epub:type="landmarks"><a href="text/ch2.xhtml">Landmark</a></nav>'
        b'<nav epub:type="toc"><ol><li><a href="text/ch1.xhtml#s2">Part <i>two</i></a></li>'
        b'<li><a href="text/ch1.xhtml">Chapter two</a><ol><li><a href="text/ch0.xhtml">One</a></li>'
        b'<li><a href="http://evil.example/">Ext</a></li><li><a href="../../x.xhtml">Esc</a></li>'
        b'<li><a href="text/ghost.xhtml">Ghost</a></li></ol></li></ol></nav></body></html>'
    )
    book = extractor(zip_bytes(members)).read_book(BOOK)
    assert [(t.title, t.index, t.anchor) for t in book.toc] == [
        ("Part two", 1, "s2"),
        ("Chapter two", 1, None),
        ("One", 0, None),
    ]
    # the chapter's own entry beats the section inside it; unlisted chapters are numbered
    assert [c.title for c in book.chapters] == ["One", "Chapter two", "Capitulo 3"]


def test_broken_toc_does_not_make_the_book_unreadable() -> None:
    members = epub_members()
    members["OEBPS/nav.xhtml"] = b"<html><nav>&nbsp;<a href='x'>"  # not well-formed XML
    ext = extractor(zip_bytes(members))
    assert ext.inspect(BOOK).page_count == 3
    assert ext.read_book(BOOK).toc == ()


def test_spine_order_is_the_opf_order_and_linear_no_is_included() -> None:
    members = epub_members(linear_no=(1,))
    members[OPF] = (
        members[OPF]
        .replace(b'<itemref idref="ch0"/>', b"@@0")
        .replace(b'<itemref idref="ch2"/>', b'<itemref idref="ch0"/>')
        .replace(b"@@0", b'<itemref idref="ch2"/>')
    )
    ext = extractor(zip_bytes(members))
    assert ext.inspect(BOOK).page_count == 3
    assert "Third chapter" in read(ext, 0) and "Hello" in read(ext, 2)
    assert "Second chapter" in read(ext, 1)  # linear="no" is a normal chapter


def test_only_html_items_of_the_spine_count() -> None:
    members = epub_members()
    members[OPF] = members[OPF].replace(
        b"</spine>", b'<itemref idref="nav-missing"/><itemref idref="img-x"/></spine>'
    )
    assert extractor(zip_bytes(members)).inspect(BOOK).page_count == 3


@pytest.mark.parametrize("how", ["meta", "property", "guide", "guide-page"])
def test_cover_by_each_of_the_three_paths(how: str) -> None:
    ext = extractor(make_epub(cover=how))
    assert ext.read_book(BOOK).has_cover is True
    page = ext.read_cover(BOOK)
    assert page.media_type == "image/png" and page.data == PNG


def test_no_cover_is_page_out_of_range() -> None:
    ext = extractor(make_epub())
    with pytest.raises(PageOutOfRange):
        ext.read_cover(BOOK)


def test_a_cover_that_is_not_an_image_is_no_cover() -> None:
    ext = extractor(make_epub(cover="property", images={"cover.png": b"<html>not an image</html>"}))
    assert ext.read_book(BOOK).has_cover is False
    with pytest.raises(PageOutOfRange):
        ext.read_cover(BOOK)


def test_pages_do_not_exist_for_books() -> None:
    with pytest.raises(PageOutOfRange):
        extractor(make_epub()).read_page(BOOK, 0)


# ---------------------------------------------------------------- titles and text encoding


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>Title",
        "Evil\u202e title\u200b\u2066x\u2069\ufeff\u00ad",
        "A" * 5000,
        "   \n\t  ",
        "<b onmouseover=x>bold</b> & more",
        "&#x1;&lt;img src=x onerror=alert(1)&gt;",
    ],
)
def test_hostile_titles_and_authors_are_sanitized(hostile: str) -> None:
    members = epub_members(title="placeholder", authors=("placeholder",))
    # XML-escape the text so the OPF stays well-formed: the hostility is in the characters.
    escaped = hostile.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    members[OPF] = members[OPF].replace(b"placeholder", escaped.encode())
    book = extractor(zip_bytes(members)).read_book(BOOK)
    for text in (book.title, *book.authors):
        assert "<" not in text and ">" not in text
        assert all(ord(c) >= 32 and unicodedata.category(c)[0] != "C" for c in text)
        assert len(text) <= 200


def test_missing_title_falls_back_for_the_scan() -> None:
    ext = extractor(make_epub(title=None))
    assert ext.inspect(BOOK).title is None  # the scan then uses the file name
    assert ext.read_book(BOOK).title == "Untitled"


def test_many_authors_are_capped_and_deduplicated() -> None:
    authors = tuple(f"Author {i % 40}" for i in range(200))
    meta = extractor(make_epub(authors=authors)).inspect(BOOK)
    assert len(meta.authors) == 20 and len(set(meta.authors)) == 20


def test_language_is_validated() -> None:
    assert extractor(make_epub(language="pt-BR")).read_book(BOOK).language == "pt-BR"
    assert extractor(make_epub(language='en"><x')).read_book(BOOK).language is None


def test_chapter_encodings() -> None:
    members = epub_members()
    members["OEBPS/text/ch0.xhtml"] = (
        '<?xml version="1.0" encoding="ISO-8859-1"?><html><body><p>a\xe7\xe3o</p></body></html>'
    ).encode("latin-1")
    members["OEBPS/text/ch1.xhtml"] = "<html><body><p>ação 日本</p></body></html>".encode("utf-16")
    members["OEBPS/text/ch2.xhtml"] = "\ufeff<html><body><p>ação</p></body></html>".encode()
    ext = extractor(zip_bytes(members))
    assert "ação" in read(ext, 0)
    assert "ação 日本" in read(ext, 1)
    assert "ação" in read(ext, 2)


# ---------------------------------------------------------------- chapters and resources


def test_chapter_is_a_sanitized_full_document() -> None:
    members = epub_members(
        chapters=[
            (
                "One",
                '<p onclick="x()">Hi <a href="http://evil/">e</a> <a href="ch1.xhtml#a">n</a></p>'
                '<script>alert(1)</script><img src="../images/p.png" alt="p"/>'
                '<img src="../images/p.svg"/>',
            ),
            ("Two", "<p id='a'>two</p>"),
        ],
        images={"p.png": PNG, "p.svg": b"<svg onload='alert(1)'/>"},
        css={"s.css": "p{color:#123;background:url(http://evil/x)}"},
    )
    members["OEBPS/text/ch0.xhtml"] = xhtml(
        '<p onclick="x()">Hi <a href="http://evil/">e</a> <a href="ch1.xhtml#a">n</a></p>'
        '<script>alert(1)</script><img src="../images/p.png" alt="p"/><img src="../images/p.svg"/>',
        head='<link rel="stylesheet" href="../styles/s.css"/>',
    ).encode()
    ext = extractor(zip_bytes(members))
    doc = read(ext, 0, theme="sepia", size=130)
    assert doc.startswith("<!DOCTYPE html>") and doc.endswith("</body></html>")
    assert "alert" not in doc and "onclick" not in doc and "evil" not in doc and "svg" not in doc
    assert '<a href="?goto=1#a" data-goto="1">n</a>' in doc
    assert '<img src="/res/' in doc and doc.count("<img") == 1
    assert "color:#123" in doc and "font-size:130%" in doc
    assert "<script" not in doc


def test_resources_by_opaque_rid_with_magic_bytes() -> None:
    members = epub_members(
        chapters=[("One", "<p>x</p>")],
        images={"a.png": PNG, "b.jpg": b"\xff\xd8\xffjpegdata", "c.png": b"<html>fake</html>"},
    )
    ext = extractor(zip_bytes(members))
    assert ext.read_resource(BOOK, 0).media_type == "image/png"
    assert ext.read_resource(BOOK, 1).media_type == "image/jpeg"
    with pytest.raises(PageOutOfRange):  # declared png, bytes are html: never served
        ext.read_resource(BOOK, 2)


@pytest.mark.parametrize("rid", [-1, 3, 10**9, True])
def test_rid_outside_the_manifest_images(rid: int) -> None:
    ext = extractor(make_epub(images={"a.png": PNG, "b.png": PNG, "c.png": PNG}))
    with pytest.raises(PageOutOfRange):
        ext.read_resource(BOOK, rid)


def test_svg_and_fonts_are_not_resources() -> None:
    members = epub_members(images={"v.svg": b"<svg/>", "a.png": PNG})
    members["OEBPS/f.otf"] = b"OTTO"
    members[OPF] = members[OPF].replace(
        b"</manifest>", b'<item id="f" href="f.otf" media-type="font/otf"/></manifest>'
    )
    ext = extractor(zip_bytes(members))
    assert ext.read_resource(BOOK, 0).data == PNG
    with pytest.raises(PageOutOfRange):
        ext.read_resource(BOOK, 1)


@pytest.mark.parametrize("index", [-1, 3, 99999, True])
def test_chapter_index_outside_the_spine(index: int) -> None:
    with pytest.raises(PageOutOfRange):
        read(extractor(make_epub()), index)


# ---------------------------------------------------------------- detection


def test_can_handle_needs_extension_and_zip_signature() -> None:
    ext = EpubExtractor(
        FakeStorage(
            {"a.epub": make_epub(), "B.EPUB": make_epub(), "t.epub": b"text", "x.zip": make_epub()}
        ),
        ExtractorLimits(),
    )
    assert ext.can_handle(entry("a.epub")) and ext.can_handle(entry("B.EPUB"))
    assert not ext.can_handle(entry("t.epub"))
    assert not ext.can_handle(entry("x.zip"))
    assert not ext.can_handle(entry("a.epub", is_dir=True))


def test_can_handle_never_raises_for_an_unreadable_file(tmp_path: Path) -> None:
    from app.adapters.storage.local import LocalStorage

    (tmp_path / "lib").mkdir()
    ext = EpubExtractor(LocalStorage(tmp_path / "lib"), ExtractorLimits())
    assert ext.can_handle(entry("ghost.epub")) is False
    assert ext.can_handle(entry("../escape.epub")) is False


# ---------------------------------------------------------------- zip attacks


@pytest.mark.parametrize("name", ["../evil.txt", "a/../../evil", "/abs/evil", "C:/evil", "x/../y"])
def test_zip_slip_member_names_are_refused(name: str) -> None:
    members = epub_members()
    members[name] = b"x"
    with pytest.raises(UnsafePath):
        extractor(zip_bytes(members)).inspect(BOOK)


@pytest.mark.skipif(os.sep != "/", reason="zipfile turns `\\` into `/` on Windows (no escape)")
def test_backslash_member_name_is_refused() -> None:
    # Patch the raw bytes (same length): zipfile itself would refuse to write the name here.
    members = epub_members()
    members["OEBPS/a_b.txt"] = b"x"
    raw = zip_bytes(members).replace(b"OEBPS/a_b.txt", b"OEBPS/a\\b.txt")
    with pytest.raises(UnsafePath):
        extractor(raw).inspect(BOOK)


def test_symlink_member_is_refused() -> None:
    with pytest.raises(UnsafePath):
        extractor(zip_bytes(epub_members(), symlinks=("OEBPS/link",))).inspect(BOOK)


def test_duplicate_member_names_are_refused() -> None:
    members = epub_members()
    data = zip_bytes(members)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import io
        import zipfile

        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf, "a") as zf:
            zf.writestr("META-INF/container.xml", CONTAINER)
    with pytest.raises(CorruptArchive):
        extractor(buf.getvalue()).inspect(BOOK)


def test_hrefs_that_escape_the_root_are_never_resolved() -> None:
    members = epub_members(images={"a.png": PNG})
    members["secret.png"] = PNG
    members[OPF] = members[OPF].replace(
        b"</manifest>",
        b'<item id="e1" href="../../secret.png" media-type="image/png"/>'
        b'<item id="e2" href="/secret.png" media-type="image/png"/>'
        b'<item id="e3" href="..%2F..%2Fsecret.png" media-type="image/png"/>'
        b'<item id="e4" href="http://evil.example/x.png" media-type="image/png"/>'
        b'<item id="e5" href="..\\secret.png" media-type="image/png"/>'
        b'<item id="e6" href="a%252e%252e/x" media-type="image/png"/></manifest>',
    )
    ext = extractor(zip_bytes(members))
    assert ext.inspect(BOOK).page_count == 3
    ext.read_resource(BOOK, 0)  # only the legitimate image exists
    with pytest.raises(PageOutOfRange):
        ext.read_resource(BOOK, 1)


def test_a_spine_that_only_points_outside_is_empty() -> None:
    members = epub_members(chapters=[("x", "<p>x</p>")])
    members[OPF] = members[OPF].replace(b'href="text/ch0.xhtml"', b'href="../../ch0.xhtml"')
    with pytest.raises(UnsupportedFormat):
        extractor(zip_bytes(members)).inspect(BOOK)


def test_container_that_points_outside_the_root() -> None:
    members = epub_members()
    members["META-INF/container.xml"] = CONTAINER.replace("OEBPS/content.opf", "../x.opf").encode()
    with pytest.raises(UnsafePath):
        extractor(zip_bytes(members)).inspect(BOOK)


def test_zip_bomb_by_ratio_is_refused() -> None:
    members = epub_members()
    members["OEBPS/bomb.bin"] = b"\0" * (50 * 1024 * 1024)
    with pytest.raises(ArchiveLimitExceeded):
        extractor(zip_bytes(members)).inspect(BOOK)


def test_total_size_entries_and_member_limits() -> None:
    data = make_epub()
    with pytest.raises(ArchiveLimitExceeded):
        extractor(data, ExtractorLimits(max_total_uncompressed_bytes=500)).inspect(BOOK)
    with pytest.raises(ArchiveLimitExceeded):
        extractor(data, ExtractorLimits(max_entries=5)).inspect(BOOK)
    with pytest.raises(ArchiveLimitExceeded):
        extractor(data, ExtractorLimits(max_page_bytes=100)).inspect(BOOK)


def test_many_entries_are_refused() -> None:
    members = epub_members()
    for i in range(10_001):
        members[f"OEBPS/f{i}.txt"] = b""
    with pytest.raises(ArchiveLimitExceeded):
        extractor(zip_bytes(members)).inspect(BOOK)


def test_encrypted_member_is_unsupported() -> None:
    data = bytearray(make_epub())
    for sig, off in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        data[data.index(sig) + off] |= 0x1
    with pytest.raises(UnsupportedFormat):
        extractor(bytes(data)).inspect(BOOK)


@pytest.mark.parametrize("junk", [b"not a zip at all", b"", b"PK\x03\x04" + b"\x00" * 10])
def test_corrupt_archives(junk: bytes) -> None:
    with pytest.raises(CorruptArchive):
        extractor(junk).inspect(BOOK)


def test_truncated_archive() -> None:
    data = make_epub()
    with pytest.raises(CorruptArchive):
        extractor(data[: len(data) // 2]).inspect(BOOK)


# ---------------------------------------------------------------- structure errors


def test_mimetype_missing_or_wrong_is_unsupported() -> None:
    members = epub_members()
    del members["mimetype"]
    with pytest.raises(UnsupportedFormat):
        extractor(zip_bytes(members)).inspect(BOOK)
    for wrong in (b"application/zip", b"", b"application/epub+zip" + b"x" * 100):
        members["mimetype"] = wrong
        with pytest.raises(UnsupportedFormat):
            extractor(zip_bytes(members)).inspect(BOOK)


def test_mimetype_with_trailing_newline_is_fine() -> None:
    members = epub_members()
    members["mimetype"] = b"application/epub+zip\n"
    assert extractor(zip_bytes(members)).inspect(BOOK).page_count == 3


def test_missing_container_or_opf() -> None:
    members = epub_members()
    del members["META-INF/container.xml"]
    with pytest.raises(CorruptArchive):
        extractor(zip_bytes(members)).inspect(BOOK)
    members = epub_members()
    del members[OPF]
    with pytest.raises(CorruptArchive):
        extractor(zip_bytes(members)).inspect(BOOK)
    members = epub_members()
    members["META-INF/container.xml"] = b"<container><rootfiles/></container>"
    with pytest.raises(CorruptArchive):
        extractor(zip_bytes(members)).inspect(BOOK)


def test_empty_spine_is_unsupported() -> None:
    members = epub_members()
    members[OPF] = members[OPF].replace(b"ch0", b"zz").replace(b"ch1", b"zz").replace(b"ch2", b"zz")
    members[OPF] = members[OPF].replace(b'idref="zz"', b'idref="nothing"')
    with pytest.raises(UnsupportedFormat):
        extractor(zip_bytes(members)).inspect(BOOK)


def test_opf_with_the_wrong_root_or_no_manifest() -> None:
    members = epub_members()
    members[OPF] = b"<notpackage/>"
    with pytest.raises(CorruptArchive):
        extractor(zip_bytes(members)).inspect(BOOK)
    members[OPF] = b'<package xmlns="http://www.idpf.org/2007/opf"><metadata/></package>'
    with pytest.raises(CorruptArchive):
        extractor(zip_bytes(members)).inspect(BOOK)


# ---------------------------------------------------------------- XML attacks


ENTITY = b'<!DOCTYPE x [<!ENTITY e "boom">]>'
XXE = b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
LAUGHS = (
    b'<!DOCTYPE x [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
    b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
)


@pytest.mark.parametrize("doctype", [ENTITY, XXE, LAUGHS], ids=["entity", "xxe", "billion-laughs"])
@pytest.mark.parametrize("target", ["container", "opf", "encryption"])
def test_xml_entities_are_refused_everywhere(doctype: bytes, target: str) -> None:
    members = epub_members()
    if target == "container":
        members["META-INF/container.xml"] = (
            b'<?xml version="1.0"?>' + doctype + CONTAINER.encode()[21:]
        )
    elif target == "opf":
        members[OPF] = members[OPF].replace(b"?>", b"?>" + doctype, 1)
    else:
        members["META-INF/encryption.xml"] = b"<?xml version='1.0'?>" + doctype + b"<encryption/>"
    with pytest.raises(CorruptArchive):
        extractor(zip_bytes(members)).inspect(BOOK)


def test_entities_in_a_toc_never_expand_and_never_break_the_book() -> None:
    members = epub_members()
    members["OEBPS/nav.xhtml"] = (
        b"<?xml version='1.0'?>"
        + LAUGHS
        + b"<html><nav><a href='text/ch0.xhtml'>&c;</a></nav></html>"
    )
    ext = extractor(zip_bytes(members))
    assert ext.read_book(BOOK).toc == ()  # refused, not expanded


def test_xml_over_two_mib_is_refused() -> None:
    members = epub_members()
    members[OPF] = noise(0, 2 * 1024 * 1024 + 1)
    with pytest.raises(ArchiveLimitExceeded):
        extractor(zip_bytes(members)).inspect(BOOK)


# ---------------------------------------------------------------- DRM


def test_drm_encryption_is_unsupported() -> None:
    members = epub_members()
    members["META-INF/encryption.xml"] = (
        b'<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
        b'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
        b'<enc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>'
        b'<enc:CipherData><enc:CipherReference URI="OEBPS/text/ch0.xhtml"/></enc:CipherData>'
        b"</enc:EncryptedData></encryption>"
    )
    with pytest.raises(UnsupportedFormat):
        extractor(zip_bytes(members)).inspect(BOOK)


def test_adobe_rights_file_is_unsupported() -> None:
    members = epub_members()
    members["META-INF/rights.xml"] = b"<rights/>"
    with pytest.raises(UnsupportedFormat):
        extractor(zip_bytes(members)).inspect(BOOK)


def test_font_obfuscation_is_not_drm_and_fonts_are_ignored() -> None:
    members = epub_members()
    members["OEBPS/f.otf"] = b"obfuscated font"
    members["META-INF/encryption.xml"] = (
        b'<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
        b'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
        b'<enc:EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/>'
        b'<enc:CipherData><enc:CipherReference URI="OEBPS/f.otf"/></enc:CipherData>'
        b"</enc:EncryptedData></encryption>"
    )
    assert extractor(zip_bytes(members)).inspect(BOOK).page_count == 3


def test_an_obfuscated_chapter_is_not_served() -> None:
    members = epub_members()
    members["META-INF/encryption.xml"] = (
        b'<encryption xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
        b'<enc:EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/>'
        b'<enc:CipherData><enc:CipherReference URI="OEBPS/text/ch0.xhtml"/></enc:CipherData>'
        b"</enc:EncryptedData></encryption>"
    )
    ext = extractor(zip_bytes(members))
    with pytest.raises(UnsupportedFormat):
        read(ext, 0)
    assert "Second" in read(ext, 1)


# ---------------------------------------------------------------- limits of our own


def test_chapter_over_two_mib_is_refused() -> None:
    members = epub_members()
    members["OEBPS/text/ch0.xhtml"] = noise(1, 2 * 1024 * 1024 + 1)
    ext = extractor(zip_bytes(members))
    assert ext.inspect(BOOK).page_count == 3
    with pytest.raises(ArchiveLimitExceeded):
        read(ext, 0)


def test_deeply_nested_chapter_is_refused() -> None:
    members = epub_members()
    members["OEBPS/text/ch0.xhtml"] = xhtml("<div>" * 150).encode()
    with pytest.raises(ArchiveLimitExceeded):
        read(extractor(zip_bytes(members)), 0)


def test_image_over_ten_mib_is_refused() -> None:
    members = epub_members(images={"a.png": PNG + noise(2, 10 * 1024 * 1024)})
    with pytest.raises(ArchiveLimitExceeded):
        extractor(zip_bytes(members)).read_resource(BOOK, 0)


def test_manifest_and_spine_item_limits() -> None:
    wide = ExtractorLimits(max_compression_ratio=1_000_000)
    members = epub_members()
    items = b'<item id="i" href="a" media-type="x/y"/>' * 20_001
    members[OPF] = members[OPF].replace(b"</manifest>", items + b"</manifest>")
    with pytest.raises(ArchiveLimitExceeded):
        extractor(zip_bytes(members), wide).inspect(BOOK)
    members = epub_members()
    refs = b'<itemref idref="a"/>' * 100_001
    members[OPF] = members[OPF].replace(b"</spine>", refs + b"</spine>")
    with pytest.raises(ArchiveLimitExceeded):
        extractor(zip_bytes(members), wide).inspect(BOOK)


def test_structure_is_cached_per_file_version() -> None:
    storage = FakeStorage({BOOK: make_epub()})
    ext = EpubExtractor(storage, ExtractorLimits())
    ext.inspect(BOOK)
    assert ext.cached_books == 1
    storage.files[BOOK] = make_epub(chapters=[("Only", "<p>x</p>")])
    storage.mtimes[BOOK] = 2  # a changed file never gets the stale structure
    assert ext.inspect(BOOK).page_count == 1
    assert ext.cached_books == 1
