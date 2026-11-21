#!/usr/bin/env python3
"""Reference receiver for the "update requested" webhook (runs on the HOST, not in the container).

The app POSTs a signed JSON body here after the admin approves an update. This process verifies
the request and then runs `docker compose pull` + `docker compose up -d` for the requested release
tag, rolling back to the previous tag if the container does not become healthy.

Pure standard library. No shell is ever used: every command is a list of arguments.
See README.md in this folder for the contract and the setup.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import signal
import socket
import subprocess  # noqa: S404 - arguments are always a list, shell is never used
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

LOG = logging.getLogger("deploy-hook")

MAX_BODY_BYTES = 16 * 1024
TIMESTAMP_WINDOW_SECONDS = 300
NONCE_TTL_SECONDS = 2 * TIMESTAMP_WINDOW_SECONDS
MAX_NONCES = 5000
MIN_SECRET_BYTES = 32
REGISTRY = "ghcr.io"
UPDATE_PATH = "/update"
SOCKET_TIMEOUT_SECONDS = 10

# re.ASCII: \d must not match other Unicode digits. Always fullmatch, never "$" (it accepts a
# trailing newline).
TAG_RE = re.compile(r"v\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?", re.ASCII)
NONCE_RE = re.compile(r"[0-9a-f]{32}", re.ASCII)
REPO_RE = re.compile(r"[A-Za-z0-9._-]{1,100}/[A-Za-z0-9._-]{1,100}", re.ASCII)
SIGNATURE_RE = re.compile(r"sha256=([0-9a-f]{64})", re.ASCII)
TIMESTAMP_RE = re.compile(r"[0-9]{1,12}", re.ASCII)
NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}", re.ASCII)
CONTAINER_ID_RE = re.compile(r"[0-9a-f]{12,64}", re.ASCII)
MAX_TAG_LENGTH = 64


class ConfigError(Exception):
    """Invalid configuration. The message never contains the secret."""


@dataclass(frozen=True)
class Config:
    secret: bytes
    repository: str
    compose_file: str
    env_file: str
    project: str = "livros"
    service: str = "backend"
    bind: str = "127.0.0.1"
    port: int = 9110
    nonce_file: str = ""
    docker: str = "docker"
    health_timeout: float = 180.0
    pull_timeout: float = 900.0
    up_timeout: float = 300.0

    @staticmethod
    def from_env(env: Mapping[str, str]) -> Config:
        secret = env.get("UPDATE_HOOK_SECRET", "").encode("utf-8")
        if len(secret) < MIN_SECRET_BYTES:
            raise ConfigError(f"UPDATE_HOOK_SECRET is required (min {MIN_SECRET_BYTES} bytes)")
        repository = env.get("UPDATE_HOOK_REPOSITORY", "")
        if not REPO_RE.fullmatch(repository):
            raise ConfigError("UPDATE_HOOK_REPOSITORY must look like owner/name")
        compose_file = env.get("UPDATE_HOOK_COMPOSE_FILE", "")
        env_file = env.get("UPDATE_HOOK_ENV_FILE", "")
        for label, value in (
            ("UPDATE_HOOK_COMPOSE_FILE", compose_file),
            ("UPDATE_HOOK_ENV_FILE", env_file),
        ):
            if not value or not os.path.isabs(value):
                raise ConfigError(f"{label} must be an absolute path")
        project = env.get("UPDATE_HOOK_PROJECT", "livros")
        service = env.get("UPDATE_HOOK_SERVICE", "backend")
        if not NAME_RE.fullmatch(project) or not NAME_RE.fullmatch(service):
            raise ConfigError(
                "UPDATE_HOOK_PROJECT / UPDATE_HOOK_SERVICE: lowercase letters, digits, - and _"
            )
        bind = env.get("UPDATE_HOOK_BIND", "127.0.0.1")
        try:
            ipaddress.ip_address(bind)
        except ValueError as exc:
            raise ConfigError("UPDATE_HOOK_BIND must be an IP address") from exc
        try:
            port = int(env.get("UPDATE_HOOK_PORT", "9110"))
        except ValueError as exc:
            raise ConfigError("UPDATE_HOOK_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ConfigError("UPDATE_HOOK_PORT out of range")
        nonce_file = env.get("UPDATE_HOOK_NONCE_FILE") or os.path.join(
            os.path.expanduser("~"), ".deploy-hook", "nonces.json"
        )
        try:
            health_timeout = float(env.get("UPDATE_HOOK_HEALTH_TIMEOUT", "180"))
        except ValueError as exc:
            raise ConfigError("UPDATE_HOOK_HEALTH_TIMEOUT must be a number") from exc
        if not 5 <= health_timeout <= 1800:
            raise ConfigError("UPDATE_HOOK_HEALTH_TIMEOUT must be between 5 and 1800 seconds")
        return Config(
            secret=secret,
            repository=repository,
            compose_file=compose_file,
            env_file=env_file,
            project=project,
            service=service,
            bind=bind,
            port=port,
            nonce_file=nonce_file,
            docker=env.get("UPDATE_HOOK_DOCKER", "docker") or "docker",
            health_timeout=health_timeout,
        )

    @property
    def image_repository(self) -> str:
        """GHCR needs the lowercase name (same derivation as the release workflow)."""
        return f"{REGISTRY}/{self.repository.lower()}"


def sign(secret: bytes, timestamp: str, body: bytes) -> str:
    """`X-Update-Signature` value: sha256=hex(HMAC_SHA256(secret, timestamp + "." + body))."""
    mac = hmac.new(secret, timestamp.encode("ascii") + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def atomic_write(
    path: str, data: str, mode_from: str | None = None, default_mode: int = 0o600
) -> None:
    """Write `data` to `path` atomically (temp file in the same folder + replace)."""
    directory = os.path.dirname(path) or "."
    mode = default_mode
    if mode_from and os.path.exists(mode_from):
        mode = os.stat(mode_from).st_mode & 0o777
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


class NonceStoreFull(Exception):
    pass


class NonceStore:
    """Remembers used nonces for `ttl` seconds in a small JSON file (nonce -> unix time seen)."""

    def __init__(
        self,
        path: str,
        ttl: int = NONCE_TTL_SECONDS,
        max_entries: int = MAX_NONCES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = path
        self._ttl = ttl
        self._max = max_entries
        self._clock = clock
        self._lock = threading.Lock()

    def _load(self) -> dict[str, float]:
        try:
            with open(self._path, encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            LOG.warning("nonce file unreadable; starting empty")
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            k: float(v)
            for k, v in raw.items()
            if isinstance(k, str) and isinstance(v, (int, float))
        }

    def consume(self, nonce: str) -> bool:
        """True if the nonce is new (and now recorded); False if it was already used."""
        with self._lock:
            now = self._clock()
            seen = {k: v for k, v in self._load().items() if now - v < self._ttl}
            if nonce in seen:
                return False
            if len(seen) >= self._max:
                raise NonceStoreFull
            seen[nonce] = now
            directory = os.path.dirname(self._path) or "."
            os.makedirs(directory, mode=0o700, exist_ok=True)
            atomic_write(self._path, json.dumps(seen))
            return True


@dataclass(frozen=True)
class CmdResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[Sequence[str], float], CmdResult]


def child_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment for docker: no hook settings (secret) and no APP_TAG.

    A process-level APP_TAG would override the value written to the env file (compose gives the
    process environment precedence over --env-file), so it is removed.
    """
    source = os.environ if environ is None else environ
    return {k: v for k, v in source.items() if not k.startswith("UPDATE_HOOK_") and k != "APP_TAG"}


