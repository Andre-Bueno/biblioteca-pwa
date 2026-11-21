"""The CSP/cache exception of the book chapter route is as narrow as the image-cache one (ADR 0010):
fixed path, GET, status 200, internal marker. Nothing else can ever receive that CSP."""

from pathlib import Path

import pytest
from app.api.security_headers import (
    BOOK_CHAPTER_CSP,
    CACHE_MARKER_BOOK_CHAPTER,
    CACHE_MARKER_HEADER,
    CACHE_MARKER_PRIVATE_IMAGE,
    SECURITY_HEADERS,
    SecurityHeadersMiddleware,
)
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.responses import Response

from epub_fixtures import make_epub
from library_env import book_env, logged_in

ITEM = "11111111-2222-4333-8444-555555555555"
CHAPTER = f"/api/v1/items/{ITEM}/book/chapters/0"
CHAPTER_CSP = BOOK_CHAPTER_CSP.decode()
GLOBAL_CSP = SECURITY_HEADERS[b"content-security-policy"].decode()
PRIVATE = "private, max-age=3600"
MARK = {CACHE_MARKER_HEADER: CACHE_MARKER_BOOK_CHAPTER}


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    return app


def _plain(response) -> None:  # type: ignore[no-untyped-def]
    assert response.headers.get_list("content-security-policy") == [GLOBAL_CSP]
    assert response.headers.get_list("cache-control") == ["no-store"]
    assert response.headers["pragma"] == "no-cache"
    assert CACHE_MARKER_HEADER not in response.headers


def test_the_chapter_csp_is_exactly_the_specified_policy() -> None:
    assert CHAPTER_CSP == (
        "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'self'; "
        "base-uri 'none'; form-action 'none'"
    )
    assert "frame-ancestors 'none'" in GLOBAL_CSP  # the global policy is untouched


def test_marked_chapter_response_gets_the_chapter_csp_and_private_cache() -> None:
    app = _app()

    @app.get("/api/v1/items/{item_id}/book/chapters/{n}")
    def chapter(item_id: str, n: str) -> Response:
        # the route tries to choose its own policy and cache: the middleware overrides both
        return Response(
            "<p>x</p>",
            media_type="text/html",
            headers=MARK
            | {"Content-Security-Policy": "default-src *", "Cache-Control": "public, max-age=9"},
        )

    response = TestClient(app).get(CHAPTER)
    assert response.headers.get_list("content-security-policy") == [CHAPTER_CSP]
    assert response.headers.get_list("cache-control") == [PRIVATE]
    assert "pragma" not in response.headers
    assert CACHE_MARKER_HEADER not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "permissions-policy" in response.headers
    assert "x-frame-options" not in response.headers


def test_chapter_path_without_the_marker_is_plain() -> None:
    app = _app()

    @app.get("/api/v1/items/{item_id}/book/chapters/{n}")
    def chapter(item_id: str, n: str) -> Response:
        return Response("x", headers={"Content-Security-Policy": "default-src *"})

    _plain(TestClient(app).get(CHAPTER))


@pytest.mark.parametrize(
    "value", ["private-image", "Book-Chapter", "book-chapter ", "1", "", "true"]
)
def test_only_the_exact_marker_counts(value: str) -> None:
    app = _app()

    @app.get("/api/v1/items/{item_id}/book/chapters/{n}")
    def chapter(item_id: str, n: str) -> Response:
        return Response("x", headers={CACHE_MARKER_HEADER: value})

    response = TestClient(app).get(CHAPTER)
    assert response.headers["content-security-policy"] == GLOBAL_CSP
    if value == "private-image":  # not for this path
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/items/{ITEM}/book",
        f"/api/v1/items/{ITEM}/book/",
        f"/api/v1/items/{ITEM}/book/chapters",
        f"/api/v1/items/{ITEM}/book/chapters/",
        f"/api/v1/items/{ITEM}/book/chapters/0/extra",
        f"/api/v1/items/{ITEM}/book/chapters/abc",
        f"/api/v1/items/{ITEM}/book/chapters/-1",
        f"/api/v1/items/{ITEM}/book/chapters/1234567",
        f"/api/v1/items/{ITEM}/book/chapters/0x1",
        f"/api/v1/items/{ITEM}/book/res/0",
        f"/api/v1/items/{ITEM}/pages/0",
        f"/api/v1/items/{ITEM}/cover",
        f"/api/v1/items/{ITEM}",
        "/api/v1/items/not-a-uuid/book/chapters/0",
        f"/api/v1/items/{ITEM}x/book/chapters/0",
        f"/api/v1/other/{ITEM}/book/chapters/0",
        f"/api/v2/items/{ITEM}/book/chapters/0",
        f"/api/v1/series/{ITEM}/book/chapters/0",
        f"/api/v1/series/{ITEM}/cover",
        "/api/v1/auth/me",
        "/api/v1/me/preferences",
        f"/x/api/v1/items/{ITEM}/book/chapters/0",
        f"/api/v1/items/{ITEM}/book/chapters/0;x",
        f"/api/v1/items/{ITEM}//book/chapters/0",
    ],
)
def test_no_other_path_can_get_the_chapter_csp(path: str) -> None:
    app = _app()

    @app.get("/{full_path:path}")
    def anything(full_path: str) -> Response:
        return Response("x", headers=MARK | {"Content-Security-Policy": "default-src *"})

    response = TestClient(app).get(path)
    assert response.headers["content-security-policy"] == GLOBAL_CSP, path
    if path.startswith("/api"):
        assert response.headers.get_list("cache-control") == ["no-store"], path
    assert CACHE_MARKER_HEADER not in response.headers


