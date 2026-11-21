"""Use cases for authentication: login, refresh, logout, change password, current user.

Security design (read before changing):

* One generic failure. Unknown user, inactive user and wrong password raise the same
  `InvalidCredentialsError`; unknown/inactive users are verified against a dummy hash (the hasher
  does that for `password_hash=None`), and failures are recorded for ALL three scopes even when
  the username does not exist, so nothing observable differs between existing and unknown names.
* Lockout is checked BEFORE the password is verified (a locked attempt costs no hashing and a
  correct password does not bypass the lock), and the attempt is RESERVED (recorded as a failure)
  in the same critical section, before the slow hash: simultaneous attempts therefore see each
  other and cannot all slip past the limit. A success or an aborted attempt (hasher busy) releases
  the reservation. The critical section is per process (one worker, see ADR 0007). Scopes:
    - `ip`: any account from one client address (blocks username spraying; changing the username
      does not help). Threshold `ip_policy`.
    - `ip_account`: one address against one account. This is the PRIMARY per-account limit:
      the attacker locks only their own address out of that account, never the victim.
    - `account` (all addresses): stops distributed guessing against one account. To keep an
      attacker from locking a victim out of their own account (account DoS), this lock only
      needs failures from SEVERAL addresses (its threshold is higher than the pair limit, so
      one address alone cannot trip it) and only applies to attempts from addresses WITHOUT a
      successful login for that account within `trusted_ip_window`. Failures are still counted
      for every address. Residual risk: a victim
      logging in from a brand-new address while under distributed attack waits for the lock
      (capped by `max_lockout`); their usual devices keep working.
* Lockouts are progressive (see `domain.lockout`) and derived from stored failures.
* A success resets the counters of its own scopes (`ip_account`, `account`). It does NOT reset the
  `ip` counter: an attacker who owns one valid account must not be able to wipe the address
  counter between guesses at other accounts.
* Refresh tokens are opaque (32 random bytes), stored only as SHA-256, rotated on every use
  (consume + store the successor in ONE transaction). Presenting an already used token revokes
  the whole family (theft signal) and is audited, EXCEPT within `refresh_reuse_grace` of its first
  use (two tabs, a retry after a lost response): then a sibling session is issued. A thief
  replaying inside that short window is not detected; after it, detection is unchanged.
  Sessions have an absolute lifetime (`session_absolute_ttl`) regardless of rotation.
* Access tokens are validated against the database on every request: account active, session
  (family) not revoked, and not issued before the last password change.

No raw IP, username, password, token or hash is ever written to the audit log (only keyed
fingerprints supplied by the attempt store).
"""

import hashlib
import logging
import math
import secrets
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import NoReturn

from app.domain.auth import (
    CurrentPasswordError,
    InvalidCredentialsError,
    InvalidSessionError,
    InvalidTokenError,
    LoginLockedError,
    NotAuthenticatedError,
    RefreshToken,
)
from app.domain.errors import DataAccessError, ResourceBusy
from app.domain.lockout import LockoutPolicy, locked_until
from app.domain.password_policy import PasswordPolicyError, validate_password
from app.domain.user import InvalidUsernameError, User, normalize_username
from app.ports.audit_log import AuditLog
from app.ports.clock import Clock
from app.ports.login_attempt_store import AttemptScope, LoginAttemptStore
from app.ports.password_hasher import PasswordHasher
from app.ports.refresh_token_repository import RefreshTokenRepository
from app.ports.token_service import TokenService
from app.ports.user_repository import UserRepository

logger = logging.getLogger(__name__)

MAX_ACCOUNT_KEY_LENGTH = 128
MAX_REFRESH_TOKEN_LENGTH = 256
_PURGE_EVERY = timedelta(hours=1)
_PURGE_RETRY = timedelta(minutes=5)  # after a failed purge
_DEAD_FAMILY_GRACE = timedelta(days=1)
# `login.locked` is audited at most once per client address per window, and the dedupe table is
# bounded: a flood of locked attempts must not grow audit_log (or this process) without limit.
_LOCKED_EVENT_WINDOW = timedelta(seconds=60)
_LOCKED_EVENT_MAX_KEYS = 10_000


