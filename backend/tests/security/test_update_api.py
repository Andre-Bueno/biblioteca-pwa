"""/api/v1/system: authorization, exact shapes, approval rules, generic errors, audit, headers."""

from pathlib import Path

import pytest
from app.domain.errors import ExternalFetchError
from app.domain.release import ConditionalJson
from app.domain.user import Role
from sqlalchemy import text

from auth_fakes import PASSWORD, ApiClient, Env
from library_env import logged_in
from update_fakes import ETAG, REPO, FakeNotifier, FakeReleaseGateway, release_doc

VERSION = "/api/v1/system/version"
CHECK = "/api/v1/system/update/check"
UPDATE = "/api/v1/system/update"
GLOBAL_CSP_PART = "frame-ancestors 'none'"
ADMIN_KEYS = {"current", "update_available", "latest", "checked_at", "webhook_configured", "update"}
LATEST_KEYS = {"tag", "version", "name", "notes", "published_at", "url"}


def make_env(
    db_url: str,
    tmp_path: Path,
    *,
    gateway: FakeReleaseGateway | None = None,
    notifier: FakeNotifier | None = None,
    version: str = "1.0.0",
    **overrides: object,
) -> tuple[Env, FakeReleaseGateway, FakeNotifier | None]:
    gw = gateway or FakeReleaseGateway()
    lib = tmp_path / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    env = Env(db_url, gateway=gw, LIBRARY_PATH=lib, APP_VERSION=version, **overrides)
    env.create_user("alice", PASSWORD)
    env.create_user("root", PASSWORD, role=Role.ADMIN)
    if notifier is not None:
        env.container.__dict__["update_notifier"] = notifier  # a fake instead of the real webhook
    return env, gw, notifier


def admin(env: Env) -> ApiClient:
    return logged_in(env, "root")


def audit_rows(env: Env) -> list[tuple[str, str | None, str]]:
    with env.container.session_factory() as session:
        rows = session.execute(text("SELECT event, user_id, detail FROM audit_log")).all()
    return [(r[0], r[1], str(r[2])) for r in rows if str(r[0]).startswith("system.")]


# ---------------------------------------------------------------- authorization


def test_anonymous_gets_401_everywhere(db_url: str, tmp_path: Path) -> None:
    env, gateway, _ = make_env(db_url, tmp_path)
    anon = env.client()
    anon.csrf()
    assert anon.get(VERSION).status_code == 401
    assert anon.post(CHECK).status_code == 401
    assert anon.post(UPDATE, {"tag": "v1.1.0"}).status_code == 401
    assert gateway.calls == []


def test_a_regular_user_only_learns_the_running_version(db_url: str, tmp_path: Path) -> None:
    env, gateway, _ = make_env(db_url, tmp_path, notifier=FakeNotifier())
    admin(env).get(VERSION)  # the admin triggers the lookup; a user must not see its result
    alice = logged_in(env, "alice")
    response = alice.get(VERSION)
    assert response.status_code == 200
    assert response.json() == {"current": "1.0.0", "update_available": False}
    for text_ in ("v1.1.0", "latest", "webhook", "notes", "checked_at"):
        assert text_ not in response.text


def test_a_regular_user_never_triggers_a_lookup(db_url: str, tmp_path: Path) -> None:
    env, gateway, _ = make_env(db_url, tmp_path)
    logged_in(env, "alice").get(VERSION)
    assert gateway.calls == []


def test_regular_user_is_forbidden_on_both_posts(db_url: str, tmp_path: Path) -> None:
    notifier = FakeNotifier()
    env, gateway, _ = make_env(db_url, tmp_path, notifier=notifier)
    admin(env).get(VERSION)
    alice = logged_in(env, "alice")
    calls = len(gateway.calls)
    assert alice.post(CHECK).status_code == 403
    assert alice.post(UPDATE, {"tag": "v1.1.0"}).status_code == 403
    assert len(gateway.calls) == calls and notifier.sent == []


