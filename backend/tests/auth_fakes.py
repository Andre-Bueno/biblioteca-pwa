"""Fakes and builders for auth tests (in-memory ports, fake clock, app factory)."""

import contextlib
import hashlib
import threading
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.adapters.persistence.migrator import upgrade
from app.adapters.security.argon2_hasher import Argon2Hasher
from app.adapters.security.jwt_tokens import JwtTokenService
from app.composition import Container
from app.core.config import Settings
from app.domain.auth import RefreshToken
from app.domain.lockout import LockoutPolicy
from app.domain.user import Role, User, UsernameAlreadyExistsError, UserNotFoundError
from app.main import create_app
from app.ports.http_gateway import HttpGateway
from app.ports.login_attempt_store import AttemptScope
from app.services.auth_service import AuthConfig, AuthService
from fastapi import FastAPI
from fastapi.testclient import TestClient

TEST_SECRET = "test-only-secret-key-not-for-production-0123456789"
PASSWORD = "correct horse battery staple"
START = datetime(2026, 11, 19, 12, 0, 0, 500_000, tzinfo=UTC)


class FakeClock:
    def __init__(self, start: datetime = START) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


class FakeHasher:
    """Deterministic, instant. `verify(None, ...)` is False like the real dummy-hash path."""

    def __init__(self) -> None:
        self.verify_calls: list[bool] = []  # True when a real hash was given

    def hash(self, password: str) -> str:
        return f"fake${password[::-1]}"

    def verify(self, password_hash: str | None, password: str) -> bool:
        self.verify_calls.append(password_hash is not None)
        legacy = f"old${password[::-1]}"
        return password_hash is not None and password_hash in (self.hash(password), legacy)

    def needs_rehash(self, password_hash: str) -> bool:
        return password_hash.startswith("old$")


class FakeUsers:
    def __init__(self) -> None:
        self.by_id: dict[str, User] = {}

    def add(self, user: User) -> None:
        if any(u.username == user.username for u in self.by_id.values()):
            raise UsernameAlreadyExistsError("username already exists")
        self.by_id[user.id] = user

    def update(self, user: User) -> None:
        """TEST SETUP ONLY (not part of the `UserRepository` port): overwrite the whole user."""
        if user.id not in self.by_id:
            raise UserNotFoundError("user not found")
        self.by_id[user.id] = user

    def replace_password_hash(
        self,
        user_id: str,
        *,
        expected_hash: str,
        new_hash: str,
        now: datetime,
        password_changed: bool,
    ) -> bool:
        user = self.by_id.get(user_id)
        if user is None or not user.is_active or user.password_hash != expected_hash:
            return False
        changed = now if password_changed else user.password_changed_at
        self.by_id[user_id] = _replace(
            user, password_hash=new_hash, updated_at=now, password_changed_at=changed
        )
        return True

    def set_password_hash(self, user_id: str, new_hash: str, now: datetime) -> None:
        user = self.by_id.get(user_id)
        if user is None:
            raise UserNotFoundError("user not found")
        self.by_id[user_id] = _replace(
            user, password_hash=new_hash, updated_at=now, password_changed_at=now
        )

    def deactivate(self, user_id: str, now: datetime) -> None:
        user = self.by_id.get(user_id)
        if user is None:
            raise UserNotFoundError("user not found")
        self.by_id[user_id] = _replace(user, is_active=False, updated_at=now)

    def get_by_id(self, user_id: str) -> User | None:
        return self.by_id.get(user_id)

    def get_by_username(self, username: str) -> User | None:
        return next((u for u in self.by_id.values() if u.username == username.lower()), None)

    def list_all(self) -> list[User]:
        return list(self.by_id.values())


class FakeRefreshTokens:
    def __init__(self) -> None:
        self.rows: dict[str, RefreshToken] = {}
        self._lock = threading.Lock()

    def add(self, token: RefreshToken) -> None:
        self.rows[token.id] = token

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return next((t for t in self.rows.values() if t.token_hash == token_hash), None)

    def mark_used(self, token_id: str, at: datetime) -> bool:
        row = self.rows[token_id]
        if row.used_at is not None or row.revoked_at is not None:
            return False
        self.rows[token_id] = _replace(row, used_at=at)
        return True

    def rotate(
        self, stored_id: str, successor: RefreshToken, at: datetime, grace: timedelta
    ) -> bool:
        with self._lock:
            row = self.rows[stored_id]
            if row.revoked_at is not None:
                return False
            if row.used_at is None:
                self.rows[stored_id] = _replace(row, used_at=at)
            elif grace <= timedelta(0) or at - row.used_at > grace:
                return False
            self.rows[successor.id] = successor
            return True

    def revoke_family(self, family_id: str, at: datetime) -> None:
        for key, row in list(self.rows.items()):
            if row.family_id == family_id and row.revoked_at is None:
                self.rows[key] = _replace(row, revoked_at=at)

    def revoke_all_for_user(self, user_id: str, at: datetime) -> None:
        for key, row in list(self.rows.items()):
            if row.user_id == user_id and row.revoked_at is None:
                self.rows[key] = _replace(row, revoked_at=at)

    def family_started_at(self, family_id: str) -> datetime | None:
        times = [r.created_at for r in self.rows.values() if r.family_id == family_id]
        return min(times) if times else None

    def is_family_active(self, family_id: str, user_id: str) -> bool:
        return any(
            r.family_id == family_id and r.user_id == user_id and r.revoked_at is None
            for r in self.rows.values()
        )

    def purge_dead_families(self, before: datetime) -> int:
        newest: dict[str, datetime] = {}
        for r in self.rows.values():
            newest[r.family_id] = max(newest.get(r.family_id, r.expires_at), r.expires_at)
        dead = {f for f, exp in newest.items() if exp < before}
        gone = [k for k, r in self.rows.items() if r.family_id in dead]
        for key in gone:
            del self.rows[key]
        return len(gone)


