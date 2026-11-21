"""The update webhook: exact contract of infra/deploy-hook (checked against the real receiver
code), destination policy, redirects, status handling and silence about secrets. Sockets:
loopback only."""

import hashlib
import hmac
import http.server
import importlib.util
import json
import logging
import re
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
from app.adapters.http.webhook_notifier import (
    MAX_RESPONSE_BYTES,
    USER_AGENT,
    WebhookNotifier,
    sign,
)
from app.domain.errors import UpdateNotifyFailed
from app.domain.release import UpdateRequest

SECRET = "s3cret-for-the-update-webhook-0123456789abcdef"  # secret-scan:allow (fictitious)
REPO = "Andre-Bueno/biblioteca-pwa"
NOW = 1_800_000_000.0
REQUESTED_AT = datetime(2027, 1, 15, 8, 0, 0, tzinfo=UTC)
REQUEST = UpdateRequest(REPO, "v1.2.3", REQUESTED_AT)
RECEIVER = Path(__file__).resolve().parents[3] / "infra" / "deploy-hook" / "receiver.py"


class Received:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []


@contextmanager
def hook_server(
    status: int = 202,
    body: bytes = b'{"status":"accepted"}',
    headers: dict[str, str] | None = None,
) -> Iterator[tuple[str, Received]]:
    received = Received()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            received.items.append(
                {
                    "path": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": self.rfile.read(length),
                }
            )
            self.send_response(status)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/update", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def notifier(url: str, **kw: object) -> WebhookNotifier:
    kw.setdefault("allow_http", True)
    kw.setdefault("clock", lambda: NOW)
    return WebhookNotifier(url, SECRET, **kw)  # type: ignore[arg-type]


