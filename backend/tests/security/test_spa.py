"""The app serves the built frontend (FRONTEND_DIST_DIR): traversal, dotfiles, fallback, cache."""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from app.core.config import Settings
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.types import Message

from auth_fakes import make_settings

INDEX_HTML = "<!doctype html><title>spa</title><script type='module' src='/assets/app-1a2b.js'>"
SECRET_OUTSIDE = "TOP-SECRET-OUTSIDE-THE-ROOT"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "site" / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX_HTML)
    (root / "sw.js").write_text("self.skipWaiting()")
    (root / "workbox-9c191d2f.js").write_text("// workbox")
    (root / "manifest.webmanifest").write_text('{"name":"x"}')
    (root / "icon-192.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    (root / "assets" / "app-1a2b.js").write_text("console.log(1)" + "/" * 2000)
    (root / "assets" / "app-3c4d.css").write_text("body{margin:0}")
    (root / ".env").write_text("SECRET_KEY=leak")
    (root / ".hidden").mkdir()
    (root / ".hidden" / "x.txt").write_text("leak")
    (root.parent / "secret.txt").write_text(SECRET_OUTSIDE)
    return root


def _app(dist: Path | None, db_url: str) -> FastAPI:
    return create_app(make_settings(db_url, FRONTEND_DIST_DIR=dist))


@pytest.fixture
def spa(dist: Path, db_url: str) -> TestClient:
    return TestClient(_app(dist, db_url))


@dataclass
class Raw:
    status: int
    headers: dict[str, str]
    body: bytes


def raw_request(app: FastAPI, path: str, method: str = "GET") -> Raw:
    """Calls the ASGI app with `path` EXACTLY as given (already decoded, like uvicorn does),
    because an HTTP client would normalise `..` before sending."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("latin-1", "replace"),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("203.0.113.9", 5000),
        "server": ("testserver", 80),
        "app": app,
    }
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    asyncio.run(app(scope, receive, send))  # type: ignore[arg-type]
    start = next(m for m in messages if m["type"] == "http.response.start")
    headers = {k.decode().lower(): v.decode("latin-1") for k, v in start["headers"]}
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return Raw(start["status"], headers, body)


def test_without_dist_dir_nothing_is_served(db_url: str, dist: Path) -> None:
    client = TestClient(_app(None, db_url))
    assert client.get("/").status_code == 404
    assert client.get("/index.html").status_code == 404
    assert client.get("/assets/app-1a2b.js").status_code == 404


def test_empty_variable_means_no_static_serving(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONTEND_DIST_DIR", "")
    assert Settings(_env_file=None).FRONTEND_DIST_DIR is None  # type: ignore[call-arg]


def test_missing_dist_dir_fails_at_startup(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="FRONTEND_DIST_DIR"):
        make_settings("sqlite:///x.db", FRONTEND_DIST_DIR=tmp_path / "does-not-exist")


def test_dist_dir_without_index_fails_at_startup(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="index.html"):
        make_settings("sqlite:///x.db", FRONTEND_DIST_DIR=tmp_path)


def test_root_and_index_serve_the_shell(spa: TestClient) -> None:
    for path in ("/", "/index.html"):
        response = spa.get(path)
        assert response.status_code == 200
        assert response.text == INDEX_HTML
        assert response.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", ["/library", "/reader/abc-123", "/assets", "/assets/", "/a/b/c/"])
def test_extensionless_unknown_path_falls_back_to_index(spa: TestClient, path: str) -> None:
    response = spa.get(path)
    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/missing.js", "/assets/gone.css", "/x/y.png", "/favicon.ico"])
def test_unknown_file_with_extension_is_a_plain_404(spa: TestClient, path: str) -> None:
    response = spa.get(path)
    assert response.status_code == 404
    assert INDEX_HTML not in response.text
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/api", "/api/", "/api/nope", "/api/v1/nope", "/api/v1/health/"])
def test_unknown_api_path_is_json_404_never_the_shell(spa: TestClient, path: str) -> None:
    response = spa.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert response.headers["cache-control"] == "no-store"
    assert "spa" not in response.text


def test_api_still_works_and_stays_no_store(spa: TestClient) -> None:
    response = spa.get("/api/v1/health")
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"


def test_docs_are_not_exposed(spa: TestClient) -> None:
    for path in ("/api/docs", "/api/openapi.json", "/docs", "/redoc", "/openapi.json"):
        response = spa.get(path)
        assert "openapi" not in response.text.lower()
        assert "swagger" not in response.text.lower()


# ---- traversal and hostile paths --------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/../secret.txt",
        "/assets/../../secret.txt",
        "/assets/../index.html/../../secret.txt",
        "/..",
        "/./index.html",
        "/assets/./app-1a2b.js",
        "/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
        "/..\\secret.txt",
        "/assets\\..\\..\\secret.txt",
        "/index.html\x00.png",
        "/secret.txt\x00",
        "/assets//app-1a2b.js",
        "//etc/passwd",
        "/C:/Windows/win.ini",
        "/index.html:stream",
    ],
)
def test_traversal_and_malformed_paths_never_reach_files(
    dist: Path, db_url: str, path: str
) -> None:
    result = raw_request(_app(dist, db_url), path)
    assert result.status == 404
    assert SECRET_OUTSIDE.encode() not in result.body
    assert INDEX_HTML.encode() not in result.body


def test_encoded_traversal_through_a_real_client(spa: TestClient) -> None:
    for path in (
        "/%2e%2e/secret.txt",
        "/%2E%2E/secret.txt",
        "/..%2Fsecret.txt",
        "/%00",
        "/a%00.js",
    ):
        response = spa.get(path)
        assert SECRET_OUTSIDE not in response.text
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            assert response.text == INDEX_HTML  # only ever the shell


@pytest.mark.parametrize(
    "path",
    ["/.env", "/.hidden", "/.hidden/x.txt", "/assets/.env", "/.git/config", "/.well-known/x"],
)
def test_dotfiles_are_never_served(dist: Path, db_url: str, path: str) -> None:
    result = raw_request(_app(dist, db_url), path)
    assert result.status == 404
    assert b"leak" not in result.body
    assert INDEX_HTML.encode() not in result.body


def test_symlink_out_of_the_root_is_not_followed(dist: Path, db_url: str) -> None:
    try:
        (dist / "assets" / "link.txt").symlink_to(dist.parent / "secret.txt")
        (dist / "linked-dir").symlink_to(dist.parent, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    app = _app(dist, db_url)
    for path in ("/assets/link.txt", "/linked-dir/secret.txt"):
        result = raw_request(app, path)
        assert result.status == 404
        assert SECRET_OUTSIDE.encode() not in result.body


def test_symlink_inside_the_root_is_not_followed_either(dist: Path, db_url: str) -> None:
    try:
        (dist / "alias.js").symlink_to(dist / "assets" / "app-1a2b.js")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    assert raw_request(_app(dist, db_url), "/alias.js").status == 404


def test_symlinked_root_is_resolved_once(dist: Path, db_url: str, tmp_path: Path) -> None:
    link = tmp_path / "root-link"
    try:
        link.symlink_to(dist, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    client = TestClient(_app(link, db_url))
    assert client.get("/sw.js").status_code == 200


# ---- methods ----------------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@pytest.mark.parametrize("path", ["/", "/index.html", "/library", "/assets/app-1a2b.js"])
def test_unsafe_methods_outside_api_are_405(
    dist: Path, db_url: str, method: str, path: str
) -> None:
    result = raw_request(_app(dist, db_url), path, method)
    assert result.status == 405
    assert result.headers["allow"] == "GET, HEAD"
    assert INDEX_HTML.encode() not in result.body


def test_wrong_method_on_a_known_api_route_is_still_405_from_the_router(spa: TestClient) -> None:
    # CSRF answers first for writes under /api; a GET-only route hit with PUT proves that the
    # router (not the SPA handler) still owns /api: it must not turn into a 404 or the shell.
    response = spa.put("/api/v1/health")
    assert response.status_code in (403, 405)
    assert INDEX_HTML not in response.text


def test_head_works_without_body(spa: TestClient) -> None:
    response = spa.head("/assets/app-1a2b.js")
    assert response.status_code == 200
    assert response.content == b""
    assert int(response.headers["content-length"]) > 2000
    assert response.headers["content-type"].startswith("text/javascript")
    assert spa.head("/").status_code == 200
    assert spa.head("/library").status_code == 200


# ---- cache and content types ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "media_type"),
    [
        ("/", "text/html"),
        ("/sw.js", "text/javascript"),
        ("/workbox-9c191d2f.js", "text/javascript"),
        ("/manifest.webmanifest", "application/manifest+json"),
    ],
)
def test_shell_and_service_worker_are_always_revalidated(
    spa: TestClient, path: str, media_type: str
) -> None:
    response = spa.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"].startswith(media_type)


@pytest.mark.parametrize(
    ("path", "media_type"),
    [("/assets/app-1a2b.js", "text/javascript"), ("/assets/app-3c4d.css", "text/css")],
)
def test_hashed_assets_are_immutable(spa: TestClient, path: str, media_type: str) -> None:
    response = spa.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["content-type"].startswith(media_type)


def test_other_files_are_revalidated_and_typed(spa: TestClient) -> None:
    response = spa.get("/icon-192.png")
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["etag"]


def test_fallback_index_is_never_cached_long(spa: TestClient) -> None:
    assert spa.get("/assets").headers["cache-control"] == "no-cache"


def test_range_request_returns_partial_content(spa: TestClient) -> None:
    response = spa.get("/assets/app-1a2b.js", headers={"Range": "bytes=0-3"})
    assert response.status_code == 206
    assert response.content == b"cons"
    assert response.headers["content-range"].startswith("bytes 0-3/")


# ---- security headers on static responses -----------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/", "/library", "/sw.js", "/assets/app-3c4d.css", "/missing.js", "/api/nope"]
)
def test_security_headers_cover_static_responses(spa: TestClient, path: str) -> None:
    response = spa.get(path)
    csp = response.headers["content-security-policy"]
    for directive in (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "worker-src 'self'",
        "manifest-src 'self'",
        "font-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
    ):
        assert directive in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in response.headers["permissions-policy"]


def test_405_and_head_also_carry_security_headers(dist: Path, db_url: str) -> None:
    app = _app(dist, db_url)
    for method in ("POST", "HEAD"):
        result = raw_request(app, "/", method)
        assert "content-security-policy" in result.headers
        assert result.headers["x-content-type-options"] == "nosniff"


def test_static_files_do_not_consume_the_api_rate_limit(dist: Path, db_url: str) -> None:
    app = create_app(
        make_settings(
            db_url, FRONTEND_DIST_DIR=dist, RATE_LIMIT_API_BURST=1, RATE_LIMIT_API_PER_MINUTE=1
        )
    )
    client = TestClient(app)
    assert all(client.get("/").status_code == 200 for _ in range(5))
    assert client.get("/api/v1/health").status_code == 200


def test_dist_dir_env_var_is_read(dist: Path, monkeypatch: pytest.MonkeyPatch, db_url: str) -> None:
    monkeypatch.setenv("FRONTEND_DIST_DIR", os.fspath(dist))
    settings = Settings(_env_file=None, DATABASE_URL=db_url)  # type: ignore[call-arg]
    assert dist == settings.FRONTEND_DIST_DIR
