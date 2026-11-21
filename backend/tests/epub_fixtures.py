"""Builders of EPUB test files (generated in code; no real book, no real content)."""

import io
import random
import stat
import zipfile
from collections.abc import Mapping
from xml.sax.saxutils import escape, quoteattr

from fakes import png

CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
    '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles></container>"
)
MIMETYPE = b"application/epub+zip"
OPF = "OEBPS/content.opf"

DEFAULT_CHAPTERS: list[tuple[str, str]] = [
    ("First", "<p>Hello <b>world</b></p>"),
    ("Second", "<p>Second chapter</p>"),
    ("Third", "<p>Third chapter</p>"),
]


def xhtml(body: str, head: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title>'
        f"{head}</head><body>{body}</body></html>"
    )


def epub_members(
    *,
    chapters: list[tuple[str, str]] | None = None,
    version: int = 3,
    title: str | None = "Sample Book",
    authors: tuple[str, ...] = ("Ann Author",),
    language: str | None = "en",
    cover: str | None = None,  # "meta" | "property" | "guide" | "guide-page"
    images: Mapping[str, bytes] | None = None,
    css: Mapping[str, str] | None = None,
    toc: bool = True,
    linear_no: tuple[int, ...] = (),
) -> dict[str, bytes]:
    """Members of a small valid EPUB. Chapters live in OEBPS/text/chN.xhtml, images in
    OEBPS/images/, stylesheets in OEBPS/styles/."""
    chapters = DEFAULT_CHAPTERS if chapters is None else chapters
    images = dict(images or {})
    css = dict(css or {})
    if cover is not None:
        images.setdefault("cover.png", png(1))
    members: dict[str, bytes] = {
        "mimetype": MIMETYPE,
        "META-INF/container.xml": CONTAINER.encode(),
    }
    manifest: list[str] = []
    spine: list[str] = []
    for n, (_t, body) in enumerate(chapters):
        members[f"OEBPS/text/ch{n}.xhtml"] = xhtml(body).encode()
        manifest.append(
            f'<item id="ch{n}" href="text/ch{n}.xhtml" media-type="application/xhtml+xml"/>'
        )
        linear = ' linear="no"' if n in linear_no else ""
        spine.append(f'<itemref idref="ch{n}"{linear}/>')
    for name, data in images.items():
        members[f"OEBPS/images/{name}"] = data
        ext = name.rsplit(".", 1)[-1]
        media = {"png": "image/png", "jpg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, "x/y")
        props = ' properties="cover-image"' if cover == "property" and name == "cover.png" else ""
        manifest.append(f'<item id="img-{name}" href="images/{name}" media-type="{media}"{props}/>')
    for name, text in css.items():
        members[f"OEBPS/styles/{name}"] = text.encode()
        manifest.append(f'<item id="css-{name}" href="styles/{name}" media-type="text/css"/>')
    spine_attr = ""
    if toc and version == 3:
        links = "".join(
            f'<li><a href="text/ch{n}.xhtml">{escape(t)}</a></li>'
            for n, (t, _b) in enumerate(chapters)
        )
        members["OEBPS/nav.xhtml"] = (
            '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>n</title></head><body>'
            f'<nav epub:type="toc"><ol>{links}</ol></nav></body></html>'
        ).encode()
        manifest.append(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        )
    if toc and version == 2:
        points = "".join(
            f'<navPoint id="p{n}" playOrder="{n + 1}"><navLabel><text>{escape(t)}</text></navLabel>'
            f'<content src="text/ch{n}.xhtml"/></navPoint>'
            for n, (t, _b) in enumerate(chapters)
        )
        members["OEBPS/toc.ncx"] = (
            '<?xml version="1.0"?>'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            f"<navMap>{points}</navMap></ncx>"
        ).encode()
        manifest.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
        spine_attr = ' toc="ncx"'
    meta = ""
    if title is not None:
        meta += f"<dc:title>{escape(title)}</dc:title>"
    for author in authors:
        meta += f"<dc:creator>{escape(author)}</dc:creator>"
    if language is not None:
        meta += f"<dc:language>{escape(language)}</dc:language>"
    guide = ""
    if cover == "meta":
        meta += '<meta name="cover" content="img-cover.png"/>'
    if cover == "guide":
        guide = '<guide><reference type="cover" title="Cover" href="images/cover.png"/></guide>'
    if cover == "guide-page":
        members["OEBPS/text/cover.xhtml"] = xhtml(
            '<img src="../images/cover.png" alt=""/>'
        ).encode()
        manifest.append(
            '<item id="coverpage" href="text/cover.xhtml" media-type="application/xhtml+xml"/>'
        )
        spine.insert(0, '<itemref idref="coverpage"/>')
        guide = '<guide><reference type="cover" href="text/cover.xhtml"/></guide>'
    members[OPF] = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<package xmlns="http://www.idpf.org/2007/opf" version="{version}.0" '
        'unique-identifier="id">'
        f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">{meta}</metadata>'
        f"<manifest>{''.join(manifest)}</manifest>"
        f"<spine{spine_attr}>{''.join(spine)}</spine>{guide}</package>"
    ).encode()
    return members


def zip_bytes(
    members: Mapping[str, bytes],
    *,
    stored: bool = False,
    symlinks: tuple[str, ...] = (),
) -> bytes:
    """Zip the members ("mimetype" first, stored). `symlinks` are extra entries flagged as UNIX
    symbolic links."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            method = zipfile.ZIP_STORED if name == "mimetype" else None
            info = zipfile.ZipInfo(name)
            info.compress_type = method if method is not None else zf.compression
            zf.writestr(info, data)
        for name in symlinks:
            link = zipfile.ZipInfo(name)
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(link, "/etc/passwd")
    return buf.getvalue()


def noise(seed: int, size: int) -> bytes:
    """Deterministic incompressible bytes (a member that stays big inside the zip)."""
    return random.Random(seed).randbytes(size)  # noqa: S311 - test data, not a secret


def make_epub(**kwargs: object) -> bytes:
    return zip_bytes(epub_members(**kwargs))  # type: ignore[arg-type]


def quote(value: str) -> str:
    return quoteattr(value)