def load_receiver() -> ModuleType:
    if not RECEIVER.is_file():
        pytest.skip("infra/deploy-hook/receiver.py is not in this checkout")
    name = "deploy_hook_receiver_under_test"
    spec = importlib.util.spec_from_file_location(name, RECEIVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


class FakeNonces:
    def __init__(self) -> None:
        self.seen: set[str] = set()

    def consume(self, nonce: str) -> bool:
        if nonce in self.seen:
            return False
        self.seen.add(nonce)
        return True


class FakeUpdater:
    def __init__(self) -> None:
        self.tags: list[str] = []

    def try_start(self, tag: str) -> bool:
        self.tags.append(tag)
        return True


def receiver_config(module: ModuleType, secret: str = SECRET, repository: str = REPO):  # type: ignore[no-untyped-def]
    return module.Config(
        secret=secret.encode(),
        repository=repository,
        compose_file="/srv/compose.yml",
        env_file="/srv/.env",
    )


def feed_receiver(
    module, received, *, secret=SECRET, repository=REPO, nonces=None, body=None, headers=None
):  # type: ignore[no-untyped-def]
    item = received.items[0]
    updater = FakeUpdater()
    response = module.process_request(
        config=receiver_config(module, secret, repository),
        nonces=nonces or FakeNonces(),
        updater=updater,
        method="POST",
        path=item["path"],
        headers=headers or item["headers"],
        body=item["body"] if body is None else body,
        now=NOW,
    )
    return response, updater


# ---------------------------------------------------------------- the exact contract


def test_the_request_has_exactly_the_contracted_shape() -> None:
    with hook_server() as (url, received):
        notifier(url).notify(REQUEST)
    (item,) = received.items
    body = item["body"]
    payload = json.loads(body)  # type: ignore[arg-type]
    assert list(payload) == ["event", "repository", "tag", "image", "requested_at", "nonce"]
    assert payload["event"] == "update_requested"
    assert payload["repository"] == REPO and payload["tag"] == "v1.2.3"
    assert payload["image"] == "ghcr.io/andre-bueno/biblioteca-pwa:v1.2.3"  # lowercase repository
    assert payload["requested_at"] == "2027-01-15T08:00:00Z"
    assert re.fullmatch(r"[0-9a-f]{32}", payload["nonce"])
    headers = item["headers"]
    assert headers["content-type"] == "application/json"  # type: ignore[index]
    assert headers["x-update-timestamp"] == "1800000000"  # type: ignore[index]
    assert headers["user-agent"] == USER_AGENT  # type: ignore[index]
    assert item["path"] == "/update"
    expected = hmac.new(
        SECRET.encode(),
        b"1800000000." + body,
        hashlib.sha256,  # type: ignore[operator]
    ).hexdigest()
    assert headers["x-update-signature"] == f"sha256={expected}"  # type: ignore[index]
    assert body == json.dumps(payload, separators=(",", ":")).encode()
    assert "cookie" not in headers and "authorization" not in headers  # type: ignore[operator]


def test_each_request_has_a_fresh_nonce() -> None:
    with hook_server() as (url, received):
        n = notifier(url)
        n.notify(REQUEST)
        n.notify(REQUEST)
    nonces = {json.loads(i["body"])["nonce"] for i in received.items}  # type: ignore[arg-type]
    assert len(nonces) == 2


def test_the_receiver_accepts_what_the_app_produces() -> None:
    module = load_receiver()
    with hook_server() as (url, received):
        notifier(url).notify(REQUEST)
    response, updater = feed_receiver(module, received)
    assert (response.status, response.body) == (202, {"status": "accepted"})
    assert updater.tags == ["v1.2.3"]


def test_the_receiver_signature_function_matches_ours() -> None:
    module = load_receiver()
    body = b'{"a":1}'
    assert sign(SECRET, "123", body) == module.sign(SECRET.encode(), "123", body)


def test_the_receiver_rejects_a_tampered_request() -> None:
    module = load_receiver()
    with hook_server() as (url, received):
        notifier(url).notify(REQUEST)
    item = received.items[0]
    body = bytes(item["body"])  # type: ignore[arg-type]
    for position in (0, 10, len(body) // 2, len(body) - 1):
        flipped = bytearray(body)
        flipped[position] ^= 0x01
        response, updater = feed_receiver(module, received, body=bytes(flipped))
        assert response.status == 401 and updater.tags == [], position
    headers = dict(item["headers"])  # type: ignore[arg-type]
    headers["x-update-timestamp"] = "1800000001"  # the timestamp is signed too
    response, _ = feed_receiver(module, received, headers=headers)
    assert response.status == 401
    response, _ = feed_receiver(
        module, received, secret="another-secret-of-more-than-32-characters"
    )
    assert response.status == 401
    response, _ = feed_receiver(module, received, repository="Someone/else")
    assert response.status == 403


def test_the_receiver_refuses_a_replay_and_a_stale_timestamp() -> None:
    module = load_receiver()
    with hook_server() as (url, received):
        notifier(url).notify(REQUEST)
    nonces = FakeNonces()
    assert feed_receiver(module, received, nonces=nonces)[0].status == 202
    assert feed_receiver(module, received, nonces=nonces)[0].status == 409  # replay
    old = WebhookNotifier("http://127.0.0.1:1/x", SECRET, allow_http=True, clock=lambda: NOW - 3600)
    with hook_server() as (url, stale):
        WebhookNotifier(url, SECRET, allow_http=True, clock=lambda: NOW - 3600).notify(REQUEST)
    assert feed_receiver(module, stale)[0].status == 401
    del old


def test_the_receiver_accepts_every_tag_shape_the_app_can_send() -> None:
    module = load_receiver()
    for tag in ("v0.0.1", "v10.20.30", "v1.0.0-rc.1"):
        with hook_server() as (url, received):
            notifier(url).notify(UpdateRequest(REPO, tag, REQUESTED_AT))
        assert feed_receiver(module, received)[0].status == 202, tag


# ---------------------------------------------------------------- answers and failures


@pytest.mark.parametrize("status", [200, 201, 202, 204, 299])
def test_any_2xx_is_success_and_the_body_is_ignored(status: int) -> None:
    with hook_server(status, b"whatever {not json") as (url, _):
        notifier(url).notify(REQUEST)


@pytest.mark.parametrize("status", [301, 302, 307, 400, 401, 403, 404, 409, 500, 503])
def test_other_statuses_fail_generically(status: int) -> None:
    with hook_server(status) as (url, received), pytest.raises(UpdateNotifyFailed) as info:
        notifier(url).notify(REQUEST)
    assert len(received.items) == 1  # a redirect is not followed
    assert str(info.value) == "" and info.value.__cause__ is None


def test_a_redirect_to_another_host_is_not_followed() -> None:
    location = {"Location": "http://127.0.0.1:9/elsewhere"}
    with hook_server(302, headers=location) as (url, received), pytest.raises(UpdateNotifyFailed):
        notifier(url).notify(REQUEST)
    assert len(received.items) == 1


def test_a_huge_answer_is_not_read_beyond_the_cap() -> None:
    with hook_server(202, b"x" * (50 * MAX_RESPONSE_BYTES)) as (url, _):
        notifier(url).notify(REQUEST)  # succeeds: only the status counts


def test_nothing_listening_is_a_generic_failure() -> None:
    with pytest.raises(UpdateNotifyFailed):
        notifier("http://127.0.0.1:1/update").notify(REQUEST)


# ---------------------------------------------------------------- destination policy


def public(host: str, port: int) -> list[str]:
    return ["8.8.8.8"]


def test_http_needs_the_flag() -> None:
    with hook_server() as (url, received), pytest.raises(UpdateNotifyFailed):
        notifier(url, allow_http=False).notify(REQUEST)
    assert received.items == []  # never connected


@pytest.mark.parametrize(
    "resolved",
    [
        ["8.8.8.8"],
        ["10.0.0.5", "8.8.8.8"],
        ["169.254.169.254"],
        ["0.0.0.0"],  # noqa: S104
        [],
        ["::ffff:8.8.8.8"],
    ],
)
def test_http_to_a_name_that_resolves_outside_the_operator_network_is_refused(
    resolved: list[str],
) -> None:
    n = WebhookNotifier(
        "http://deploy.example.com/update",
        SECRET,
        allow_http=True,
        resolver=lambda host, port: resolved,
    )
    with pytest.raises(UpdateNotifyFailed):
        n.notify(REQUEST)


@pytest.mark.parametrize("address", ["8.8.8.8", "169.254.169.254", "0.0.0.0", "100.63.0.1"])  # noqa: S104
def test_http_to_a_public_ip_literal_is_refused(address: str) -> None:
    with pytest.raises(UpdateNotifyFailed):
        WebhookNotifier(f"http://{address}/update", SECRET, allow_http=True).notify(REQUEST)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "192.168.0.9", "100.64.0.7"])
