"""Book routes end to end: authorization, hostile ids and queries, exact headers of the chapter
route (and that no other route gets them), cache, images, covers, no path leaks."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from app.api.security_headers import BOOK_CHAPTER_CSP, CACHE_MARKER_HEADER

from auth_fakes import Env
from epub_fixtures import epub_members, make_epub, xhtml, zip_bytes
from fakes import png
from library_env import add_item, book_env, item_id_by_title, logged_in

GLOBAL_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
    "connect-src 'self'; worker-src 'self'; manifest-src 'self'; font-src 'self'; "
    "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
CHAPTER_CSP = (
    "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'self'; "
    "base-uri 'none'; form-action 'none'"
)
PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=()"
PNG = png(1)
UNKNOWN = "11111111-2222-4333-8444-555555555555"


def library() -> dict[str, bytes]:
    rich = epub_members(
        chapters=[
            (
                "One",
                '<p>Hello <a href="ch1.xhtml#x">next</a> <img src="../images/p.png" alt="p"/></p>',
            ),
            ("Two", '<p id="x">Two</p><script>alert(1)</script>'),
        ],
        images={"p.png": PNG, "v.svg": b"<svg onload='alert(1)'/>"},
        cover="property",
    )
    rich["OEBPS/text/ch0.xhtml"] = xhtml(
        '<p>Hello <a href="ch1.xhtml#x">next</a> <img src="../images/p.png" alt="p"/></p>'
        '<img src="../images/v.svg"/>'
    ).encode()
    return {
        "Saga/Book One.epub": zip_bytes(rich),
        "Plain.epub": make_epub(title="Plain Title"),
        "Broken.epub": b"PK\x03\x04 broken",
        "Text.epub": b"not a zip",
    }


@pytest.fixture
def env(db_url: str, tmp_path: Path) -> Env:
    return book_env(db_url, tmp_path, library())[0]


def book_id(env: Env, title: str = "Sample Book") -> str:
    return item_id_by_title(logged_in(env), title)


# ---------------------------------------------------------------- scan and listing


def test_scan_lists_books_and_survives_broken_files(env: Env) -> None:
    alice = logged_in(env)
    items = alice.get("/api/v1/items?type=book&limit=100").json()["items"]
    assert sorted((i["title"], i["type"], i["page_count"]) for i in items) == [
        ("Plain Title", "book", 3),
        ("Sample Book", "book", 2),
    ]
    assert all("rel_path" not in i and "Saga" not in str(i) for i in items)
    status = env.container.scan_runner.run()
    assert status.state.value == "finished"


def test_second_scan_is_incremental_and_keeps_ids(db_url: str, tmp_path: Path) -> None:
    env, lib = book_env(db_url, tmp_path, library(), scan=False)
    env.container.scan_runner.run()
    first = {i["id"] for i in logged_in(env).get("/api/v1/items?limit=100").json()["items"]}
    env.container.scan_runner.run()
    again = {i["id"] for i in logged_in(env).get("/api/v1/items?limit=100").json()["items"]}
    assert first == again and len(first) == 2


def test_a_text_file_named_epub_is_skipped_and_a_truncated_one_is_an_error(env: Env) -> None:
    status = env.container.scan_runner.run()
    # Broken.epub starts like a zip but is not one: an error. Text.epub is not even handled.
    assert status.errors_by_reason == {"CorruptArchive": 1}
    assert status.skipped == 2 and status.unchanged == 2  # Text.epub and the Saga directory


def test_books_group_by_folder_like_any_item(env: Env) -> None:
    alice = logged_in(env)
    series = alice.get("/api/v1/series?limit=100").json()["items"]
    assert "Saga" in [s["title"] for s in series]
    sid = next(s["id"] for s in series if s["title"] == "Saga")
    chapters = alice.get(f"/api/v1/series/{sid}").json()["chapters"]
    assert [c["title"] for c in chapters] == ["Sample Book"]  # the OPF title, not "Capitulo N"


# ---------------------------------------------------------------- authorization


@pytest.mark.parametrize("suffix", ["/book", "/book/chapters/0", "/book/res/0"])
def test_anonymous_gets_401(env: Env, suffix: str) -> None:
    item = book_id(env)
    anon = env.client()
    assert anon.get(f"/api/v1/items/{item}{suffix}").status_code == 401


def test_two_users_both_read_the_library_but_progress_is_private(env: Env) -> None:
    item = book_id(env)
    alice, bob = logged_in(env, "alice"), logged_in(env, "bob")
    for client in (alice, bob):
        assert client.get(f"/api/v1/items/{item}/book").status_code == 200
        assert client.get(f"/api/v1/items/{item}/book/chapters/0").status_code == 200
    assert alice.put(f"/api/v1/progress/{item}", {"locator": 10_500}).status_code == 200
    assert bob.get(f"/api/v1/progress/{item}").status_code == 404
    assert alice.get(f"/api/v1/progress/{item}").json()["locator"] == 10_500


# ---------------------------------------------------------------- /book


def test_book_info_shape_and_no_paths(env: Env) -> None:
    alice = logged_in(env)
    item = book_id(env)
    response = alice.get(f"/api/v1/items/{item}/book")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"title", "authors", "language", "chapters", "toc", "has_cover"}
    assert body["title"] == "Sample Book" and body["authors"] == ["Ann Author"]
    assert body["language"] == "en" and body["has_cover"] is True
    assert body["chapters"] == [{"index": 0, "title": "One"}, {"index": 1, "title": "Two"}]
    assert body["toc"][0] == {"title": "One", "index": 0, "anchor": None}
    for leaked in ("Saga", "OEBPS", ".epub", "content.opf", "container"):
        assert leaked not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"] == GLOBAL_CSP


@pytest.mark.parametrize(
    "path",
    [
        "not-a-uuid/book",
        f"{UNKNOWN}/book",
        f"{UNKNOWN}/book/chapters/0",
        f"{UNKNOWN}/book/res/0",
        "A" * 36 + "/book",
    ],
)
def test_hostile_or_unknown_ids_are_a_generic_404(env: Env, path: str) -> None:
    response = logged_in(env).get(f"/api/v1/items/{path}")
    assert response.status_code == 404 and response.json() == {"detail": "Not found"}


def test_path_tricks_in_the_id_never_reach_a_file(env: Env) -> None:
    alice = logged_in(env)
    for path in ("../etc/passwd/book", "%2e%2e%2fsecret/book", "..%5Csecret/book/chapters/0"):
        response = alice.get(f"/api/v1/items/{path}")
        assert response.status_code == 404
        assert "passwd" not in response.text and "secret" not in response.text


def test_image_items_have_no_book_routes(db_url: str, tmp_path: Path) -> None:
    env, _ = book_env(db_url, tmp_path, library())
    manga = add_item(env, "A Manga")
    alice = logged_in(env)
    for suffix in ("/book", "/book/chapters/0", "/book/res/0"):
        assert alice.get(f"/api/v1/items/{manga.id}{suffix}").status_code == 404


def test_a_book_has_no_page_images(env: Env) -> None:
    item = book_id(env)
    assert logged_in(env).get(f"/api/v1/items/{item}/pages/0").status_code == 404


# ---------------------------------------------------------------- chapter route


def test_chapter_headers_are_exactly_the_exception(env: Env) -> None:
    item = book_id(env)
    response = logged_in(env).get(f"/api/v1/items/{item}/book/chapters/0?theme=dark&size=120")
    assert response.status_code == 200
    headers = response.headers
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert headers["content-security-policy"] == CHAPTER_CSP
    assert headers["content-security-policy"].encode() == BOOK_CHAPTER_CSP
    assert headers["cache-control"] == "private, max-age=3600"
    assert "pragma" not in headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["permissions-policy"] == PERMISSIONS
    assert "x-frame-options" not in headers
    assert CACHE_MARKER_HEADER not in headers
    assert headers["etag"].startswith('"') and len(headers["etag"]) == 66
    assert headers.get_list("content-security-policy") == [CHAPTER_CSP]
    assert headers.get_list("cache-control") == ["private, max-age=3600"]


def test_chapter_body_is_sanitized_and_themed(env: Env) -> None:
    item = book_id(env)
    alice = logged_in(env)
    doc = alice.get(f"/api/v1/items/{item}/book/chapters/0?theme=sepia&size=140").text
    assert "font-size:140%" in doc and "#f4ecd8" in doc
    assert f"/api/v1/items/{item}/book/res/0" in doc  # the png; the svg image is not written
    assert "svg" not in doc and "alert" not in doc
    assert '<a href="?goto=1#x" data-goto="1">next</a>' in doc
    two = alice.get(f"/api/v1/items/{item}/book/chapters/1").text
    assert "alert" not in two and "<script" not in two


def test_chapter_defaults_and_theme_variants(env: Env) -> None:
    item = book_id(env)
    alice = logged_in(env)
    default = alice.get(f"/api/v1/items/{item}/book/chapters/0")
    assert "prefers-color-scheme" in default.text and "font-size:100%" in default.text
    for theme in ("auto", "light", "dark", "sepia"):
        assert alice.get(f"/api/v1/items/{item}/book/chapters/0?theme={theme}").status_code == 200
    assert alice.get(f"/api/v1/items/{item}/book/chapters/0?size=80").status_code == 200
    assert alice.get(f"/api/v1/items/{item}/book/chapters/0?size=200").status_code == 200


@pytest.mark.parametrize(
    "query",
    [
        "theme=neon",
        "theme=",
        "theme=DARK",
        "theme=dark%0d%0aX-Evil:1",
        "theme=%3C/style%3E%3Cscript%3Ealert(1)%3C/script%3E",
        "theme=dark;color:red",
        "size=79",
        "size=201",
        "size=abc",
        "size=",
        "size=-1",
        "size=100.5",
        "size=1e2",
        "size=99999999999999999999",
        "theme=dark&theme=light&size=abc",
    ],
)
def test_invalid_query_is_a_generic_422_without_echo(env: Env, query: str) -> None:
    item = book_id(env)
    response = logged_in(env).get(f"/api/v1/items/{item}/book/chapters/0?{query}")
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    assert "alert" not in response.text and "neon" not in response.text
    assert response.headers["content-security-policy"] == GLOBAL_CSP  # errors never get the CSP
    assert response.headers["cache-control"] == "no-store"


def test_query_text_never_reaches_the_document(env: Env) -> None:
    item = book_id(env)
    doc = logged_in(env).get(f"/api/v1/items/{item}/book/chapters/0?theme=dark&size=100&x=<b>").text
    assert "<b>" not in doc


@pytest.mark.parametrize("n", ["2", "99", "-1", "abc", "１", "1.5", "0x1", "1234567", " 1", "٣"])
def test_chapter_number_outside_is_a_generic_404(env: Env, n: str) -> None:
    item = book_id(env)
    response = logged_in(env).get(f"/api/v1/items/{item}/book/chapters/{n}")
    assert response.status_code == 404
    assert response.headers["content-security-policy"] == GLOBAL_CSP
    assert response.headers["cache-control"] == "no-store"


def test_chapter_etag_and_304(env: Env) -> None:
    item = book_id(env)
    alice = logged_in(env)
    url = f"/api/v1/items/{item}/book/chapters/1?theme=light&size=110"
    first = alice.get(url)
    etag = first.headers["etag"]
    assert alice.get(url).headers["etag"] == etag  # stable
    assert alice.get(url.replace("light", "dark")).headers["etag"] != etag  # depends on options
    again = alice.http.get(url, headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""
    assert again.headers["cache-control"] == "private, max-age=3600"
    assert again.headers["etag"] == etag
    stale = alice.http.get(url, headers={"If-None-Match": '"nope"'})
    assert stale.status_code == 200


def test_other_routes_keep_the_global_csp_and_no_store(env: Env) -> None:
    item = book_id(env)
    alice = logged_in(env)
    for path in (
        f"/api/v1/items/{item}",
        f"/api/v1/items/{item}/book",
        "/api/v1/items",
        "/api/v1/auth/me",
        "/api/v1/me/preferences",
        f"/api/v1/items/{item}/book/chapters/9",
    ):
        response = alice.get(path)
        assert response.headers["content-security-policy"] == GLOBAL_CSP, path
        assert response.headers["cache-control"] == "no-store", path
    assert "frame-ancestors 'none'" in GLOBAL_CSP


# ---------------------------------------------------------------- resources and covers


def test_resource_by_rid_is_an_image_with_private_cache(env: Env) -> None:
    item = book_id(env)
    alice = logged_in(env)
    response = alice.get(f"/api/v1/items/{item}/book/res/0")
    assert response.status_code == 200 and response.content == PNG
    headers = response.headers
    assert headers["content-type"] == "image/png"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["content-disposition"] == "inline"
    assert headers["cache-control"] == "private, max-age=3600"
    assert headers["content-security-policy"] == GLOBAL_CSP
    assert CACHE_MARKER_HEADER not in headers
    cached = alice.http.get(
        f"/api/v1/items/{item}/book/res/0", headers={"If-None-Match": headers["etag"]}
    )
    assert cached.status_code == 304


@pytest.mark.parametrize("rid", ["2", "3", "99", "-1", "abc", "1234567", "0.5", "1%2F"])
def test_resource_ids_outside_the_manifest_are_404(env: Env, rid: str) -> None:
    """The manifest has two images (png and cover) and an svg that gets no rid at all."""
    item = book_id(env)
    response = logged_in(env).get(f"/api/v1/items/{item}/book/res/{rid}")
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"


def test_an_svg_is_never_served_whatever_its_path(env: Env) -> None:
    item = book_id(env)
    alice = logged_in(env)
    for rid in range(0, 6):
        response = alice.get(f"/api/v1/items/{item}/book/res/{rid}")
        assert b"svg" not in response.content and b"alert" not in response.content


def test_cover_routes_use_the_epub_cover(env: Env) -> None:
    alice = logged_in(env)
    item = book_id(env)
    cover = alice.get(f"/api/v1/items/{item}/cover")
    assert cover.status_code == 200 and cover.content == PNG
    assert cover.headers["cache-control"] == "private, max-age=3600"
    series = next(
        s["id"]
        for s in alice.get("/api/v1/series?limit=100").json()["items"]
        if s["title"] == "Saga"
    )
    assert alice.get(f"/api/v1/series/{series}/cover").content == PNG


def test_a_book_without_cover_is_a_404_cover(env: Env) -> None:
    item = book_id(env, "Plain Title")
    alice = logged_in(env)
    assert alice.get(f"/api/v1/items/{item}/book").json()["has_cover"] is False
    assert alice.get(f"/api/v1/items/{item}/cover").status_code == 404


# ---------------------------------------------------------------- errors never leak


def test_broken_book_after_scan_is_a_generic_422_without_paths(db_url: str, tmp_path: Path) -> None:
    env, lib = book_env(db_url, tmp_path, {"Secret/My Book.epub": make_epub()})
    item = book_id(env)
    (lib / "Secret" / "My Book.epub").write_bytes(b"PK\x03\x04 truncated")
    alice = logged_in(env)
    for suffix in ("/book", "/book/chapters/0", "/book/res/0"):
        response = alice.get(f"/api/v1/items/{item}{suffix}")
        assert response.status_code == 422
        assert response.json() == {"detail": "Item cannot be read"}
        assert "Secret" not in response.text and "epub" not in response.text.lower()


def test_book_deleted_from_disk_is_a_generic_error(db_url: str, tmp_path: Path) -> None:
    env, lib = book_env(db_url, tmp_path, {"Secret/My Book.epub": make_epub()})
    item = book_id(env)
    (lib / "Secret" / "My Book.epub").unlink()
    response = logged_in(env).get(f"/api/v1/items/{item}/book/chapters/0")
    assert response.status_code in (404, 503)
    assert "Secret" not in response.text


def test_output_of_every_chapter_parses_without_active_content(env: Env) -> None:
    class Tags(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.tags: set[str] = set()

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            self.tags.add(tag)
            assert not any(k.startswith("on") for k, _ in attrs)

    item = book_id(env)
    alice = logged_in(env)
    for n in (0, 1):
        parser = Tags()
        parser.feed(alice.get(f"/api/v1/items/{item}/book/chapters/{n}").text)
        assert not parser.tags & {"script", "iframe", "object", "embed", "form", "svg", "base"}
    assert re.search(r"https?://", alice.get(f"/api/v1/items/{item}/book/chapters/0").text) is None
