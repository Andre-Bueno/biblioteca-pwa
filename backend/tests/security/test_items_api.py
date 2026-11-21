"""Authorization, input hostility, error hygiene and image headers of the catalog routes."""

import shutil
import uuid
from pathlib import Path

import pytest
from app.domain.errors import ArchiveLimitExceeded, CorruptArchive, UnsafePath
from app.domain.item import ItemType
from app.domain.library import Page
from fastapi.testclient import TestClient

from auth_fakes import Env
from fakes import make_cbz, png
from library_env import add_item, item_id_by_title, library_env, logged_in

UNKNOWN = "11111111-2222-4333-8444-555555555555"
PRIVATE_CACHE = "private, max-age=3600"


@pytest.fixture
def lib_env(db_url: str, tmp_path: Path) -> tuple[Env, Path]:
    return library_env(db_url, tmp_path)


# ---------------------------------------------------------------- authorization


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/items"),
        ("GET", f"/api/v1/items/{UNKNOWN}"),
        ("GET", f"/api/v1/items/{UNKNOWN}/pages/0"),
        ("GET", f"/api/v1/items/{UNKNOWN}/cover"),
        ("GET", "/api/v1/library/scan/status"),
        ("POST", "/api/v1/library/scan"),
    ],
)
def test_anonymous_gets_401_everywhere(lib_env: tuple[Env, Path], method: str, path: str) -> None:
    env, _ = lib_env
    client = env.client()
    response = client.get(path) if method == "GET" else client.post(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert "rel_path" not in response.text


def test_anonymous_cannot_read_a_real_page(lib_env: tuple[Env, Path]) -> None:
    env, _ = lib_env
    item = env.container.item_repository.get_by_rel_path("Vol 1.cbz")
    assert item is not None
    assert env.client().get(f"/api/v1/items/{item.id}/pages/0").status_code == 401
    assert env.client().get(f"/api/v1/items/{item.id}/cover").status_code == 401


def test_garbage_cookie_is_not_authentication(lib_env: tuple[Env, Path]) -> None:
    env, _ = lib_env
    response = env.client().get("/api/v1/items", cookies={"access_token": "not.a.jwt"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"), [("POST", "/api/v1/library/scan"), ("GET", "/api/v1/library/scan/status")]
)
def test_regular_user_cannot_use_scan(lib_env: tuple[Env, Path], method: str, path: str) -> None:
    env, _ = lib_env
    client = logged_in(env, "alice")
    response = client.get(path) if method == "GET" else client.post(path)
    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


def test_scan_post_needs_csrf(lib_env: tuple[Env, Path]) -> None:
    env, _ = lib_env
    client = logged_in(env, "root")
    response = client.http.post("/api/v1/library/scan")  # no CSRF header, no Origin
    assert response.status_code == 403


def test_scan_endpoint_accepts_no_path_or_body_fields(lib_env: tuple[Env, Path]) -> None:
    env, _ = lib_env
    client = logged_in(env, "root")
    response = client.post("/api/v1/library/scan", {"path": "/etc"})
    assert response.status_code == 202  # the body is ignored: there is no parameter to inject
    assert "/etc" not in response.text
    env.container.scan_runner.wait(5)


# ---------------------------------------------------------------- listing


def test_list_never_exposes_paths(lib_env: tuple[Env, Path]) -> None:
    env, _ = lib_env
    body = logged_in(env).get("/api/v1/items").json()
    assert {i["title"] for i in body["items"]} == {"Vol 1", "Folder Manga"}
    for item in body["items"]:
        assert set(item) == {"id", "type", "title", "format", "page_count", "added_at", "has_cover"}
        assert item["has_cover"] is True
    raw = str(body)
    assert "rel_path" not in raw
    assert ".cbz" not in raw
    assert "broken-secret-name" not in raw  # failed files never became items


def test_pagination_limit_is_capped_at_100(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    for i in range(130):
        add_item(env, f"Item {i:03d}")
    client = logged_in(env)
    assert len(client.get("/api/v1/items").json()["items"]) == 50  # default
    capped = client.get("/api/v1/items?limit=100000").json()
    assert (len(capped["items"]), capped["limit"], capped["has_more"]) == (100, 100, True)
    tail = client.get("/api/v1/items?limit=100&offset=100").json()
    assert (len(tail["items"]), tail["has_more"]) == (30, False)

    seen: list[str] = []
    for offset in range(0, 130, 25):
        seen += [
            i["id"] for i in client.get(f"/api/v1/items?limit=25&offset={offset}").json()["items"]
        ]
    assert len(seen) == len(set(seen)) == 130  # stable order: no overlap, no gaps


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=-1",
        "limit=abc",
        "offset=-1",
        "offset=99999999999",
        "type=video",
        f"q={'x' * 101}",
    ],
)
def test_invalid_query_parameters_are_rejected_generically(
    lib_env: tuple[Env, Path], query: str
) -> None:
    response = logged_in(lib_env[0]).get(f"/api/v1/items?{query}")
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_q_of_exactly_100_characters_is_accepted(lib_env: tuple[Env, Path]) -> None:
    assert logged_in(lib_env[0]).get(f"/api/v1/items?q={'x' * 100}").status_code == 200


def test_type_filter(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    add_item(env, "A manga")
    add_item(env, "A book", item_type=ItemType.BOOK)
    client = logged_in(env)
    assert [i["title"] for i in client.get("/api/v1/items?type=book").json()["items"]] == ["A book"]


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("%25", ["100% real"]),
        ("_", ["snake_case"]),
        ("%5C", ["back\\slash"]),
        ("%22hi%22", ['say "hi"']),
        ("%27", ["it's here"]),
        ("a%C3%A7%C3%A3o", ["Ação Épica"]),
        ("%E6%97%A5%E6%9C%AC", ["日本語"]),
        ("%27%20OR%20%271%27%3D%271", []),
        ("%27%3B%20DROP%20TABLE%20items%3B--", []),
        ("%00", []),
        ("%25_", []),
    ],
)
def test_search_special_characters(
    db_url: str, tmp_path: Path, q: str, expected: list[str]
) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    for title in [
        "100% real",
        "snake_case",
        "back\\slash",
        'say "hi"',
        "it's here",
        "Ação Épica",
        "日本語",
        "plain",
    ]:
        add_item(env, title)
    client = logged_in(env)
    response = client.get(f"/api/v1/items?q={q}")
    assert response.status_code == 200
    assert [i["title"] for i in response.json()["items"]] == expected
    assert client.get("/api/v1/items").json()["items"]  # the table survived


