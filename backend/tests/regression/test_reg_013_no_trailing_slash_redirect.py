"""REG-013 (FIND-2026-008): trailing-slash redirects reflected the Host header.

Bug: FastAPI's default `redirect_slashes=True` answered `GET /api/v1/items/` with a 307 whose
Location was built from the request `Host` (`http://evil.com/api/v1/items`), before any
authentication. The API is consumed by exact URLs, so the redirect is disabled: a slash variant is
a plain 404 and no `Location` is ever produced.
"""

import pytest
from fastapi.testclient import TestClient

from auth_fakes import Env


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/items/",
        "/api/v1/auth/me/",
        "/api/v1/items/00000000-0000-0000-0000-000000000000/pages/0/",
    ],
)
@pytest.mark.parametrize("host", ["evil.com", "testserver"])
def test_slash_variants_are_404_without_location(env: Env, path: str, host: str) -> None:
    client = TestClient(env.app, base_url="https://testserver")
    response = client.get(path, headers={"Host": host}, follow_redirects=False)
    assert response.status_code == 404
    assert "location" not in response.headers


def test_exact_routes_still_work(env: Env) -> None:
    assert env.client().get("/api/v1/health").status_code == 200
