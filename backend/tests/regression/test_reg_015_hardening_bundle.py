"""REG-015 (FIND-2026-010): hardening items that need no new dependency.

One test group per adopted sub-item (the numbers are those of the finding):
1. no `Server: uvicorn` header (`--no-server-header`);
2. uvicorn connection limits and timeouts in the image (env-tunable);
3. runtime and dev dependencies pinned in pyproject.toml;
5. a request with a repeated `Origin` header is refused by the CSRF check.
Not adopted here (see the finding): HSTS and a large password denylist.
"""

import re
import tomllib
from pathlib import Path

import pytest

from auth_fakes import Env

ROOT = Path(__file__).resolve().parents[3]


def _dockerfile() -> str:
    """The image start-up logic: the Dockerfile plus the entrypoint it runs (uvicorn flags)."""
    return (ROOT / "infra" / "Dockerfile").read_text(encoding="utf-8") + (
        ROOT / "infra" / "entrypoint.sh"
    ).read_text(encoding="utf-8")


def test_1_server_header_is_disabled_in_the_image() -> None:
    assert "--no-server-header" in _dockerfile()


@pytest.mark.parametrize(
    "flag", ["--limit-concurrency", "--timeout-keep-alive", "--timeout-graceful-shutdown"]
)
def test_2_uvicorn_limits_are_set_and_tunable(flag: str) -> None:
    assert re.search(rf"{flag} \S*\$\{{UVICORN_\w+:-\d+\}}", _dockerfile()), flag


def test_3_dependencies_are_pinned() -> None:
    project = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    entries = list(project["project"]["dependencies"])
    for extra in project["project"]["optional-dependencies"].values():
        entries.extend(extra)
    unpinned = [e for e in entries if "==" not in e]
    assert not unpinned, unpinned


def test_5_duplicate_origin_header_is_rejected(env: Env) -> None:
    client = env.client()
    token = client.csrf()
    headers = [
        ("Origin", client.ORIGIN),
        ("Origin", "https://evil.example"),
        ("X-CSRF-Token", token),
    ]
    response = client.http.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "x" * 12}, headers=headers
    )
    assert response.status_code == 403
    swapped = client.http.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "x" * 12},
        headers=[
            ("Origin", "https://evil.example"),
            ("Origin", client.ORIGIN),
            ("X-CSRF-Token", token),
        ],
    )
    assert swapped.status_code == 403


def test_5_single_origin_still_accepted(env: Env) -> None:
    assert env.client().login().status_code == 200