def _replace(token: RefreshToken, **changes: datetime | None) -> RefreshToken:
    from dataclasses import replace

    return replace(token, **changes)


class FakeAttempts:
    def __init__(self) -> None:
        self.rows: list[tuple[int, AttemptScope, str, datetime, bool]] = []
        self._next_id = 1
        self._lock = threading.Lock()

    def fingerprint(self, scope: AttemptScope, key: str) -> str:
        return hashlib.sha256(f"{scope}|{key}".encode()).hexdigest()[:16]

    def record(self, scope: AttemptScope, key: str, at: datetime, *, success: bool) -> None:
        with self._lock:
            self.rows.append((self._next_id, scope, key, at, success))
            self._next_id += 1

    def reserve_failures(self, keys: Sequence[tuple[AttemptScope, str]], at: datetime) -> list[int]:
        with self._lock:
            ids: list[int] = []
            for scope, key in keys:
                self.rows.append((self._next_id, scope, key, at, False))
                ids.append(self._next_id)
                self._next_id += 1
            return ids

    def release(self, reservation_ids: Sequence[int]) -> None:
        with self._lock:
            self.rows = [r for r in self.rows if r[0] not in reservation_ids or r[4]]

    def _last_success_id(self, scope: AttemptScope, key: str) -> int:
        ids = [r[0] for r in self.rows if r[1] == scope and r[2] == key and r[4]]
        return max(ids, default=0)

    def failures_since_last_success(
        self, scope: AttemptScope, key: str, since: datetime
    ) -> list[datetime]:
        last = self._last_success_id(scope, key)
        return sorted(
            r[3]
            for r in self.rows
            if r[1] == scope and r[2] == key and not r[4] and r[0] > last and r[3] > since
        )

    def last_success_at(self, scope: AttemptScope, key: str) -> datetime | None:
        times = [r[3] for r in self.rows if r[1] == scope and r[2] == key and r[4]]
        return max(times, default=None)

    def purge(self, failures_before: datetime, successes_before: datetime) -> int:
        keep = [r for r in self.rows if r[3] >= (successes_before if r[4] else failures_before)]
        removed = len(self.rows) - len(keep)
        self.rows = keep
        return removed


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[
            tuple[str, str | None, str | None, Mapping[str, str | int | bool] | None]
        ] = []
        self.purged_before: list[datetime] = []

    def record(
        self,
        event: str,
        *,
        user_id: str | None = None,
        ip: str | None = None,
        detail: Mapping[str, str | int | bool] | None = None,
    ) -> None:
        self.events.append((event, user_id, ip, detail))

    def purge(self, before: datetime) -> int:
        self.purged_before.append(before)
        return 0

    def names(self) -> list[str]:
        return [e[0] for e in self.events]


DEFAULT_CONFIG = AuthConfig(
    access_ttl=timedelta(minutes=15),
    refresh_ttl=timedelta(days=30),
    session_absolute_ttl=timedelta(days=90),
    ip_policy=LockoutPolicy(20, timedelta(minutes=15), timedelta(minutes=5), timedelta(hours=1)),
    ip_account_policy=LockoutPolicy(
        5, timedelta(minutes=15), timedelta(minutes=5), timedelta(hours=1)
    ),
    account_policy=LockoutPolicy(
        15, timedelta(minutes=15), timedelta(minutes=5), timedelta(hours=1)
    ),
    trusted_ip_window=timedelta(days=30),
)


def make_user(
    username: str = "alice",
    password: str = PASSWORD,
    *,
    role: Role = Role.USER,
    active: bool = True,
    now: datetime = START,
) -> User:
    return User(
        id=f"id-{username}",
        username=username,
        password_hash=FakeHasher().hash(password),
        role=role,
        is_active=active,
        theme_pref="system",
        created_at=now,
        updated_at=now,
        password_changed_at=now,
    )