@dataclass(frozen=True, slots=True)
class AuthConfig:
    """Injected by the composition root (the service never reads settings)."""

    access_ttl: timedelta
    refresh_ttl: timedelta
    session_absolute_ttl: timedelta
    ip_policy: LockoutPolicy
    ip_account_policy: LockoutPolicy
    account_policy: LockoutPolicy
    trusted_ip_window: timedelta
    audit_retention: timedelta = timedelta(days=180)
    # Tolerance for a refresh token presented again shortly after its first use (see `refresh`).
    refresh_reuse_grace: timedelta = timedelta(0)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """Result of login/refresh/change-password. Tokens are for cookies, never for bodies/logs."""

    user: User
    access_token: str = field(repr=False)
    access_expires_at: datetime
    refresh_token: str = field(repr=False)
    refresh_expires_at: datetime
    issued_at: datetime

    @property
    def access_max_age_seconds(self) -> int:
        return max(1, int((self.access_expires_at - self.issued_at).total_seconds()))

    @property
    def refresh_max_age_seconds(self) -> int:
        """Remaining life of the refresh token (capped by the session's absolute lifetime)."""
        return max(1, int((self.refresh_expires_at - self.issued_at).total_seconds()))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _account_key(raw_username: str) -> str:
    """Case/space-insensitive key so "Alice", " alice " and "ALICE" share one counter."""
    return raw_username.strip().lower()[:MAX_ACCOUNT_KEY_LENGTH]


def _floor_seconds(moment: datetime) -> datetime:
    return moment.replace(microsecond=0)


