"""Static checks of the packaging files (the image itself is validated by building it)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_entrypoint_is_lf_only_and_strict() -> None:
    raw = (ROOT / "infra" / "entrypoint.sh").read_bytes()
    assert b"\r" not in raw  # a CRLF shebang breaks the container
    text = raw.decode()
    assert text.startswith("#!/bin/sh\n")
    assert "set -eu" in text
    assert "python -m app.cli migrate" in text
    assert "exec uvicorn" in text


def test_gitattributes_forces_lf_for_shell_scripts() -> None:
    assert re.search(r"^\*\.sh\s+text\s+eol=lf\s*$", _text(".gitattributes"), re.MULTILINE)


def test_dockerfile_is_pinned_non_root_and_serves_the_frontend() -> None:
    text = _text("infra/Dockerfile")
    for line in text.splitlines():
        if line.startswith("FROM "):
            assert ":latest" not in line
            assert re.search(r":\d+\.\d+\.\d+", line), line  # exact version, never a floating tag
    assert re.search(r"^FROM node:24\.\d+\.\d+-slim AS ", text, re.MULTILINE)
    assert "npm ci" in text
    assert "FRONTEND_DIST_DIR=/app/static" in text
    assert "MIGRATIONS_DIR=/app/migrations" in text
    assert re.search(r"^USER app$", text, re.MULTILINE)
    assert "HEALTHCHECK" in text
    assert "SECRET_KEY=" not in text


def test_constraints_pin_every_runtime_dependency() -> None:
    pins = _text("infra/constraints.txt")
    for name in ("fastapi", "uvicorn", "sqlalchemy", "alembic", "argon2-cffi", "pyjwt"):
        assert re.search(rf"^{name}==", pins, re.MULTILINE | re.IGNORECASE), name


def test_compose_hardening() -> None:
    text = _text("infra/compose.example.yml")
    for needle in (
        "read_only: true",
        "no-new-privileges:true",
        "cap_drop:",
        "restart: unless-stopped",
        ":/library:ro",
        "${BIND_ADDRESS:-127.0.0.1}",
        "COOKIE_SECURE: ${COOKIE_SECURE:-true}",
    ):
        assert needle in text, needle


def test_dockerignore_keeps_sources_in_and_secrets_out() -> None:
    lines = {line.strip() for line in _text(".dockerignore").splitlines()}
    assert "frontend" not in lines  # the frontend is built inside the image
    assert {"frontend/node_modules", "frontend/dist", ".env", ".git"} <= lines
    assert "!infra/entrypoint.sh" in lines and "!infra/constraints.txt" in lines