def test_missing_items_are_not_listed_nor_readable(lib_env: tuple[Env, Path]) -> None:
    env, lib = lib_env
    client = logged_in(env)
    item_id = item_id_by_title(client, "Vol 1")
    (lib / "Vol 1.cbz").unlink()
    env.container.scan_runner.run()
    assert "Vol 1" not in {i["title"] for i in client.get("/api/v1/items").json()["items"]}
    assert client.get(f"/api/v1/items/{item_id}").status_code == 404
    assert client.get(f"/api/v1/items/{item_id}/pages/0").status_code == 404
    assert client.get(f"/api/v1/items/{item_id}/cover").status_code == 404


# ---------------------------------------------------------------- hostile ids and page numbers

BAD_IDS = [
    "..",
    "../../etc/passwd",
    "..%2F..%2Fetc%2Fpasswd",
    "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..\\..\\windows\\win.ini",
    "' OR '1'='1",
    "1",
    "0" * 36,
    "x" * 36,
    "{" + UNKNOWN + "}",
    "urn:uuid:" + UNKNOWN,
    UNKNOWN.replace("-", ""),
    UNKNOWN + "0",
    "x" * 5000,
    "%00",
    "٣" * 36,
]


@pytest.mark.parametrize("bad", BAD_IDS)
@pytest.mark.parametrize("suffix", ["", "/pages/0", "/cover"])
def test_hostile_ids_are_404_never_500(lib_env: tuple[Env, Path], bad: str, suffix: str) -> None:
    api = logged_in(lib_env[0])
    response = api.get(f"/api/v1/items/{bad}{suffix}")
    assert response.status_code == 404
    assert "passwd" not in response.text and "win.ini" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_unknown_but_valid_uuid_is_404(lib_env: tuple[Env, Path]) -> None:
    api = logged_in(lib_env[0])
    for suffix in ("", "/pages/0", "/cover"):
        response = api.get(f"/api/v1/items/{UNKNOWN}{suffix}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not found"}


