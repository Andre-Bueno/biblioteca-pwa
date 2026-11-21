"""Request body size limit (413) under /api, by declared length and by actual bytes."""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.body_limit import BodySizeLimitMiddleware
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from auth_fakes import Env

LIMIT = 64 * 1024


def test_declared_content_length_over_the_limit_is_413(env: Env) -> None:
    client = env.client()
    body = json.dumps({"username": "alice", "password": "x" * (LIMIT + 1)})
    response = client.http.post(
        "/api/v1/auth/login", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
    assert response.headers["cache-control"] == "no-store"
    assert "content-security-policy" in response.headers  # the outer middleware still decorates


def test_default_limit_is_64_kib_and_a_normal_login_still_works(env: Env) -> None:
    assert env.settings.MAX_BODY_BYTES == LIMIT
    assert env.client().login().status_code == 200


def test_body_exactly_at_the_limit_passes_the_size_check(db_url: str) -> None:
    env = Env(db_url, MAX_BODY_BYTES=200)
    client = env.client()
    ok = client.http.post("/api/v1/auth/csrf", content=b"x" * 200)
    assert ok.status_code != 413
    too_big = client.http.post("/api/v1/auth/csrf", content=b"x" * 201)
    assert too_big.status_code == 413


def test_streamed_body_without_content_length_is_cut(db_url: str) -> None:
    env = Env(db_url, MAX_BODY_BYTES=1000)
    client = env.client()

    def chunks() -> Iterator[bytes]:
        for _ in range(50):
            yield b"x" * 100

    headers = {"Origin": client.ORIGIN, "X-CSRF-Token": client.csrf()}
    response = client.http.post("/api/v1/auth/login", content=chunks(), headers=headers)
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


def test_limit_is_configurable(db_url: str) -> None:
    env = Env(db_url, MAX_BODY_BYTES=50)
    env.create_user()
    big = env.client().http.post("/api/v1/auth/login", json={"username": "a" * 80, "password": "p"})
    assert big.status_code == 413


@pytest.mark.parametrize("value", ["abc", "-1", "1e3", "١٢٣", "1 2", "0x10", ""])
def test_invalid_content_length_is_a_generic_400(env: Env, value: str) -> None:
    app = env.app
    seen: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        seen.append(message)

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": [(b"content-length", value.encode("utf-8"))],
    }
    middleware = BodySizeLimitMiddleware(app, max_bytes=LIMIT)
    asyncio.run(middleware(scope, receive, send))
    assert seen[0]["status"] == 400
    assert json.loads(seen[1]["body"]) == {"detail": "Invalid Content-Length"}


def _run(scope_path: str, headers: list[tuple[bytes, bytes]], chunks: list[bytes], limit: int):  # type: ignore[no-untyped-def]
    """Drive the middleware around a minimal app that reads the whole body."""
    consumed: list[int] = []
    sent: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                raise RuntimeError("client went away")
            total += len(message.get("body", b""))
            if not message.get("more_body", False):
                break
        consumed.append(total)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    queue = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
        for i, c in enumerate(chunks)
    ]

    async def receive() -> Message:
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "method": "POST", "path": scope_path, "headers": headers}
    asyncio.run(BodySizeLimitMiddleware(app, max_bytes=limit)(scope, receive, send))
    return consumed, sent


def test_lying_content_length_is_caught_by_counting_bytes() -> None:
    consumed, sent = _run(
        "/api/v1/x", [(b"content-length", b"10")], [b"a" * 60, b"b" * 60, b"c" * 60], 100
    )
    assert consumed == []  # the app never saw a complete oversized body
    assert sent[0]["status"] == 413
    assert len([m for m in sent if m["type"] == "http.response.start"]) == 1  # exactly one answer


def test_chunks_under_the_limit_pass_untouched() -> None:
    consumed, sent = _run("/api/v1/x", [], [b"a" * 40, b"b" * 40], 100)
    assert consumed == [80]
    assert sent[0]["status"] == 200


def test_non_api_paths_are_not_limited() -> None:
    consumed, sent = _run("/something", [(b"content-length", b"999999")], [b"a" * 500], 100)
    assert consumed == [500]
    assert sent[0]["status"] == 200


def test_oversized_body_never_reaches_the_route_handler() -> None:
    app = FastAPI()
    calls: list[int] = []

    @app.post("/api/v1/echo")
    async def echo(request: Request) -> dict[str, int]:
        calls.append(1)
        return {"n": len(await request.body())}

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=100)
    client = TestClient(app)
    assert client.post("/api/v1/echo", content=b"x" * 100).json() == {"n": 100}
    assert client.post("/api/v1/echo", content=b"x" * 101).status_code == 413
    assert len(calls) == 1


def test_limit_applies_to_the_new_routes_too(db_url: str, tmp_path: Path) -> None:
    from library_env import library_env, logged_in

    env, _ = library_env(db_url, tmp_path, scan=False, MAX_BODY_BYTES=100)
    admin = logged_in(env, "root")
    response = admin.post("/api/v1/library/scan", {"junk": "x" * 500})
    assert response.status_code == 413
    assert env.container.scan_runner.status().state.value == "idle"  # nothing was started
