import asyncio
import logging

import pytest
from app.api.security_headers import SecurityHeadersMiddleware
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect
from starlette.responses import Response
from starlette.types import Message, Receive, Scope, Send

EXPECTED_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
    "connect-src 'self'; worker-src 'self'; manifest-src 'self'; font-src 'self'; "
    "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def test_security_headers_present(client: TestClient) -> None:
    headers = client.get("/api/v1/health").headers
    assert headers["content-security-policy"] == EXPECTED_CSP
    assert "unsafe-inline" not in headers["content-security-policy"]
    assert "unsafe-eval" not in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in headers["permissions-policy"]


def test_security_headers_on_404(client: TestClient) -> None:
    response = client.get("/nao-existe")
    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == EXPECTED_CSP


def test_unhandled_exception_returns_generic_500_with_headers() -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail /etc/passwd")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert "secret" not in response.text
    assert "Traceback" not in response.text
    assert response.headers["content-security-policy"] == EXPECTED_CSP
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_exception_after_response_started_is_reraised() -> None:
    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("late failure")

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    async def receive() -> Message:
        return {"type": "http.request"}

    middleware = SecurityHeadersMiddleware(inner)
    with pytest.raises(RuntimeError):
        asyncio.run(middleware({"type": "http"}, receive, send))
    assert [m["status"] for m in sent if m["type"] == "http.response.start"] == [200]


async def _noop_receive() -> Message:
    return {"type": "http.request"}


def test_cancelled_error_is_not_swallowed() -> None:
    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        raise asyncio.CancelledError

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = SecurityHeadersMiddleware(inner)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(middleware({"type": "http"}, _noop_receive, send))
    assert sent == []  # no fake 500 for a cancellation


@pytest.mark.parametrize("exc", [ClientDisconnect(), BrokenPipeError("pipe")])
def test_disconnect_after_start_is_reraised_without_error_log(
    caplog: pytest.LogCaptureFixture, exc: Exception
) -> None:
    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise exc

    async def send(message: Message) -> None:
        return None

    middleware = SecurityHeadersMiddleware(inner)
    with (
        caplog.at_level(logging.DEBUG, logger="app.api.security_headers"),
        pytest.raises(type(exc)),
    ):
        asyncio.run(middleware({"type": "http"}, _noop_receive, send))
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_real_error_after_start_is_logged_and_reraised(caplog: pytest.LogCaptureFixture) -> None:
    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("late failure")

    async def send(message: Message) -> None:
        return None

    middleware = SecurityHeadersMiddleware(inner)
    with (
        caplog.at_level(logging.ERROR, logger="app.api.security_headers"),
        pytest.raises(RuntimeError),
    ):
        asyncio.run(middleware({"type": "http"}, _noop_receive, send))
    assert [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_preexisting_security_headers_are_replaced() -> None:
    app = FastAPI()

    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/weak-headers")
    def weak_headers() -> Response:
        return Response(
            "x",
            headers={
                "Content-Security-Policy": "default-src *; style-src 'unsafe-inline'",
                "X-Content-Type-Options": "sniff",
            },
        )

    response = TestClient(app).get("/weak-headers")
    assert response.headers["content-security-policy"] == EXPECTED_CSP
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers.get_list("content-security-policy") == [EXPECTED_CSP]