def test_uppercase_uuid_resolves_to_the_same_item(lib_env: tuple[Env, Path]) -> None:
    api = logged_in(lib_env[0])
    item_id = item_id_by_title(api, "Vol 1")
    assert api.get(f"/api/v1/items/{item_id.upper()}").status_code == 200


@pytest.mark.parametrize(
    "n",
    [
        "-1",
        "3",
        "4",
        "999999999",
        "1000000000",
        "99999999999999999999",
        "abc",
        "1.5",
        "1e3",
        "0x1",
        "+1",
        " 1",
        "1 ",
        "٣",
        "%00",
        "..%2F1",
        "1%2F..",
        "",
        "%20",
    ],
)
def test_page_number_out_of_range_or_hostile_is_404(lib_env: tuple[Env, Path], n: str) -> None:
    api = logged_in(lib_env[0])
    item_id = item_id_by_title(api, "Vol 1")  # 3 pages: valid indexes are 0..2
    response = api.get(f"/api/v1/items/{item_id}/pages/{n}")
    assert response.status_code in (404, 405)
    assert response.headers["cache-control"] == "no-store"


def test_valid_page_numbers(lib_env: tuple[Env, Path]) -> None:
    api = logged_in(lib_env[0])
    item_id = item_id_by_title(api, "Vol 1")
    for n, seed in ((0, 1), (1, 2), (2, 3), ("00", 1)):
        response = api.get(f"/api/v1/items/{item_id}/pages/{n}")
        assert response.status_code == 200
        assert response.content == png(seed)


# ---------------------------------------------------------------- page / cover responses


def test_page_response_headers(lib_env: tuple[Env, Path]) -> None:
    api = logged_in(lib_env[0])
    item_id = item_id_by_title(api, "Vol 1")
    response = api.get(f"/api/v1/items/{item_id}/pages/1")
    assert response.status_code == 200
    assert response.content == png(2)
    h = response.headers
    assert h["content-type"] == "image/png"
    assert h["x-content-type-options"] == "nosniff"
    assert h["content-disposition"] == "inline"
    assert h["cache-control"] == PRIVATE_CACHE
    assert h.get_list("cache-control") == [PRIVATE_CACHE]
    assert "pragma" not in h
    assert "x-internal-cache-class" not in h  # the marker never leaves the server
    assert h["etag"].startswith('"') and not h["etag"].startswith("W/")
    assert "default-src 'self'" in h["content-security-policy"]  # other headers still apply
    assert h["referrer-policy"] == "no-referrer"


def test_cover_has_the_same_policy(lib_env: tuple[Env, Path]) -> None:
    api = logged_in(lib_env[0])
    for title, seed in (("Vol 1", 1), ("Folder Manga", 1)):
        response = api.get(f"/api/v1/items/{item_id_by_title(api, title)}/cover")
        assert response.status_code == 200
        assert response.content == png(seed)
        assert response.headers["cache-control"] == PRIVATE_CACHE
        assert response.headers["content-disposition"] == "inline"
        assert response.headers["x-content-type-options"] == "nosniff"


def test_if_none_match_gives_304_without_body(lib_env: tuple[Env, Path]) -> None:
    api = logged_in(lib_env[0])
    url = f"/api/v1/items/{item_id_by_title(api, 'Vol 1')}/pages/0"
    first = api.get(url)
    etag = first.headers["etag"]
    for header in (etag, f"W/{etag}", f'"other", {etag}', "*"):
        again = api.http.get(url, headers={"If-None-Match": header})
        assert again.status_code == 304, header
        assert again.content == b""
        assert again.headers["etag"] == etag
        assert again.headers["cache-control"] == PRIVATE_CACHE
        assert again.headers["x-content-type-options"] == "nosniff"
    stale = api.http.get(url, headers={"If-None-Match": '"stale"'})
    assert stale.status_code == 200
    assert stale.headers["etag"] == etag
    # Different content has a different strong validator.
    other = api.get(f"/api/v1/items/{item_id_by_title(api, 'Vol 1')}/pages/1")
    assert other.headers["etag"] != etag