def test_writes_need_csrf(db_url: str, tmp_path: Path) -> None:
    env, _, _ = make_env(db_url, tmp_path, notifier=FakeNotifier())
    root = admin(env)
    root.get(VERSION)
    plain = {"Origin": root.ORIGIN}  # no X-CSRF-Token
    assert root.http.post(CHECK, headers=plain).status_code == 403
    assert root.http.post(UPDATE, json={"tag": "v1.1.0"}, headers=plain).status_code == 403


# ---------------------------------------------------------------- GET /system/version (admin)


def test_admin_gets_the_full_view(db_url: str, tmp_path: Path) -> None:
    env, gateway, _ = make_env(db_url, tmp_path, notifier=FakeNotifier())
    body = admin(env).get(VERSION).json()
    assert set(body) == ADMIN_KEYS
    assert body["current"] == "1.0.0" and body["update_available"] is True
    assert set(body["latest"]) == LATEST_KEYS
    assert body["latest"]["tag"] == "v1.1.0" and body["latest"]["version"] == "1.1.0"
    assert body["latest"]["url"] == f"https://github.com/{REPO}/releases/tag/v1.1.0"
    assert body["checked_at"] is not None and body["webhook_configured"] is True
    assert body["update"] == {"state": "idle", "tag": None, "requested_at": None}
    assert len(gateway.calls) == 1


def test_admin_view_without_a_webhook(db_url: str, tmp_path: Path) -> None:
    env, _, _ = make_env(db_url, tmp_path)
    assert admin(env).get(VERSION).json()["webhook_configured"] is False


def test_up_to_date_and_dev_builds(db_url: str, tmp_path: Path) -> None:
    env, gateway, _ = make_env(db_url, tmp_path, version="1.1.0")
    body = admin(env).get(VERSION).json()
    assert body["update_available"] is False and body["latest"]["tag"] == "v1.1.0"
    dev, dev_gateway, _ = make_env(db_url + "x", tmp_path / "dev", version="dev")
    body = admin(dev).get(VERSION).json()
    assert body == {
        "current": "dev",
        "update_available": False,
        "latest": None,
        "checked_at": None,
        "webhook_configured": False,
        "update": {"state": "idle", "tag": None, "requested_at": None},
    }
    assert dev_gateway.calls == []  # APP_VERSION=dev: no network
    assert logged_in(dev, "alice").get(VERSION).json() == {
        "current": "dev",
        "update_available": False,
    }


def test_a_lookup_failure_never_breaks_the_route(db_url: str, tmp_path: Path) -> None:
    gateway = FakeReleaseGateway(ExternalFetchError("network"))
    env, _, _ = make_env(db_url, tmp_path, gateway=gateway)
    response = admin(env).get(VERSION)
    assert response.status_code == 200 and response.json()["latest"] is None


def test_release_text_is_plain_text_in_the_response(db_url: str, tmp_path: Path) -> None:
    doc = release_doc(body="<script>alert(1)</script><b>hi</b>‮", name="<i>n</i>")
    gateway = FakeReleaseGateway(ConditionalJson(200, doc, ETAG))
    env, _, _ = make_env(db_url, tmp_path, gateway=gateway)
    latest = admin(env).get(VERSION).json()["latest"]
    for value in (latest["notes"], latest["name"]):
        assert "<" not in value and "‮" not in value and "script" not in value


# ---------------------------------------------------------------- POST /system/update/check


def test_check_forces_a_lookup_and_is_limited_to_three_per_minute(
    db_url: str, tmp_path: Path
) -> None:
    env, gateway, _ = make_env(db_url, tmp_path)
    root = admin(env)
    root.get(VERSION)
    for _ in range(3):
        response = root.post(CHECK)
        assert response.status_code == 200 and set(response.json()) == ADMIN_KEYS
    assert len(gateway.calls) == 4  # the GET, then three forced
    blocked = root.post(CHECK)
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1
    assert blocked.json() == {"detail": "Too many requests"}
    assert len(gateway.calls) == 4