def test_image_marker_on_the_chapter_path_does_nothing() -> None:
    app = _app()

    @app.get("/{full_path:path}")
    def anything(full_path: str) -> Response:
        return Response("x", headers={CACHE_MARKER_HEADER: CACHE_MARKER_PRIVATE_IMAGE})

    _plain(TestClient(app).get(CHAPTER))


def test_chapter_marker_on_image_paths_does_nothing() -> None:
    app = _app()

    @app.get("/{full_path:path}")
    def anything(full_path: str) -> Response:
        return Response("x", headers=MARK)

    for path in (
        f"/api/v1/items/{ITEM}/pages/0",
        f"/api/v1/items/{ITEM}/cover",
        f"/api/v1/items/{ITEM}/book/res/0",
        f"/api/v1/series/{ITEM}/cover",
    ):
        _plain(TestClient(app).get(path))


def test_marker_is_ignored_for_other_methods() -> None:
    app = _app()

    @app.post("/api/v1/items/{item_id}/book/chapters/{n}")
    def chapter(item_id: str, n: str) -> Response:
        return Response("x", headers=MARK)

    _plain(TestClient(app).post(CHAPTER))


@pytest.mark.parametrize("status", [201, 204, 301, 400, 401, 403, 404, 422, 429, 500, 503])
def test_error_and_other_statuses_never_get_the_exception(status: int) -> None:
    app = _app()

    @app.get("/api/v1/items/{item_id}/book/chapters/{n}")
    def chapter(item_id: str, n: str) -> Response:
        return Response("x", status_code=status, headers=MARK)

    _plain(TestClient(app, follow_redirects=False).get(CHAPTER))


def test_304_is_cacheable_but_keeps_the_global_csp() -> None:
    app = _app()

    @app.get("/api/v1/items/{item_id}/book/chapters/{n}")
    def chapter(item_id: str, n: str) -> Response:
        return Response(status_code=304, headers=MARK)

    response = TestClient(app).get(CHAPTER)
    assert response.status_code == 304
    assert response.headers["cache-control"] == PRIVATE
    assert response.headers["content-security-policy"] == GLOBAL_CSP  # no body: nothing to frame


def test_the_marker_never_leaks_outside_api() -> None:
    app = _app()

    @app.get("/static-thing")
    def static_thing() -> Response:
        return Response("x", headers=MARK)

    response = TestClient(app).get("/static-thing")
    assert CACHE_MARKER_HEADER not in response.headers
    assert response.headers["content-security-policy"] == GLOBAL_CSP


def test_real_app_only_the_chapter_route_gets_the_chapter_csp(db_url: str, tmp_path: Path) -> None:
    """Behavioral check over every REGISTERED GET route of the real app, called with a real book:
    the chapter CSP appears on `book/chapters/{n}` and nowhere else; the private cache only on page
    images, covers, book images and chapters; the internal marker never reaches the client."""
    env, _ = book_env(
        db_url,
        tmp_path,
        {
            "One.epub": make_epub(
                cover="property", images={"a.png": b"\x89PNG\r\n\x1a\n" + b"1" * 20}
            )
        },
    )
    client = logged_in(env, "root")
    item = env.container.item_repository.get_by_rel_path("One.epub")
    assert item is not None and item.series_id is not None
    values = {"item_id": item.id, "n": "0", "rid": "0", "series_id": item.series_id}

    flat = [
        r
        for top in env.app.routes
        for r in (top.original_router.routes if hasattr(top, "original_router") else [top])
    ]
    routes = [
        r
        for r in flat
        if isinstance(r, APIRoute) and "GET" in r.methods and r.path.startswith("/api")
    ]
    assert len(routes) >= 12
    chapter_csp: set[str] = set()
    private: set[str] = set()
    for route in routes:
        assert set(route.param_convertors) <= set(values), f"teach this test {route.path}"
        response = client.get(route.path.format(**values))
        assert CACHE_MARKER_HEADER not in response.headers, route.path
        if response.headers["content-security-policy"] == CHAPTER_CSP:
            chapter_csp.add(route.path)
            assert response.status_code == 200
        else:
            assert response.headers["content-security-policy"] == GLOBAL_CSP, route.path
        if response.headers.get("cache-control") == PRIVATE:
            assert response.status_code == 200, route.path
            private.add(route.path)
        else:
            assert response.headers["cache-control"] == "no-store", route.path
    assert chapter_csp == {"/api/v1/items/{item_id}/book/chapters/{n}"}
    assert private == {
        "/api/v1/items/{item_id}/cover",
        "/api/v1/series/{series_id}/cover",
        "/api/v1/items/{item_id}/book/res/{rid}",
        "/api/v1/items/{item_id}/book/chapters/{n}",
    }