def test_304_still_requires_authentication(lib_env: tuple[Env, Path]) -> None:
    env, _ = lib_env
    url = f"/api/v1/items/{item_id_by_title(logged_in(env), 'Vol 1')}/pages/0"
    response = env.client().http.get(url, headers={"If-None-Match": "*"})
    assert response.status_code == 401


def test_other_routes_stay_no_store(lib_env: tuple[Env, Path]) -> None:
    env, _ = lib_env
    admin = logged_in(env, "root")
    item_id = item_id_by_title(admin, "Vol 1")
    for path in (
        "/api/v1/items",
        f"/api/v1/items/{item_id}",
        "/api/v1/library/scan/status",
        "/api/v1/auth/me",
        f"/api/v1/items/{UNKNOWN}/pages/0",  # an error on an allowlisted path
        f"/api/v1/items/{item_id}/pages/99",
        "/api/v1/items/not-a-uuid/cover",
    ):
        headers = admin.get(path).headers
        assert headers.get_list("cache-control") == ["no-store"], path
        assert headers["pragma"] == "no-cache", path
    started = admin.post("/api/v1/library/scan")
    assert started.headers["cache-control"] == "no-store"
    env.container.scan_runner.wait(5)


# ---------------------------------------------------------------- error hygiene


def _assert_generic(response, *forbidden: str) -> None:  # type: ignore[no-untyped-def]
    text = response.text.lower()
    for word in ("traceback", "zipfile", "badzip", ".cbz", "lib", "tmp", "pytest", *forbidden):
        assert word.lower() not in text, word
    assert response.headers["cache-control"] == "no-store"


def test_corrupted_file_after_scan_is_a_generic_422(lib_env: tuple[Env, Path]) -> None:
    env, lib = lib_env
    api = logged_in(env)
    item_id = item_id_by_title(api, "Vol 1")
    (lib / "Vol 1.cbz").write_bytes(b"this is no longer a zip file")
    for suffix in ("/pages/0", "/cover"):
        response = api.get(f"/api/v1/items/{item_id}{suffix}")
        assert response.status_code == 422
        assert response.json() == {"detail": "Item cannot be read"}
        _assert_generic(response, "Vol 1")


def test_zip_bomb_after_scan_is_a_generic_422(db_url: str, tmp_path: Path) -> None:
    env, lib = library_env(db_url, tmp_path, EXTRACTOR_MAX_COMPRESSION_RATIO=20)
    api = logged_in(env)
    item_id = item_id_by_title(api, "Vol 1")
    bomb = make_cbz({"1.png": png() + b"\x00" * 2_000_000, "2.png": png(), "3.png": png()})
    (lib / "Vol 1.cbz").write_bytes(bomb)
    response = api.get(f"/api/v1/items/{item_id}/pages/0")
    assert response.status_code == 422
    assert response.json() == {"detail": "Item cannot be read"}
    _assert_generic(response)


def test_deleted_file_after_scan_is_404_without_the_path(lib_env: tuple[Env, Path]) -> None:
    env, lib = lib_env
    api = logged_in(env)
    item_id = item_id_by_title(api, "Vol 1")
    (lib / "Vol 1.cbz").unlink()
    response = api.get(f"/api/v1/items/{item_id}/pages/0")
    assert response.status_code == 404
    _assert_generic(response, "Vol 1")