def test_check_limit_is_per_user(db_url: str, tmp_path: Path) -> None:
    env, _, _ = make_env(db_url, tmp_path)
    env.create_user("root2", PASSWORD, role=Role.ADMIN)
    first, second = admin(env), logged_in(env, "root2")
    for _ in range(3):
        assert first.post(CHECK).status_code == 200
    assert first.post(CHECK).status_code == 429
    assert second.post(CHECK).status_code == 200


# ---------------------------------------------------------------- POST /system/update


def test_approving_sends_the_request_and_audits_it(db_url: str, tmp_path: Path) -> None:
    notifier = FakeNotifier()
    env, _, _ = make_env(db_url, tmp_path, notifier=notifier)
    root = admin(env)
    root.get(VERSION)
    response = root.post(UPDATE, {"tag": "v1.1.0"})
    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"state", "tag", "requested_at"}
    assert (body["state"], body["tag"]) == ("requested", "v1.1.0")
    assert [(r.repository, r.tag) for r in notifier.sent] == [(REPO, "v1.1.0")]
    view = root.get(VERSION).json()["update"]
    assert (view["state"], view["tag"]) == ("requested", "v1.1.0") and view["requested_at"]
    rows = audit_rows(env)
    assert [r[0] for r in rows] == ["system.update_requested"]
    assert "v1.1.0" in rows[0][2]


def test_a_second_request_within_ten_minutes_is_a_409(db_url: str, tmp_path: Path) -> None:
    notifier = FakeNotifier()
    env, _, _ = make_env(db_url, tmp_path, notifier=notifier)
    root = admin(env)
    root.get(VERSION)
    assert root.post(UPDATE, {"tag": "v1.1.0"}).status_code == 202
    again = root.post(UPDATE, {"tag": "v1.1.0"})
    assert again.status_code == 409 and again.json() == {
        "detail": "An update was already requested"
    }
    assert len(notifier.sent) == 1
    env.clock.advance(11 * 60)
    assert root.post(UPDATE, {"tag": "v1.1.0"}).status_code == 202


@pytest.mark.parametrize("tag", ["v1.0.9", "v9.9.9", "v1.1.0-rc.1", "v1.1.1"])
def test_a_tag_that_is_not_the_latest_is_a_409(db_url: str, tmp_path: Path, tag: str) -> None:
    notifier = FakeNotifier()
    env, _, _ = make_env(db_url, tmp_path, notifier=notifier)
    root = admin(env)
    root.get(VERSION)
    response = root.post(UPDATE, {"tag": tag})
    assert response.status_code == 409 and response.json() == {
        "detail": "That update is not available"
    }
    assert notifier.sent == [] and audit_rows(env) == []


def test_no_update_without_a_known_release(db_url: str, tmp_path: Path) -> None:
    env, _, _ = make_env(db_url, tmp_path, notifier=FakeNotifier())
    assert admin(env).post(UPDATE, {"tag": "v1.1.0"}).status_code == 409  # never looked up


def test_up_to_date_build_cannot_update(db_url: str, tmp_path: Path) -> None:
    env, _, _ = make_env(db_url, tmp_path, notifier=FakeNotifier(), version="1.1.0")
    root = admin(env)
    root.get(VERSION)
    assert root.post(UPDATE, {"tag": "v1.1.0"}).status_code == 409


def test_dev_build_cannot_update(db_url: str, tmp_path: Path) -> None:
    notifier = FakeNotifier()
    env, gateway, _ = make_env(db_url, tmp_path, notifier=notifier, version="dev")
    root = admin(env)
    root.get(VERSION)
    assert root.post(UPDATE, {"tag": "v1.1.0"}).status_code == 409
    assert gateway.calls == [] and notifier.sent == []