class AuthService:
    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        attempts: LoginAttemptStore,
        tokens: TokenService,
        hasher: PasswordHasher,
        audit: AuditLog,
        clock: Clock,
        config: AuthConfig,
    ) -> None:
        self._users = users
        self._refresh = refresh_tokens
        self._attempts = attempts
        self._tokens = tokens
        self._hasher = hasher
        self._audit = audit
        self._clock = clock
        self._cfg = config
        self._last_purge: datetime | None = None
        self._purge_failed_at: datetime | None = None
        # Serializes "check the lock + reserve the attempt" (NOT the slow hash).
        self._attempt_lock = threading.Lock()
        self._locked_logged: dict[str, datetime] = {}
        self._locked_logged_lock = threading.Lock()

    # ------------------------------------------------------------------ login

    def login(self, username: str, password: str, ip: str) -> IssuedSession:
        account = _account_key(username)
        reservation = self._begin_attempt(ip, account, "login.locked")
        try:
            user = self._find_user(account)
            usable = user is not None and user.is_active
            # `None` makes the hasher verify against its dummy hash: same cost, always False.
            valid = self._hasher.verify(user.password_hash if user and usable else None, password)
        except BaseException:
            self._release(reservation)  # the attempt did not happen (hasher busy, DB error...)
            raise
        if not (valid and user is not None and usable):
            # The reserved failure stays recorded.
            self._audit.record(
                "login.failure",
                detail={
                    "ip_key": self._attempts.fingerprint("ip", ip),
                    "account_key": self._attempts.fingerprint("account", account),
                },
            )
            self._maybe_purge(self._clock.now())
            raise InvalidCredentialsError("invalid credentials")

        self._release(reservation)  # success: it must not count (the ip scope is never reset)
        now = self._clock.now()
        if self._hasher.needs_rehash(user.password_hash):
            try:
                new_hash = self._hasher.hash(password)
            except ResourceBusy:
                pass  # keep the old hash; it is upgraded at a later login
            else:
                # Compare-and-set: the (slow) hash above must not overwrite a deactivation or a
                # password reset made meanwhile; if it does not apply, the old hash stays.
                self._users.replace_password_hash(
                    user.id,
                    expected_hash=user.password_hash,
                    new_hash=new_hash,
                    now=now,
                    password_changed=False,
                )
        self._record_success(ip, account)
        session = self._start_session(user, now)
        self._audit.record("login.success", user_id=user.id)
        self._maybe_purge(now)
        return session

    # ---------------------------------------------------------------- refresh

    def refresh(self, refresh_token: str | None) -> IssuedSession:
        if not refresh_token or len(refresh_token) > MAX_REFRESH_TOKEN_LENGTH:
            raise InvalidSessionError("invalid session")
        stored = self._refresh.get_by_hash(_sha256(refresh_token))
        if stored is None:
            raise InvalidSessionError("invalid session")
        now = self._clock.now()
        if stored.revoked_at is not None:
            raise InvalidSessionError("invalid session")
        if stored.used_at is not None and not self._within_reuse_grace(stored.used_at, now):
            self._reuse_detected(stored, now)
        if stored.expires_at <= now:
            raise InvalidSessionError("invalid session")

        user = self._users.get_by_id(stored.user_id)
        if user is None or not user.is_active or user.password_changed_at > stored.created_at:
            self._refresh.revoke_family(stored.family_id, now)
            raise InvalidSessionError("invalid session")
        started = self._refresh.family_started_at(stored.family_id)
        if started is None or started + self._cfg.session_absolute_ttl <= now:
            self._refresh.revoke_family(stored.family_id, now)
            raise InvalidSessionError("invalid session")

        raw, successor = self._new_refresh_token(user, stored.family_id, now, started)
        if not self._refresh.rotate(stored.id, successor, now, self._cfg.refresh_reuse_grace):
            # Revoked meanwhile, or used longer ago than the grace window: replay.
            self._reuse_detected(stored, now)
        session = self._finish_session(user, successor, raw, now)
        self._audit.record("token.refresh", user_id=user.id)
        self._maybe_purge(now)
        return session

    def _within_reuse_grace(self, used_at: datetime, now: datetime) -> bool:
        grace = self._cfg.refresh_reuse_grace
        return grace > timedelta(0) and now - used_at <= grace

    def _reuse_detected(self, stored: RefreshToken, now: datetime) -> NoReturn:
        self._refresh.revoke_family(stored.family_id, now)
        self._audit.record(
            "token.reuse_detected", user_id=stored.user_id, detail={"family_id": stored.family_id}
        )
        raise InvalidSessionError("invalid session")

    # ----------------------------------------------------------------- logout

    def logout(self, refresh_token: str | None, access_token: str | None) -> None:
        """Revoke the session identified by either token. Idempotent; never raises on bad input."""
        now = self._clock.now()
        families: dict[str, str] = {}  # family_id -> user_id
        if refresh_token and len(refresh_token) <= MAX_REFRESH_TOKEN_LENGTH:
            stored = self._refresh.get_by_hash(_sha256(refresh_token))
            if stored is not None:
                families[stored.family_id] = stored.user_id
        if access_token:
            try:
                claims = self._tokens.decode_access_token(access_token, now=now)
                families[claims.session_id] = claims.user_id
            except InvalidTokenError:
                pass
        for family_id, user_id in families.items():
            self._refresh.revoke_family(family_id, now)
            self._audit.record("logout", user_id=user_id)

    # -------------------------------------------------------- change password

    def change_password(
        self, user_id: str, current_password: str, new_password: str, ip: str
    ) -> IssuedSession:
        user = self._users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise NotAuthenticatedError("not authenticated")
        account = _account_key(user.username)
        # Re-authentication is a password oracle for whoever holds a session: same lockout.
        reservation = self._begin_attempt(ip, account, "login.locked")
        try:
            correct = self._hasher.verify(user.password_hash, current_password)
        except BaseException:
            self._release(reservation)
            raise
        if not correct:
            self._audit.record(
                "login.failure",
                user_id=user.id,
                detail={"reason": "change_password"},
            )
            raise CurrentPasswordError("current password is incorrect")
        self._release(reservation)
        self._record_success(ip, account)
        validate_password(new_password, user.username)
        if new_password == current_password:
            raise PasswordPolicyError("new password must differ from the current one")

        now = self._clock.now()
        new_hash = self._hasher.hash(new_password)
        applied = self._users.replace_password_hash(
            user.id,
            expected_hash=user.password_hash,
            new_hash=new_hash,
            now=now,
            password_changed=True,
        )
        if not applied:
            # Deactivated or password changed/reset while we were hashing: do not overwrite.
            raise NotAuthenticatedError("not authenticated")
        updated = replace(user, password_hash=new_hash, updated_at=now, password_changed_at=now)
        self._refresh.revoke_all_for_user(user.id, now)
        session = self._start_session(updated, now)
        self._audit.record("password.changed", user_id=user.id)
        return session

    # ----------------------------------------------------------- current user

    def current_user(self, access_token: str | None) -> User:
        """Validate the access token against the database. Raises `NotAuthenticatedError`."""
        if not access_token:
            raise NotAuthenticatedError("not authenticated")
        now = self._clock.now()
        try:
            claims = self._tokens.decode_access_token(access_token, now=now)
        except InvalidTokenError:
            raise NotAuthenticatedError("not authenticated") from None
        user = self._users.get_by_id(claims.user_id)
        if user is None or not user.is_active:
            raise NotAuthenticatedError("not authenticated")
        # `iat` has 1 s resolution: compare against the floored change time. Old tokens are also
        # killed by session revocation, which has no such granularity limit.
        if claims.issued_at < _floor_seconds(user.password_changed_at):
            raise NotAuthenticatedError("not authenticated")
        if not self._refresh.is_family_active(claims.session_id, user.id):
            raise NotAuthenticatedError("not authenticated")
        return user

    # ---------------------------------------------------------------- helpers

    def _find_user(self, account: str) -> User | None:
        try:
            normalized = normalize_username(account)
        except InvalidUsernameError:
            return None  # malformed names are simply "unknown"
        return self._users.get_by_username(normalized)

    def _scopes(self, ip: str, account: str) -> tuple[tuple[AttemptScope, str], ...]:
        return (("ip", ip), ("account", account), ("ip_account", f"{ip}\0{account}"))

    def _begin_attempt(self, ip: str, account: str, event: str) -> list[int]:
        """Atomically (per process) enforce the lock and reserve this attempt as a failure.

        The reservation is made BEFORE the slow password check so concurrent attempts count each
        other. Raises `LoginLockedError` without reserving anything when locked."""
        with self._attempt_lock:
            self._enforce_lock(ip, account, event)
            return self._attempts.reserve_failures(self._scopes(ip, account), self._clock.now())

    def _release(self, reservation: list[int]) -> None:
        try:
            self._attempts.release(reservation)
        except DataAccessError:
            # Never let bookkeeping mask the real outcome; the reservation then counts as a
            # failure (the safe direction) until it ages out.
            logger.warning("Could not release a login attempt reservation")

    def _record_success(self, ip: str, account: str) -> None:
        now = self._clock.now()
        # Deliberately not the `ip` scope (see module docstring).
        self._attempts.record("account", account, now, success=True)
        self._attempts.record("ip_account", f"{ip}\0{account}", now, success=True)

    def _lock_end(
        self, scope: AttemptScope, key: str, policy: LockoutPolicy, now: datetime
    ) -> datetime | None:
        failures = self._attempts.failures_since_last_success(scope, key, now - policy.lookback)
        return locked_until(failures, policy, now)

    def _is_trusted_ip(self, ip: str, account: str, now: datetime) -> bool:
        last = self._attempts.last_success_at("ip_account", f"{ip}\0{account}")
        return last is not None and now - last <= self._cfg.trusted_ip_window

    def _enforce_lock(self, ip: str, account: str, event: str) -> None:
        now = self._clock.now()
        ends = [
            self._lock_end("ip", ip, self._cfg.ip_policy, now),
            self._lock_end("ip_account", f"{ip}\0{account}", self._cfg.ip_account_policy, now),
        ]
        if not self._is_trusted_ip(ip, account, now):
            ends.append(self._lock_end("account", account, self._cfg.account_policy, now))
        active = [end for end in ends if end is not None]
        if not active:
            return
        remaining = (max(active) - now).total_seconds()
        self._audit_locked(event, ip, account, now)
        raise LoginLockedError(math.ceil(remaining))

    def _audit_locked(self, event: str, ip: str, account: str, now: datetime) -> None:
        """At most one event per client address per window (and a bounded dedupe table)."""
        ip_key = self._attempts.fingerprint("ip", ip)
        with self._locked_logged_lock:
            last = self._locked_logged.get(ip_key)
            if last is not None and now - last < _LOCKED_EVENT_WINDOW:
                return
            if len(self._locked_logged) >= _LOCKED_EVENT_MAX_KEYS:
                self._locked_logged = {
                    k: t for k, t in self._locked_logged.items() if now - t < _LOCKED_EVENT_WINDOW
                }
                if len(self._locked_logged) >= _LOCKED_EVENT_MAX_KEYS:
                    return  # table full of live entries: drop the event, never grow
            self._locked_logged[ip_key] = now
        self._audit.record(
            event,
            detail={
                "ip_key": ip_key,
                "account_key": self._attempts.fingerprint("account", account),
            },
        )

    def _start_session(self, user: User, now: datetime) -> IssuedSession:
        return self._issue(user, str(uuid.uuid4()), now, now)

    def _new_refresh_token(
        self, user: User, family_id: str, now: datetime, family_started: datetime
    ) -> tuple[str, RefreshToken]:
        """(raw opaque value, record to store). The raw value only ever goes to the cookie."""
        raw = secrets.token_urlsafe(32)
        refresh_expires = min(
            now + self._cfg.refresh_ttl, family_started + self._cfg.session_absolute_ttl
        )
        return raw, RefreshToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            family_id=family_id,
            token_hash=_sha256(raw),
            created_at=now,
            expires_at=refresh_expires,
        )

    def _finish_session(
        self, user: User, token: RefreshToken, raw: str, now: datetime
    ) -> IssuedSession:
        access_expires = now + self._cfg.access_ttl
        access = self._tokens.issue_access_token(
            user_id=user.id, session_id=token.family_id, issued_at=now, expires_at=access_expires
        )
        return IssuedSession(
            user=user,
            access_token=access,
            access_expires_at=access_expires,
            refresh_token=raw,
            refresh_expires_at=token.expires_at,
            issued_at=now,
        )

    def _issue(
        self, user: User, family_id: str, now: datetime, family_started: datetime
    ) -> IssuedSession:
        raw, token = self._new_refresh_token(user, family_id, now, family_started)
        self._refresh.add(token)
        return self._finish_session(user, token, raw, now)

    def purge_expired(self) -> tuple[int, int, int]:
        """Delete expired login attempts, dead refresh families and audit events past retention.
        Returns the three counts. Raises on database errors (callers decide what to do)."""
        now = self._clock.now()
        cfg = self._cfg
        lookback = max(
            p.lookback for p in (cfg.ip_policy, cfg.ip_account_policy, cfg.account_policy)
        )
        attempts = self._attempts.purge(now - lookback, now - cfg.trusted_ip_window)
        families = self._refresh.purge_dead_families(now - _DEAD_FAMILY_GRACE)
        events = self._audit.purge(now - cfg.audit_retention)
        return attempts, families, events

    def _maybe_purge(self, now: datetime) -> None:
        """Opportunistic maintenance, at most hourly. Isolated: a failure is logged generically
        and retried after `_PURGE_RETRY`; it must never break the request that triggered it."""
        if self._last_purge is not None and now - self._last_purge < _PURGE_EVERY:
            return
        if self._purge_failed_at is not None and now - self._purge_failed_at < _PURGE_RETRY:
            return
        try:
            self.purge_expired()
        except Exception:
            self._purge_failed_at = now
            logger.warning("Maintenance purge failed; it will be retried later")
            return
        self._last_purge = now
        self._purge_failed_at = None
