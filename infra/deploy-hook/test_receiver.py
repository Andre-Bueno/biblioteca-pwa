"""Tests for receiver.py. No network (loopback only), no Docker: `python -m unittest`."""

from __future__ import annotations

import http.client
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import unittest
from collections.abc import Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import receiver  # noqa: E402

SECRET = b"unit-test-secret-with-more-than-32-bytes!"
REPO = "Andre-Bueno/biblioteca-pwa"
NOW = 1_800_000_000
NONCE_A = "a" * 32


def setUpModule() -> None:
    logging.disable(logging.CRITICAL)  # keep the test output clean


def tearDownModule() -> None:
    logging.disable(logging.NOTSET)


def make_config(tmp: str, **over: object) -> receiver.Config:
    base: dict[str, object] = {
        "secret": SECRET,
        "repository": REPO,
        "compose_file": os.path.join(tmp, "compose.yml"),
        "env_file": os.path.join(tmp, ".env"),
        "nonce_file": os.path.join(tmp, "state", "nonces.json"),
        "health_timeout": 30.0,
    }
    base.update(over)
    return receiver.Config(**base)  # type: ignore[arg-type]


def payload(**over: object) -> dict[str, object]:
    tag = str(over.get("tag", "v1.2.3"))
    data: dict[str, object] = {
        "event": "update_requested",
        "repository": REPO,
        "tag": tag,
        "image": f"ghcr.io/andre-bueno/biblioteca-pwa:{tag}",
        "requested_at": "2026-11-21T12:00:00Z",
        "nonce": NONCE_A,
    }
    data.update(over)
    return data


def signed(body: bytes, ts: int = NOW, secret: bytes = SECRET) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Update-Timestamp": str(ts),
        "X-Update-Signature": receiver.sign(secret, str(ts), body),
    }


class FakeUpdater:
    def __init__(self, accept: bool = True) -> None:
        self.accept = accept
        self.tags: list[str] = []

    def try_start(self, tag: str) -> bool:
        self.tags.append(tag)
        return self.accept


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = make_config(self.tmp)
        self.nonces = receiver.NonceStore(self.cfg.nonce_file, clock=lambda: float(NOW))
        self.updater = FakeUpdater()

    def post(
        self,
        data: object = None,
        *,
        raw: bytes | None = None,
        headers: dict[str, str] | None = None,
        ts: int = NOW,
        now: float = NOW,
        method: str = "POST",
        path: str = "/update",
    ) -> receiver.Response:
        body = (
            raw if raw is not None else json.dumps(data if data is not None else payload()).encode()
        )
        return receiver.process_request(
            config=self.cfg,
            nonces=self.nonces,
            updater=self.updater,
            method=method,
            path=path,
            headers=headers if headers is not None else signed(body, ts),
            body=body,
            now=now,
        )