class Rig:
    """An `AuthService` over in-memory fakes, exposing every collaborator for assertions."""

    def __init__(self, config: AuthConfig = DEFAULT_CONFIG) -> None:
        self.clock = FakeClock()
        self.users = FakeUsers()
        self.refresh = FakeRefreshTokens()
        self.attempts = FakeAttempts()
        self.audit = FakeAudit()
        self.hasher = FakeHasher()
        self.tokens = JwtTokenService(b"k" * 32)
        self.service = AuthService(
            users=self.users,
            refresh_tokens=self.refresh,
            attempts=self.attempts,
            tokens=self.tokens,
            hasher=self.hasher,
            audit=self.audit,
            clock=self.clock,
            config=config,
        )
        self.users.add(make_user())

    def fail(self, times: int, *, ip: str = "9.9.9.9", username: str = "alice") -> None:
        from app.domain.auth import InvalidCredentialsError

        for _ in range(times):
            with contextlib.suppress(InvalidCredentialsError):
                self.service.login(username, "wrong password here", ip)


# ---------------------------------------------------------------- API level


def make_settings(db_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "SECRET_KEY": TEST_SECRET,
        "DATABASE_URL": db_url,
        "COOKIE_SECURE": True,
        "LIBRARY_PATH": Path("/library"),
        # Raise the rate limits by default so unrelated tests never hit them.
        "RATE_LIMIT_API_BURST": 10_000,
        "RATE_LIMIT_API_PER_MINUTE": 100_000,
        "RATE_LIMIT_AUTH_BURST": 10_000,
        "RATE_LIMIT_AUTH_PER_MINUTE": 100_000,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class Env:
    """A fully wired app on a temporary migrated SQLite database with a fake clock."""

    def __init__(
        self,
        db_url: str,
        *,
        hasher: Argon2Hasher | None = None,
        gateway: HttpGateway | None = None,
        **overrides: object,
    ) -> None:
        upgrade(db_url)
        self.clock = FakeClock()
        self.settings = make_settings(db_url, **overrides)
        self.hasher = hasher or Argon2Hasher(time_cost=1, memory_cost_kib=8, parallelism=1)
        self.container = Container(
            self.settings, hasher=self.hasher, clock=self.clock, gateway=gateway
        )
        self.app: FastAPI = create_app(self.settings, container=self.container)

    def create_user(
        self, username: str = "alice", password: str = PASSWORD, *, role: Role = Role.USER
    ) -> User:
        return self.container.user_service.create_user(username, password, role=role)

    def client(self, ip: str = "10.0.0.1") -> "ApiClient":
        return ApiClient(self.app, ip)


class ApiClient:
    """TestClient wrapper that behaves like the frontend: fetches the CSRF cookie first, echoes
    it in the header and sends a same-origin `Origin`."""

    ORIGIN = "https://testserver"

    def __init__(self, app: FastAPI, ip: str) -> None:
        self.http = TestClient(app, base_url=self.ORIGIN, client=(ip, 50000))

    def csrf(self) -> str:
        response = self.http.get("/api/v1/auth/csrf")
        assert response.status_code == 204
        token = self.http.cookies.get("csrf_token")
        assert token
        return token

    def cookie(self, name: str) -> str | None:
        return self.http.cookies.get(name)

    def _with_cookies(self, headers: dict[str, str], cookies: dict[str, str] | None) -> None:
        if cookies is not None:
            csrf = self.http.cookies.get("csrf_token")
            merged = dict(cookies) | ({"csrf_token": csrf} if csrf else {})
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in merged.items())

    def get(self, path: str, cookies: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
        headers: dict[str, str] = {}
        self._with_cookies(headers, cookies)
        return self.http.get(path, headers=headers)

    def post(  # type: ignore[no-untyped-def]
        self,
        path: str,
        json: object | None = None,
        *,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ):
        sent = {"Origin": self.ORIGIN, "X-CSRF-Token": self.cookie("csrf_token") or self.csrf()}
        self._with_cookies(sent, cookies)
        sent.update(headers or {})
        return self.http.post(path, json=json, headers=sent)

    def _write_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        sent = {"Origin": self.ORIGIN, "X-CSRF-Token": self.cookie("csrf_token") or self.csrf()}
        sent.update(headers or {})
        return sent

    def put(  # type: ignore[no-untyped-def]
        self, path: str, json: object | None = None, *, headers: dict[str, str] | None = None
    ):
        return self.http.put(path, json=json, headers=self._write_headers(headers))

    def delete(self, path: str, *, headers: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
        return self.http.delete(path, headers=self._write_headers(headers))

    def login(self, username: str = "alice", password: str = PASSWORD):  # type: ignore[no-untyped-def]
        return self.post("/api/v1/auth/login", {"username": username, "password": password})
