"""The private-cache exception to `no-store` is narrow: fixed paths AND an explicit marker."""

from pathlib import Path

import pytest
from app.api.security_headers import (
    CACHE_MARKER_HEADER,
    CACHE_MARKER_PRIVATE_IMAGE,
    SecurityHeadersMiddleware,
)
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.responses import Response

from library_env import library_env, logged_in

ITEM = "11111111-2222-4333-8444-555555555555"
PAGE = f"/api/v1/items/{ITEM}/pages/0"
COVER = f"/api/v1/items/{ITEM}/cover"
SERIES_COVER = f"/api/v1/series/{ITEM}/cover"
PRIVATE = "private, max-age=3600"
MARK = {CACHE_MARKER_HEADER: CACHE_MARKER_PRIVATE_IMAGE}


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    return app


def _no_store(response) -> None:  # type: ignore[no-untyped-def]
    assert response.headers.get_list("cache-control") == ["no-store"]
    assert response.headers["pragma"] == "no-cache"
    assert CACHE_MARKER_HEADER not in response.headers


def test_marked_response_on_the_allowlisted_paths_is_privately_cacheable() -> None:
    app = _app()

    @app.get("/api/v1/items/{item_id}/pages/{n}")
    def page(item_id: str, n: str) -> Response:
        return Response(b"x", headers=MARK | {"Cache-Control": "public, max-age=99999999"})

    @app.get("/api/v1/items/{item_id}/cover")
    def cover(item_id: str) -> Response:
        return Response(b"x", headers=MARK)

    @app.get("/api/v1/series/{series_id}/cover")
    def series_cover(series_id: str) -> Response:
        return Response(b"x", headers=MARK | {"Cache-Control": "public"})

    client = TestClient(app)
    for path in (PAGE, COVER, SERIES_COVER):
        response = client.get(path)
        assert response.headers.get_list("cache-control") == [PRIVATE], path  # canonical value
        assert "pragma" not in response.headers
        assert CACHE_MARKER_HEADER not in response.headers
        assert "content-security-policy" in response.headers
        assert response.headers["x-content-type-options"] == "nosniff"


def test_allowlisted_path_without_the_marker_stays_no_store() -> None:
    app = _app()

    @app.get("/api/v1/items/{item_id}/pages/{n}")
    def page(item_id: str, n: str) -> Response:
        return Response(b"x", headers={"Cache-Control": "public, max-age=3600"})

    _no_store(TestClient(app).get(PAGE))


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/items",
        f"/api/v1/items/{ITEM}",
        f"/api/v1/items/{ITEM}/pages",
        f"/api/v1/items/{ITEM}/pages/0/extra",
        f"/api/v1/items/{ITEM}/cover/x",
        f"/api/v1/items/{ITEM}/pages/-1",
        f"/api/v1/items/{ITEM}/pages/abc",
        f"/api/v1/items/{ITEM}/pages/1234567890",  # more than 9 digits
        "/api/v1/items/not-a-uuid/pages/0",
        f"/api/v1/items/{ITEM}x/cover",
        "/api/v1/library/scan/status",
        "/api/v1/auth/me",
        "/api/v1/health",
        f"/api/v1/other/{ITEM}/pages/0",
        f"/api/v2/items/{ITEM}/cover",
        f"/api/v2/series/{ITEM}/cover",
        "/api/v1/series",
        f"/api/v1/series/{ITEM}",
        f"/api/v1/series/{ITEM}/cover/x",
        f"/api/v1/series/{ITEM}/pages/0",
        f"/api/v1/series/{ITEM}/chapters",
        f"/api/v1/series/{ITEM}x/cover",
        "/api/v1/series/not-a-uuid/cover",
    ],
)
def test_no_other_route_can_opt_in_even_with_the_marker(path: str) -> None:
    app = _app()

    @app.get("/{full_path:path}")
    def anything(full_path: str) -> Response:
        return Response("x", headers=MARK | {"Cache-Control": "public"})

    _no_store(TestClient(app).get(path))


def test_marker_is_ignored_for_non_get_methods() -> None:
    app = _app()

    @app.post("/api/v1/items/{item_id}/cover")
    def cover(item_id: str) -> Response:
        return Response("x", headers=MARK)

    _no_store(TestClient(app).post(COVER))


@pytest.mark.parametrize("status", [401, 403, 404, 422, 500])
def test_error_statuses_are_never_cacheable(status: int) -> None:
    app = _app()

    @app.get("/api/v1/items/{item_id}/cover")
    def cover(item_id: str) -> Response:
        return Response("x", status_code=status, headers=MARK)

    _no_store(TestClient(app).get(COVER))


@pytest.mark.parametrize("value", ["public", "private-image ", "PRIVATE-IMAGE", "1", ""])
def test_only_the_exact_marker_value_counts(value: str) -> None:
    app = _app()

    @app.get("/api/v1/items/{item_id}/cover")
    def cover(item_id: str) -> Response:
        return Response("x", headers={CACHE_MARKER_HEADER: value})

    _no_store(TestClient(app).get(COVER))


def test_304_on_an_allowlisted_path_keeps_the_private_policy() -> None:
    app = _app()

    @app.get("/api/v1/items/{item_id}/cover")
    def cover(item_id: str) -> Response:
        return Response(status_code=304, headers=MARK)

    response = TestClient(app).get(COVER)
    assert response.status_code == 304
    assert response.headers["cache-control"] == PRIVATE


def test_the_marker_never_leaks_outside_api_either() -> None:
    app = _app()

    @app.get("/static-thing")
    def static_thing() -> Response:
        return Response("x", headers=MARK | {"Cache-Control": "public, max-age=3600"})

    response = TestClient(app).get("/static-thing")
    assert CACHE_MARKER_HEADER not in response.headers
    assert response.headers["cache-control"] == "public, max-age=3600"  # unchanged outside /api


def test_real_app_only_page_and_cover_routes_are_privately_cacheable(
    db_url: str, tmp_path: Path
) -> None:
    """Behavioral check over the REGISTERED routes (not the source text): call every GET route of
    the real app as an admin; only the page and cover routes may answer with the private cache
    policy, everything else stays `no-store`, and the internal marker never reaches the client."""
    env, _ = library_env(db_url, tmp_path)
    client = logged_in(env, "root")
    item = env.container.item_repository.get_by_rel_path("Vol 1.cbz")
    assert item is not None
    assert item.series_id is not None
    values = {"item_id": item.id, "n": "0", "series_id": item.series_id}

    # FastAPI >= 0.16x nests included routers: flatten them (their paths already carry prefixes).
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
    # health, csrf, me, items (list/get/page/cover), series (list/get/cover), scan status
    assert len(routes) >= 9
    private: set[str] = set()
    for route in routes:
        params = set(route.param_convertors)
        assert params <= set(values), f"{route.path}: teach this test its path parameters"
        response = client.get(route.path.format(**values))
        assert CACHE_MARKER_HEADER not in response.headers, route.path
        if response.headers.get("cache-control") == PRIVATE:
            assert response.status_code == 200, route.path
            private.add(route.path)
        else:
            assert response.headers["cache-control"] == "no-store", route.path
    assert private == {
        "/api/v1/items/{item_id}/pages/{n}",
        "/api/v1/items/{item_id}/cover",
        "/api/v1/series/{series_id}/cover",
    }