class ValidationTests(Base):
    def test_valid_request_is_accepted(self) -> None:
        res = self.post()
        self.assertEqual(res.status, 202)
        self.assertEqual(self.updater.tags, ["v1.2.3"])

    def test_prerelease_tag_is_accepted(self) -> None:
        self.assertEqual(self.post(payload(tag="v1.2.3-rc.1")).status, 202)

    def test_invalid_signature_wrong_secret(self) -> None:
        body = json.dumps(payload()).encode()
        res = self.post(raw=body, headers=signed(body, secret=b"x" * 40))
        self.assertEqual(res.status, 401)
        self.assertEqual(self.updater.tags, [])

    def test_tampered_body_invalid_signature(self) -> None:
        body = json.dumps(payload()).encode()
        headers = signed(body)
        tampered = json.dumps(payload(tag="v9.9.9")).encode()
        self.assertEqual(self.post(raw=tampered, headers=headers).status, 401)

    def test_malformed_or_missing_auth_headers(self) -> None:
        body = json.dumps(payload()).encode()
        good = signed(body)
        cases = {
            "no signature": {k: v for k, v in good.items() if k != "X-Update-Signature"},
            "no timestamp": {k: v for k, v in good.items() if k != "X-Update-Timestamp"},
            "bad prefix": {
                **good,
                "X-Update-Signature": good["X-Update-Signature"].replace("sha256=", "sha1="),
            },
            "uppercase hex": {**good, "X-Update-Signature": good["X-Update-Signature"].upper()},
            "timestamp not numeric": {**good, "X-Update-Timestamp": "12abc"},
            "timestamp negative": {**good, "X-Update-Timestamp": "-5"},
        }
        for name, headers in cases.items():
            with self.subTest(name):
                self.assertEqual(self.post(raw=body, headers=headers).status, 401)

    def test_old_timestamp_rejected(self) -> None:
        self.assertEqual(self.post(ts=NOW - 301).status, 401)

    def test_future_timestamp_rejected(self) -> None:
        self.assertEqual(self.post(ts=NOW + 301).status, 401)

    def test_timestamp_window_edge_accepted(self) -> None:
        self.assertEqual(self.post(ts=NOW - 300).status, 202)

    def test_nonce_replay_rejected(self) -> None:
        self.assertEqual(self.post().status, 202)
        res = self.post()
        self.assertEqual((res.status, res.body["error"]), (409, "replay"))
        self.assertEqual(self.updater.tags, ["v1.2.3"])

    def test_invalid_tags_rejected_and_never_reach_updater(self) -> None:
        bad = [
            "latest",
            "v1.2",
            "1.2.3",
            "v1.2.3\n",
            "v1.2.3 ",
            "v1.2.3; rm -rf /",
            "v1.2.3 && id",
            "v1.2.3\nAPP_TAG=evil",
            "v1.2.3-$(id)",
            "v1.2.3-`id`",
            "v1.2.3-a_b",
            "v1.2.3-",
            "../v1.0.0",
            "v١.٢.٣",  # non-ASCII digits
            "v1.2.3-" + "a" * 100,
            "",
        ]
        for i, tag in enumerate(bad):
            with self.subTest(tag=tag):
                nonce = f"{i:032x}"
                res = self.post(
                    payload(tag=tag, image=f"ghcr.io/andre-bueno/biblioteca-pwa:{tag}", nonce=nonce)
                )
                self.assertEqual(res.status, 400)
        self.assertEqual(self.updater.tags, [])

    def test_non_string_tag_rejected(self) -> None:
        self.assertEqual(self.post(payload(tag=["v1.2.3"])).status, 400)

    def test_wrong_repository_rejected(self) -> None:
        res = self.post(payload(repository="evil/repo"))
        self.assertEqual(res.status, 403)
        self.assertEqual(self.updater.tags, [])

    def test_repository_case_insensitive(self) -> None:
        self.assertEqual(self.post(payload(repository=REPO.lower())).status, 202)

    def test_image_must_match_repository_and_tag(self) -> None:
        for image in (
            "ghcr.io/evil/other:v1.2.3",
            "ghcr.io/andre-bueno/biblioteca-pwa:v9.9.9",
            "docker.io/x:v1.2.3",
        ):
            with self.subTest(image=image):
                self.assertEqual(self.post(payload(image=image)).status, 400)
        self.assertEqual(self.updater.tags, [])

    def test_invalid_nonce_rejected(self) -> None:
        for nonce in ("short", "A" * 32, "g" * 32, "a" * 33, 123):
            with self.subTest(nonce=nonce):
                self.assertEqual(self.post(payload(nonce=nonce)).status, 400)

    def test_wrong_event_and_bad_requested_at(self) -> None:
        self.assertEqual(self.post(payload(event="other")).status, 400)
        self.assertEqual(self.post(payload(requested_at="not a date", nonce="b" * 32)).status, 400)

    def test_oversized_body_rejected(self) -> None:
        big = json.dumps(payload(requested_at="2026-11-21T12:00:00Z" + "x" * 20000)).encode()
        self.assertGreater(len(big), receiver.MAX_BODY_BYTES)
        self.assertEqual(self.post(raw=big).status, 413)
        self.assertEqual(self.updater.tags, [])

    def test_malformed_json_with_valid_signature(self) -> None:
        for raw in (b"{not json", b"", b"[1,2]", b'"text"', b"\xff\xfe\x00", b"[" * 5000):
            with self.subTest(raw=raw[:10]):
                self.assertEqual(self.post(raw=raw).status, 400)

    def test_missing_fields(self) -> None:
        data = payload()
        del data["nonce"]
        self.assertEqual(self.post(data).status, 400)

    def test_content_type_must_be_json(self) -> None:
        body = json.dumps(payload()).encode()
        headers = {**signed(body), "Content-Type": "text/plain"}
        self.assertEqual(self.post(raw=body, headers=headers).status, 415)
        headers = {**signed(body), "Content-Type": "application/json; charset=utf-8"}
        self.assertEqual(self.post(raw=body, headers=headers).status, 202)

    def test_method_and_path(self) -> None:
        self.assertEqual(self.post(method="GET").status, 405)
        self.assertEqual(self.post(path="/other").status, 404)

    def test_busy_returns_409(self) -> None:
        self.updater.accept = False
        res = self.post()
        self.assertEqual((res.status, res.body["error"]), (409, "busy"))

    def test_nonce_store_full_fails_closed(self) -> None:
        self.nonces = receiver.NonceStore(
            self.cfg.nonce_file, max_entries=1, clock=lambda: float(NOW)
        )
        self.assertEqual(self.post().status, 202)
        self.assertEqual(self.post(payload(nonce="b" * 32)).status, 503)

    def test_unauthenticated_requests_do_not_consume_nonces(self) -> None:
        body = json.dumps(payload()).encode()
        self.post(raw=body, headers=signed(body, secret=b"y" * 40))
        self.assertEqual(self.post().status, 202)


class NonceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "n", "nonces.json")

    def test_ttl_expiry(self) -> None:
        clock = [1000.0]
        store = receiver.NonceStore(self.path, ttl=600, clock=lambda: clock[0])
        self.assertTrue(store.consume("a" * 32))
        clock[0] = 1599.0
        self.assertFalse(store.consume("a" * 32))
        clock[0] = 1601.0
        self.assertTrue(store.consume("a" * 32))

    def test_persists_across_instances(self) -> None:
        receiver.NonceStore(self.path, clock=lambda: 1000.0).consume("c" * 32)
        self.assertFalse(receiver.NonceStore(self.path, clock=lambda: 1001.0).consume("c" * 32))

    def test_corrupt_file_is_treated_as_empty(self) -> None:
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{broken")
        self.assertTrue(receiver.NonceStore(self.path, clock=lambda: 1000.0).consume("d" * 32))

    def test_concurrent_same_nonce_only_once(self) -> None:
        store = receiver.NonceStore(self.path, clock=lambda: 1000.0)
        results: list[bool] = []
        threads = [
            threading.Thread(target=lambda: results.append(store.consume("e" * 32)))
            for _ in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(True), 1)


class EnvFileTests(unittest.TestCase):
    def test_replace_dedupe_and_append(self) -> None:
        text = "OTHER_SETTING=abc\nAPP_TAG=v0.1.0\nOTHER=1\nAPP_TAG=v0.0.1\n"
        self.assertEqual(
            receiver.set_app_tag(text, "v1.0.0"), "OTHER_SETTING=abc\nAPP_TAG=v1.0.0\nOTHER=1\n"
        )
        self.assertEqual(receiver.set_app_tag("A=1", "v1.0.0"), "A=1\nAPP_TAG=v1.0.0\n")
        self.assertEqual(receiver.set_app_tag("", "v1.0.0"), "APP_TAG=v1.0.0\n")

    def test_commented_line_is_kept(self) -> None:
        out = receiver.set_app_tag("# APP_TAG=v0.0.1\n", "v1.0.0")
        self.assertEqual(out, "# APP_TAG=v0.0.1\nAPP_TAG=v1.0.0\n")

    def test_injection_refused(self) -> None:
        for tag in ("v1.0.0\nOTHER_SETTING=x", "latest", "v1.0.0 "):
            with self.assertRaises(ValueError):
                receiver.set_app_tag("A=1\n", tag)

    def test_child_env_scrubs_hook_settings_and_app_tag(self) -> None:
        env = receiver.child_env(
            {"PATH": "/bin", "UPDATE_HOOK_SECRET": "s", "UPDATE_HOOK_PORT": "1", "APP_TAG": "x"}
        )
        self.assertEqual(env, {"PATH": "/bin"})


class FakeRunner:
    """Scripted docker. `health` is a list of inspect outputs per call (last repeats)."""

    def __init__(
        self, env_file: str, *, pull_rc: int = 0, up_rc: int = 0, new_tag_health: str = "healthy"
    ) -> None:
        self.env_file = env_file
        self.pull_rc = pull_rc
        self.up_rc = up_rc
        self.new_tag_health = new_tag_health
        self.calls: list[list[str]] = []
        self.env_at_up: list[str] = []
        self.block: threading.Event | None = None
        self.entered = threading.Event()

    def __call__(self, args: Sequence[str], timeout: float) -> receiver.CmdResult:
        self.calls.append(list(args))
        if self.block is not None:
            self.entered.set()
            self.block.wait(5)
        if "pull" in args:
            return receiver.CmdResult(self.pull_rc, "", "pull error" if self.pull_rc else "")
        if "up" in args:
            with open(self.env_file, encoding="utf-8") as handle:
                self.env_at_up.append(handle.read())
            return receiver.CmdResult(self.up_rc, "", "up error" if self.up_rc else "")
        if "ps" in args:
            return receiver.CmdResult(0, "0123456789abcdef\n")
        if "inspect" in args:
            new = "APP_TAG=v2.0.0" in self.env_at_up[-1]
            return receiver.CmdResult(
                0, "running " + (self.new_tag_health if new else "healthy") + "\n"
            )
        raise AssertionError(f"unexpected command {args}")


class UpdaterTests(unittest.TestCase):
    ORIGINAL = "OTHER_SETTING=keep-me\nAPP_TAG=v1.0.0\n"

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = make_config(self.tmp)
        with open(self.cfg.env_file, "w", encoding="utf-8") as handle:
            handle.write(self.ORIGINAL)
        self.clock = [0.0]

    def updater(self, runner: FakeRunner) -> receiver.Updater:
        def sleep(seconds: float) -> None:
            self.clock[0] += seconds

        return receiver.Updater(
            self.cfg, runner=runner, sleep=sleep, monotonic=lambda: self.clock[0]
        )

    def env_text(self) -> str:
        with open(self.cfg.env_file, encoding="utf-8") as handle:
            return handle.read()

    def test_success_writes_tag_and_runs_pull_then_up_without_shell(self) -> None:
        runner = FakeRunner(self.cfg.env_file)
        self.assertTrue(self.updater(runner).update("v2.0.0"))
        self.assertEqual(self.env_text(), "OTHER_SETTING=keep-me\nAPP_TAG=v2.0.0\n")
        verbs = [c[c.index("--env-file") + 2] for c in runner.calls if "compose" in c]
        self.assertEqual(verbs[:2], ["pull", "up"])
        for call in runner.calls:
            self.assertIsInstance(call, list)
            self.assertTrue(all(isinstance(a, str) for a in call))
            self.assertEqual(call[0], "docker")
            self.assertNotIn("v2.0.0", " ".join(call))  # the tag only travels through the env file

    def test_unhealthy_new_version_rolls_back(self) -> None:
        runner = FakeRunner(self.cfg.env_file, new_tag_health="unhealthy")
        self.assertFalse(self.updater(runner).update("v2.0.0"))
        self.assertEqual(self.env_text(), self.ORIGINAL)
        self.assertEqual(len(runner.env_at_up), 2)
        self.assertIn("APP_TAG=v2.0.0", runner.env_at_up[0])
        self.assertIn("APP_TAG=v1.0.0", runner.env_at_up[1])

    def test_never_healthy_times_out_and_rolls_back(self) -> None:
        runner = FakeRunner(self.cfg.env_file, new_tag_health="starting")
        self.assertFalse(self.updater(runner).update("v2.0.0"))
        self.assertEqual(self.env_text(), self.ORIGINAL)
        self.assertGreaterEqual(self.clock[0], self.cfg.health_timeout)

    def test_pull_failure_restores_env_file(self) -> None:
        runner = FakeRunner(self.cfg.env_file, pull_rc=1)
        self.assertFalse(self.updater(runner).update("v2.0.0"))
        self.assertEqual(self.env_text(), self.ORIGINAL)

    def test_up_failure_rolls_back(self) -> None:
        runner = FakeRunner(self.cfg.env_file, up_rc=1)
        self.assertFalse(self.updater(runner).update("v2.0.0"))
        self.assertEqual(self.env_text(), self.ORIGINAL)

    def test_missing_env_file_changes_nothing(self) -> None:
        os.remove(self.cfg.env_file)
        runner = FakeRunner(self.cfg.env_file)
        self.assertFalse(self.updater(runner).update("v2.0.0"))
        self.assertEqual(runner.calls, [])

    def test_update_refuses_invalid_tag(self) -> None:
        runner = FakeRunner(self.cfg.env_file)
        with self.assertRaises(ValueError):
            self.updater(runner).update("v1.0.0\nX=1")
        self.assertEqual(self.env_text(), self.ORIGINAL)

    def test_only_one_update_at_a_time(self) -> None:
        runner = FakeRunner(self.cfg.env_file)
        runner.block = threading.Event()
        updater = self.updater(runner)
        self.assertTrue(updater.try_start("v2.0.0"))
        self.assertTrue(runner.entered.wait(5))
        self.assertFalse(updater.try_start("v3.0.0"))
        runner.block.set()
        updater.join(10)
        self.assertEqual(self.env_text(), "OTHER_SETTING=keep-me\nAPP_TAG=v2.0.0\n")
        self.assertTrue(updater.try_start("v2.0.0"))  # lock released afterwards
        updater.join(10)


class ConfigTests(unittest.TestCase):
    def env(self, **over: str) -> dict[str, str]:
        base = {
            "UPDATE_HOOK_SECRET": SECRET.decode(),
            "UPDATE_HOOK_REPOSITORY": REPO,
            "UPDATE_HOOK_COMPOSE_FILE": os.path.abspath("compose.yml"),
            "UPDATE_HOOK_ENV_FILE": os.path.abspath(".env"),
        }
        base.update(over)
        return base

    def test_defaults_are_loopback(self) -> None:
        cfg = receiver.Config.from_env(self.env())
        self.assertEqual((cfg.bind, cfg.port, cfg.project), ("127.0.0.1", 9110, "livros"))
        self.assertEqual(cfg.image_repository, "ghcr.io/andre-bueno/biblioteca-pwa")

    def test_invalid_configs_are_refused_without_leaking_the_secret(self) -> None:
        cases = [
            self.env(UPDATE_HOOK_SECRET="short"),
            self.env(UPDATE_HOOK_REPOSITORY="not-a-repo"),
            self.env(UPDATE_HOOK_REPOSITORY="a/b; id"),
            self.env(UPDATE_HOOK_COMPOSE_FILE="relative.yml"),
            self.env(UPDATE_HOOK_ENV_FILE=""),
            self.env(UPDATE_HOOK_PROJECT="Bad Name"),
            self.env(UPDATE_HOOK_BIND="not-an-ip"),
            self.env(UPDATE_HOOK_PORT="0"),
            self.env(UPDATE_HOOK_PORT="abc"),
        ]
        for env in cases:
            with self.subTest(env=env.get("UPDATE_HOOK_REPOSITORY")):
                with self.assertRaises(receiver.ConfigError) as ctx:
                    receiver.Config.from_env(env)
                self.assertNotIn(env["UPDATE_HOOK_SECRET"], str(ctx.exception))
        env = self.env()
        del env["UPDATE_HOOK_SECRET"]
        with self.assertRaises(receiver.ConfigError):
            receiver.Config.from_env(env)


class HttpTests(Base):
    """A few requests through the real HTTP server on loopback."""

    def setUp(self) -> None:
        super().setUp()
        self.cfg = make_config(self.tmp, bind="127.0.0.1", port=0)
        self.server = receiver.make_server(
            self.cfg, receiver.NonceStore(self.cfg.nonce_file), self.updater
        )
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def request(
        self, method: str, path: str, body: bytes | None, headers: dict[str, str]
    ) -> tuple[int, dict[str, str]]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            return resp.status, json.loads(resp.read().decode())
        finally:
            conn.close()

    def test_signed_request_gets_202(self) -> None:
        body = json.dumps(payload()).encode()
        status, _ = self.request(
            "POST", "/update", body, signed(body, ts=int(__import__("time").time()))
        )
        self.assertEqual(status, 202)
        self.assertEqual(self.updater.tags, ["v1.2.3"])

    def test_huge_content_length_gets_413_without_reading(self) -> None:
        headers = {"Content-Type": "application/json", "Content-Length": "100000000"}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest("POST", "/update")
            for key, value in headers.items():
                conn.putheader(key, value)
            conn.endheaders()
            resp = conn.getresponse()
            self.assertEqual(resp.status, 413)
        finally:
            conn.close()

    def test_get_gets_405_and_missing_length_411(self) -> None:
        self.assertEqual(self.request("GET", "/update", None, {})[0], 405)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest("POST", "/update")
            conn.putheader("Content-Type", "application/json")
            conn.endheaders()
            self.assertEqual(conn.getresponse().status, 411)
        finally:
            conn.close()

    def test_unsigned_request_gets_401(self) -> None:
        body = json.dumps(payload()).encode()
        status, _ = self.request("POST", "/update", body, {"Content-Type": "application/json"})
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