def subprocess_runner(args: Sequence[str], timeout: float) -> CmdResult:
    try:
        done = subprocess.run(  # noqa: S603 - list of args, shell=False
            list(args),
            shell=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=child_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CmdResult(124, "", "timeout")
    except OSError as exc:
        return CmdResult(127, "", type(exc).__name__)
    return CmdResult(done.returncode, done.stdout or "", done.stderr or "")


def set_app_tag(text: str, tag: str) -> str:
    """Return the env-file text with a single `APP_TAG=<tag>` line (other lines are kept as is)."""
    if not TAG_RE.fullmatch(tag):
        raise ValueError("invalid tag")
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if text.count("\r\n") > text.count("\n") - text.count("\r\n") else "\n"
    out: list[str] = []
    placed = False
    for line in lines:
        if re.match(r"\s*APP_TAG\s*=", line):
            if not placed:
                out.append(f"APP_TAG={tag}{newline}")
                placed = True
            continue
        out.append(line)
    if not placed:
        if out and not out[-1].endswith(("\n", "\r")):
            out[-1] += newline
        out.append(f"APP_TAG={tag}{newline}")
    return "".join(out)


def _tail(text: str, limit: int = 300) -> str:
    return " ".join(text.split())[-limit:]


class Updater:
    """Runs one update at a time: env file -> pull -> up -> wait healthy; rolls back on failure."""

    def __init__(
        self,
        config: Config,
        runner: Runner = subprocess_runner,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cfg = config
        self._run = runner
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def _compose(self, *args: str) -> list[str]:
        c = self._cfg
        return [
            c.docker,
            "compose",
            "-p",
            c.project,
            "-f",
            c.compose_file,
            "--env-file",
            c.env_file,
            *args,
        ]

    def _wait_healthy(self) -> bool:
        c = self._cfg
        deadline = self._monotonic() + c.health_timeout
        while True:
            ps = self._run(self._compose("ps", "-q", c.service), 30)
            first = ps.stdout.split()[0] if ps.returncode == 0 and ps.stdout.split() else ""
            if CONTAINER_ID_RE.fullmatch(first):
                fmt = (
                    "{{.State.Status}} "
                    "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"
                )
                info = self._run([c.docker, "inspect", "--format", fmt, first], 30)
                parts = info.stdout.split()
                if info.returncode == 0 and len(parts) == 2:
                    status, health = parts
                    if health == "healthy" and status == "running":
                        return True
                    if health == "unhealthy" or status in ("exited", "dead"):
                        return False
            if self._monotonic() >= deadline:
                return False
            self._sleep(3)

    def _apply(self, pull: bool) -> bool:
        c = self._cfg
        if pull:
            res = self._run(self._compose("pull"), c.pull_timeout)
            if res.returncode != 0:
                LOG.error("compose pull failed (code %s): %s", res.returncode, _tail(res.stderr))
                return False
        res = self._run(self._compose("up", "-d"), c.up_timeout)
        if res.returncode != 0:
            LOG.error("compose up failed (code %s): %s", res.returncode, _tail(res.stderr))
            return False
        return self._wait_healthy()

    def update(self, tag: str) -> bool:
        """Synchronous update. True on success; False if it rolled back (or failed early)."""
        if not TAG_RE.fullmatch(tag) or len(tag) > MAX_TAG_LENGTH:
            raise ValueError("invalid tag")
        env_file = self._cfg.env_file
        try:
            with open(env_file, encoding="utf-8", newline="") as handle:
                original = handle.read()
        except OSError as exc:
            LOG.error("cannot read the env file (%s); nothing changed", type(exc).__name__)
            return False
        LOG.info("update to %s: started", tag)
        atomic_write(env_file, set_app_tag(original, tag), mode_from=env_file)
        if self._apply(pull=True):
            LOG.info("update to %s: container healthy", tag)
            return True
        LOG.error("update to %s: failed; rolling back to the previous APP_TAG", tag)
        atomic_write(env_file, original, mode_from=env_file)
        if self._apply(pull=False):
            LOG.warning("rollback finished: previous version is healthy")
        else:
            LOG.error("rollback FAILED: the service needs manual attention")
        return False

    def try_start(self, tag: str) -> bool:
        """Start an update in the background. False if another one is running (one at a time)."""
        if not self._lock.acquire(blocking=False):
            return False

        def work() -> None:
            try:
                self.update(tag)
            except Exception as exc:  # the worker must never die silently with the lock held
                LOG.error("update crashed: %s", type(exc).__name__)
            finally:
                self._lock.release()

        try:
            self._thread = threading.Thread(target=work, name="deploy-hook-update")
            self._thread.start()
        except BaseException:
            self._lock.release()
            raise
        return True

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)


@dataclass(frozen=True)
class Response:
    status: int
    body: dict[str, str]


def _err(status: int, code: str) -> Response:
    return Response(status, {"error": code})


def process_request(
    *,
    config: Config,
    nonces: NonceStore,
    updater: Any,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
    now: float | None = None,
) -> Response:
    """All checks, in order. `updater` needs only `try_start(tag) -> bool`."""
    if method != "POST":
        return _err(405, "method_not_allowed")
    if path != UPDATE_PATH:
        return _err(404, "not_found")
    h = {k.lower(): v for k, v in headers.items()}
    if h.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        return _err(415, "unsupported_media_type")
    if len(body) > MAX_BODY_BYTES:
        return _err(413, "body_too_large")

    timestamp = h.get("x-update-timestamp", "")
    sig_match = SIGNATURE_RE.fullmatch(h.get("x-update-signature", ""))
    if not TIMESTAMP_RE.fullmatch(timestamp) or not sig_match:
        return _err(401, "unauthorized")
    expected = sign(config.secret, timestamp, body)
    if not hmac.compare_digest(expected.encode("ascii"), sig_match.group(0).encode("ascii")):
        return _err(401, "unauthorized")
    current = time.time() if now is None else now
    if abs(current - int(timestamp)) > TIMESTAMP_WINDOW_SECONDS:
        return _err(401, "stale_timestamp")

    # From here on the sender is authenticated; the content is still validated strictly.
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return _err(400, "malformed_json")
    if not isinstance(payload, dict):
        return _err(400, "malformed_json")
    fields = {
        k: payload.get(k) for k in ("event", "repository", "tag", "image", "requested_at", "nonce")
    }
    if not all(isinstance(v, str) for v in fields.values()):
        return _err(400, "invalid_payload")
    if fields["event"] != "update_requested":
        return _err(400, "invalid_event")
    if str(fields["repository"]).casefold() != config.repository.casefold():
        return _err(403, "repository_mismatch")
    tag = str(fields["tag"])
    if len(tag) > MAX_TAG_LENGTH or not TAG_RE.fullmatch(tag):
        return _err(400, "invalid_tag")
    if fields["image"] != f"{config.image_repository}:{tag}":
        return _err(400, "image_mismatch")
    if not NONCE_RE.fullmatch(str(fields["nonce"])):
        return _err(400, "invalid_nonce")
    requested_at = str(fields["requested_at"])
    try:
        datetime.fromisoformat(
            requested_at.replace("Z", "+00:00") if requested_at.endswith("Z") else requested_at
        )
    except ValueError:
        return _err(400, "invalid_requested_at")
    if len(requested_at) > 40:
        return _err(400, "invalid_requested_at")

    try:
        fresh = nonces.consume(str(fields["nonce"]))
    except NonceStoreFull:
        return _err(503, "nonce_store_full")
    except OSError:
        LOG.error("nonce store not writable")
        return _err(500, "nonce_store_error")
    if not fresh:
        return _err(409, "replay")
    if not updater.try_start(tag):
        return _err(409, "busy")
    LOG.info("update accepted for tag %s", tag)
    return Response(202, {"status": "accepted"})


def make_handler(config: Config, nonces: NonceStore, updater: Any) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        timeout = SOCKET_TIMEOUT_SECONDS
        protocol_version = "HTTP/1.0"

        def version_string(self) -> str:
            return "deploy-hook"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            LOG.info("%s %s", self.address_string(), format % args)

        def _send(self, response: Response) -> None:
            data = json.dumps(response.body).encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if response.status == 405:
                self.send_header("Allow", "POST")
            self.end_headers()
            self.wfile.write(data)

        def _handle(self, method: str) -> None:
            body = b""
            if method == "POST":
                if self.headers.get("Transfer-Encoding"):
                    self._send(_err(400, "chunked_not_supported"))
                    return
                raw_length = self.headers.get("Content-Length")
                if raw_length is None:
                    self._send(_err(411, "length_required"))
                    return
                if not re.fullmatch(r"[0-9]{1,9}", raw_length, re.ASCII):
                    self._send(_err(400, "invalid_content_length"))
                    return
                length = int(raw_length)
                if length > MAX_BODY_BYTES:
                    self._send(_err(413, "body_too_large"))
                    return
                body = self.rfile.read(length)
                if len(body) != length:
                    self._send(_err(400, "incomplete_body"))
                    return
            path = self.path.split("?", 1)[0]
            self._send(
                process_request(
                    config=config,
                    nonces=nonces,
                    updater=updater,
                    method=method,
                    path=path,
                    headers=dict(self.headers.items()),
                    body=body,
                )
            )

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_GET  # noqa: N815

    return Handler


def make_server(config: Config, nonces: NonceStore, updater: Any) -> ThreadingHTTPServer:
    class Server(ThreadingHTTPServer):
        daemon_threads = True
        address_family = (
            socket.AF_INET6 if ipaddress.ip_address(config.bind).version == 6 else socket.AF_INET
        )

    return Server((config.bind, config.port), make_handler(config, nonces, updater))


def main(environ: Mapping[str, str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        config = Config.from_env(os.environ if environ is None else environ)
    except ConfigError as exc:
        print(f"deploy-hook: configuration error: {exc}", file=sys.stderr)
        return 2
    if not ipaddress.ip_address(config.bind).is_loopback:
        LOG.warning(
            "listening on a non-loopback address (%s); keep it behind a firewall or proxy",
            config.bind,
        )
    server = make_server(config, NonceStore(config.nonce_file), Updater(config))

    def stop(_signum: int, _frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOG.info("listening on %s:%s for %s", config.bind, config.port, config.repository)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