def test_missing_webhook_is_a_503(db_url: str, tmp_path: Path) -> None:
    env, _, _ = make_env(db_url, tmp_path)  # no notifier
    root = admin(env)
    root.get(VERSION)
    response = root.post(UPDATE, {"tag": "v1.1.0"})
    assert response.status_code == 503 and response.json() == {"detail": "Update is not configured"}


def test_a_failing_webhook_is_a_generic_502_audited_without_leaks(
    db_url: str, tmp_path: Path
) -> None:
    env, _, _ = make_env(db_url, tmp_path, notifier=FakeNotifier(fail=True))
    root = admin(env)
    root.get(VERSION)
    response = root.post(UPDATE, {"tag": "v1.1.0"})
    assert response.status_code == 502 and response.json() == {"detail": "Update request failed"}
    assert [r[0] for r in audit_rows(env)] == ["system.update_failed"]
    view = root.get(VERSION).json()["update"]
    assert view == {"state": "failed", "tag": "v1.1.0", "requested_at": None}
    assert root.post(UPDATE, {"tag": "v1.1.0"}).status_code == 502  # may be retried at once


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"tag": ""},
        {"tag": "1.1.0"},
        {"tag": "v1.1"},
        {"tag": "v1.1.0\n"},
        {"tag": "v1.1.0; rm -rf /"},
        {"tag": "v1.1.0-" + "a" * 60},
        {"tag": 1},
        {"tag": None},
        {"tag": ["v1.1.0"]},
        {"tag": "v1.1.0", "url": "https://evil.example/hook"},
        {"tag": "v1.1.0", "webhook": "https://evil.example/hook"},
        {"tag": "v1.1.0", "secret": "x"},
        [],
        "v1.1.0",
    ],
)
def test_invalid_bodies_are_a_generic_422_and_nothing_is_sent(
    db_url: str, tmp_path: Path, body: object
) -> None:
    notifier = FakeNotifier()
    env, _, _ = make_env(db_url, tmp_path, notifier=notifier)
    root = admin(env)
    root.get(VERSION)
    response = root.post(UPDATE, body)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    assert "evil" not in response.text and notifier.sent == []


def test_there_is_no_way_to_change_the_destination_or_roll_back(
    db_url: str, tmp_path: Path
) -> None:
    env, _, _ = make_env(db_url, tmp_path, notifier=FakeNotifier())
    root = admin(env)
    for method, path in (
        ("put", "/api/v1/system/webhook"),
        ("post", "/api/v1/system/webhook"),
        ("put", UPDATE),
        ("delete", UPDATE),
        ("post", "/api/v1/system/rollback"),
        ("post", "/api/v1/system/update/rollback"),
        ("get", "/api/v1/system/update"),
        ("get", "/api/v1/system/update/check"),
    ):
        response = getattr(root, method)(path) if method != "put" else root.put(path, {})
        assert response.status_code in (404, 405), (method, path)


# ---------------------------------------------------------------- headers and leaks


def test_every_system_response_is_no_store_with_the_global_csp(db_url: str, tmp_path: Path) -> None:
    env, _, _ = make_env(db_url, tmp_path, notifier=FakeNotifier())
    root = admin(env)
    responses = [
        root.get(VERSION),
        root.post(CHECK),
        root.post(UPDATE, {"tag": "v1.1.0"}),
        root.post(UPDATE, {"tag": "v1.1.0"}),  # 409
        root.post(UPDATE, {"tag": "nope"}),  # 422
        logged_in(env, "alice").get(VERSION),
        logged_in(env, "alice").post(CHECK),  # 403
        env.client().get(VERSION),  # 401
    ]
    for response in responses:
        assert response.headers.get_list("cache-control") == ["no-store"]
        assert GLOBAL_CSP_PART in response.headers["content-security-policy"]
        assert response.headers["x-content-type-options"] == "nosniff"