class _RaisingExtractor:
    format = "boom"
    item_type = ItemType.MANGA

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def can_handle(self, entry: object) -> bool:
        return False

    def read_page(self, rel_path: str, index: int) -> Page:
        raise self.exc

    def read_cover(self, rel_path: str) -> Page:
        raise self.exc


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (CorruptArchive("/secret/dir/file.cbz is bad"), 422),
        (ArchiveLimitExceeded("/secret/dir/file.cbz too big"), 422),
        (UnsafePath("/secret/dir/../../etc"), 422),
        (FileNotFoundError("/secret/dir/file.cbz"), 404),
        (PermissionError("/secret/dir/file.cbz"), 503),
        (OSError("disk exploded at /secret/dir"), 503),
    ],
)
def test_extractor_errors_never_leak_messages(
    lib_env: tuple[Env, Path], exc: Exception, status: int
) -> None:
    env, _ = lib_env
    item = add_item(env, "Weird", fmt="boom")
    env.container.extractors = [_RaisingExtractor(exc)]  # type: ignore[list-item]
    api = logged_in(env)
    for suffix in ("/pages/0", "/cover"):
        response = api.get(f"/api/v1/items/{item.id}{suffix}")
        assert response.status_code == status
        assert "secret" not in response.text and "exploded" not in response.text
        assert response.headers["cache-control"] == "no-store"


def test_unexpected_error_is_a_generic_500(lib_env: tuple[Env, Path]) -> None:
    env, _ = lib_env
    item = add_item(env, "Weird", fmt="boom")
    env.container.extractors = [_RaisingExtractor(RuntimeError("secret internal detail"))]  # type: ignore[list-item]
    api = logged_in(env)
    api.http = TestClient(
        env.app,
        base_url="https://testserver",
        raise_server_exceptions=False,
        client=("10.0.0.1", 50000),
    )
    api.login()
    response = api.get(f"/api/v1/items/{item.id}/pages/0")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert response.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------- only image types are served


class _FixedPageExtractor:
    format = "fixed"
    item_type = ItemType.MANGA

    def __init__(self, media_type: str, data: bytes = b"<svg onload=alert(1)>") -> None:
        self.page = Page(data=data, media_type=media_type)

    def can_handle(self, entry: object) -> bool:
        return False

    def read_page(self, rel_path: str, index: int) -> Page:
        return self.page

    def read_cover(self, rel_path: str) -> Page:
        return self.page


@pytest.mark.parametrize(
    "media_type",
    [
        "image/svg+xml",
        "text/html",
        "application/javascript",
        "application/octet-stream",
        "text/html; charset=utf-8",
        "image/png; foo",
        "IMAGE/PNG",
        "",
    ],
)
def test_non_allowed_media_types_are_never_served(
    lib_env: tuple[Env, Path], media_type: str
) -> None:
    env, _ = lib_env
    item = add_item(env, "Fixed", fmt="fixed")
    env.container.extractors = [_FixedPageExtractor(media_type)]  # type: ignore[list-item]
    api = logged_in(env)
    for suffix in ("/pages/0", "/cover"):
        response = api.get(f"/api/v1/items/{item.id}{suffix}")
        assert response.status_code == 422
        assert "<svg" not in response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["content-type"] == "application/json"


@pytest.mark.parametrize(
    "media_type", ["image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"]
)
def test_allowed_media_types_are_served_with_nosniff(
    lib_env: tuple[Env, Path], media_type: str
) -> None:
    env, _ = lib_env
    item = add_item(env, "Fixed", fmt="fixed")
    env.container.extractors = [_FixedPageExtractor(media_type, b"data")]  # type: ignore[list-item]
    response = logged_in(env).get(f"/api/v1/items/{item.id}/pages/0")
    assert response.status_code == 200
    assert response.headers["content-type"] == media_type
    assert response.headers["x-content-type-options"] == "nosniff"


def test_content_type_follows_magic_bytes_not_file_names(db_url: str, tmp_path: Path) -> None:
    """A page named .png whose bytes are not an image never becomes an item page."""
    env, lib = library_env(db_url, tmp_path, scan=False)
    (lib / "Evil.cbz").write_bytes(make_cbz({"1.png": b"<html><script>alert(1)</script>"}))
    shutil.rmtree(lib / "Folder Manga")
    report = env.container.scan_runner.run()
    assert report.state.value == "finished"
    api = logged_in(env)
    titles = {i["title"] for i in api.get("/api/v1/items").json()["items"]}
    assert "Evil" not in titles  # rejected at scan time (no readable page)


def test_item_ids_are_uuid4_and_unguessable(lib_env: tuple[Env, Path]) -> None:
    api = logged_in(lib_env[0])
    for item in api.get("/api/v1/items").json()["items"]:
        assert uuid.UUID(item["id"]).version == 4