def test_http_policy_accepts_loopback_private_and_cgnat(address: str) -> None:
    n = WebhookNotifier(f"http://{address}:1/update", SECRET, allow_http=True)
    assert n._address() == address  # noqa: SLF001
    named = WebhookNotifier(
        "http://hook.tailnet.example/update",
        SECRET,
        allow_http=True,
        resolver=lambda host, port: [address],
    )
    assert named._address() == address  # noqa: SLF001


def test_the_connection_goes_to_the_checked_address_not_to_a_second_lookup() -> None:
    lookups: list[str] = []

    def resolver(host: str, port: int) -> list[str]:
        lookups.append(host)
        return ["127.0.0.1"]

    with hook_server() as (url, received):
        port = url.rsplit(":", 1)[1].split("/")[0]
        n = WebhookNotifier(
            f"http://hook.internal.example:{port}/update",
            SECRET,
            allow_http=True,
            resolver=resolver,
            clock=lambda: NOW,
        )
        n.notify(REQUEST)
    assert lookups == ["hook.internal.example"]  # resolved once, then pinned
    assert received.items[0]["headers"]["host"].startswith("hook.internal.example")  # type: ignore[index,union-attr]


def test_https_is_accepted_for_any_destination() -> None:
    n = WebhookNotifier(
        "https://deploy.example.com/update", SECRET, resolver=lambda host, port: ["8.8.8.8"]
    )
    assert n._address() == "8.8.8.8"  # noqa: SLF001 - the policy; TLS itself is not opened here


def test_constructor_refuses_a_bad_url() -> None:
    for url in ("ftp://x/y", "https://", "not a url", ""):
        with pytest.raises(ValueError):
            WebhookNotifier(url, SECRET)


# ---------------------------------------------------------------- silence


def test_nothing_sensitive_is_logged_raised_or_shown(caplog: pytest.LogCaptureFixture) -> None:
    url_secret = "token-in-path-9f8e7d6c"
    with caplog.at_level(logging.DEBUG), hook_server(500, b"internal detail") as (url, _):
        n = WebhookNotifier(f"{url}/{url_secret}", SECRET, allow_http=True, clock=lambda: NOW)
        with pytest.raises(UpdateNotifyFailed) as info:
            n.notify(REQUEST)
        with pytest.raises(UpdateNotifyFailed):
            notifier("http://127.0.0.1:1/x/" + url_secret).notify(REQUEST)
    everything = "\n".join(
        [caplog.text, repr(n), str(info.value), repr(info.value), str(info.value.__cause__)]
    )
    for forbidden in (SECRET, url_secret, "127.0.0.1", "internal detail", "sha256=", "nonce"):
        assert forbidden not in everything, forbidden