def test_no_url_or_secret_in_any_response_or_audit(db_url: str, tmp_path: Path) -> None:
    secret = "a-webhook-secret-of-at-least-32-characters-xyz"  # secret-scan:allow (fictitious)
    env, _, _ = make_env(
        db_url,
        tmp_path,
        notifier=FakeNotifier(fail=True),
        UPDATE_WEBHOOK_URL="https://deploy.example.com/hook-token-77",
        UPDATE_WEBHOOK_SECRET=secret,
    )
    root = admin(env)
    texts = [
        root.get(VERSION).text,
        root.post(CHECK).text,
        root.post(UPDATE, {"tag": "v1.1.0"}).text,
    ]
    texts.append(str(audit_rows(env)))
    for body in texts:
        for forbidden in (secret, "deploy.example.com", "hook-token-77"):
            assert forbidden not in body


def test_release_check_does_not_depend_on_metadata_being_enabled(
    db_url: str, tmp_path: Path
) -> None:
    env, gateway, _ = make_env(db_url, tmp_path, METADATA_ENABLED=False)
    assert admin(env).get(VERSION).json()["latest"]["tag"] == "v1.1.0"
    assert len(gateway.calls) == 1


def test_check_can_be_switched_off(db_url: str, tmp_path: Path) -> None:
    env, gateway, _ = make_env(db_url, tmp_path, UPDATE_CHECK_ENABLED=False)
    body = admin(env).get(VERSION).json()
    assert body["latest"] is None and body["update_available"] is False
    assert gateway.calls == []


def test_end_to_end_with_the_real_webhook_adapter_over_loopback(
    db_url: str, tmp_path: Path
) -> None:
    from test_webhook_notifier import SECRET, feed_receiver, hook_server, load_receiver

    receiver = load_receiver()
    with hook_server() as (url, received):
        env, _, _ = make_env(
            db_url,
            tmp_path,
            UPDATE_WEBHOOK_URL=url,
            UPDATE_WEBHOOK_SECRET=SECRET,
            UPDATE_WEBHOOK_ALLOW_HTTP=True,
        )
        root = admin(env)
        assert root.get(VERSION).json()["webhook_configured"] is True
        assert root.post(UPDATE, {"tag": "v1.1.0"}).status_code == 202
    assert len(received.items) == 1
    # What the app really sent is accepted by the real receiver code (clock: its own `now`).
    item = received.items[0]
    stamp = float(item["headers"]["x-update-timestamp"])  # type: ignore[index]
    response = receiver.process_request(
        config=receiver.Config(
            secret=SECRET.encode(), repository=REPO, compose_file="/c.yml", env_file="/e"
        ),
        nonces=type("N", (), {"consume": lambda self, n: True})(),
        updater=type("U", (), {"try_start": lambda self, t: True})(),
        method="POST",
        path=item["path"],
        headers=item["headers"],
        body=item["body"],
        now=stamp,
    )
    assert response.status == 202
    del feed_receiver


def test_the_real_webhook_failing_is_a_502_without_leaks(db_url: str, tmp_path: Path) -> None:
    from test_webhook_notifier import SECRET, hook_server

    with hook_server(500, b"secret internal detail") as (url, _):
        env, _, _ = make_env(
            db_url,
            tmp_path,
            UPDATE_WEBHOOK_URL=url,
            UPDATE_WEBHOOK_SECRET=SECRET,
            UPDATE_WEBHOOK_ALLOW_HTTP=True,
        )
        root = admin(env)
        root.get(VERSION)
        response = root.post(UPDATE, {"tag": "v1.1.0"})
    assert response.status_code == 502 and response.json() == {"detail": "Update request failed"}
    for forbidden in (SECRET, "127.0.0.1", "internal detail"):
        assert forbidden not in response.text and forbidden not in str(audit_rows(env))
