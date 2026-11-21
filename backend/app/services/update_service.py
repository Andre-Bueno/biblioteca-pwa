"""Use cases: know the running version, learn (lazily) about a newer release, and ask the
operator's deploy agent to update when an admin approves.

No background thread: the release is looked up when an admin asks for `/system/version` and the
cache is older than the interval, under a single-flight lock with a short wait. A failure keeps the
old value and never reaches the caller as an error. The app never touches Docker: approving only
sends a signed webhook (port `UpdateNotifier`).
"""

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.errors import (
    DomainError,
    ExternalFetchError,
    UpdateAlreadyRequested,
    UpdateNotAvailable,
    UpdateNotConfigured,
    UpdateNotifyFailed,
)
from app.domain.release import (
    Release,
    UpdateRequest,
    UpdateStateName,
    Version,
    parse_app_version,
    parse_release,
)
from app.ports.audit_log import AuditLog
from app.ports.clock import Clock
from app.ports.http_gateway import HttpGateway
from app.ports.update_notifier import UpdateNotifier

logger = logging.getLogger(__name__)

RELEASE_URL = "https://api.github.com/repos/{repository}/releases/latest"
REQUEST_COOLDOWN = timedelta(minutes=10)
REFRESH_WAIT_SECONDS = 3.0  # a second caller waits this long for the lookup in flight
FAILURE_PAUSE = timedelta(minutes=1)  # after a network failure, do not ask again for a while
MIN_THROTTLE_PAUSE = timedelta(minutes=1)
MAX_THROTTLE_PAUSE = timedelta(hours=2)
DEFAULT_THROTTLE_PAUSE = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class UpdateConfig:
    current: str  # APP_VERSION as given ("dev" when not a release build)
    repository: str
    check_enabled: bool
    interval: timedelta
    webhook_configured: bool


@dataclass(frozen=True, slots=True)
class UpdateStatus:
    state: str = UpdateStateName.IDLE.value
    tag: str | None = None
    requested_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class VersionInfo:
    current: str
    update_available: bool
    latest: Release | None
    checked_at: datetime | None
    webhook_configured: bool
    update: UpdateStatus


class UpdateService:
    def __init__(
        self,
        gateway: HttpGateway,
        notifier: UpdateNotifier | None,
        audit: AuditLog,
        clock: Clock,
        config: UpdateConfig,
    ) -> None:
        self._gateway = gateway
        self._notifier = notifier
        self._audit = audit
        self._clock = clock
        self._cfg = config
        self._current: Version | None = parse_app_version(config.current)
        self._state = threading.Lock()  # protects everything below
        self._refresh_lock = threading.Lock()  # single flight for the lookup
        self._latest: Release | None = None
        self._etag: str | None = None
        self._checked_at: datetime | None = None
        self._not_before: datetime | None = None  # throttled or failed: no lookup before this
        self._request = UpdateStatus()

    # -- state -----------------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """The check works only for a real release build (APP_VERSION is a semantic version)."""
        return self._cfg.check_enabled and self._current is not None

    @property
    def current(self) -> str:
        return self._cfg.current

    def _available(self) -> bool:
        latest, current = self._latest, self._current
        return (
            self.enabled
            and latest is not None
            and current is not None
            and (latest.version > current)
        )

    def snapshot(self) -> VersionInfo:
        with self._state:
            on = self.enabled
            return VersionInfo(
                current=self._cfg.current,
                update_available=self._available(),
                latest=self._latest if on else None,
                checked_at=self._checked_at if on else None,
                webhook_configured=self._cfg.webhook_configured and self._notifier is not None,
                update=self._request,
            )

    # -- lookup -----------------------------------------------------------------------------

    def info(self) -> VersionInfo:
        """Snapshot for an admin, refreshing the cache first when it is older than the interval."""
        self.refresh(force=False)
        return self.snapshot()

    def refresh(self, *, force: bool) -> None:
        """Look up the latest release if due (or `force`). Never raises."""
        if not self.enabled:
            return
        if not self._due(force):
            return
        if not self._refresh_lock.acquire(timeout=REFRESH_WAIT_SECONDS):
            return  # a lookup is in flight and slow: serve what we have
        try:
            if not self._due(force):
                return  # another caller finished while we waited
            self._lookup()
        except Exception as exc:  # the API must never fail because of the release check
            logger.warning("Release check failed (%s)", type(exc).__name__)
        finally:
            self._refresh_lock.release()

    def _due(self, force: bool) -> bool:
        now = self._clock.now()
        with self._state:
            if self._not_before is not None and now < self._not_before:
                return False  # throttled by GitHub, or a recent failure: respect it
            if force or self._checked_at is None:
                return True
            return now - self._checked_at >= self._cfg.interval

    def _lookup(self) -> None:
        url = RELEASE_URL.format(repository=self._cfg.repository)
        with self._state:
            etag = self._etag
        now = self._clock.now()
        try:
            answer = self._gateway.get_json_conditional(url, etag)
        except ExternalFetchError as exc:
            logger.info("Release check unavailable (%s)", exc.reason)
            with self._state:
                self._not_before = now + FAILURE_PAUSE
            return
        if answer.status in (403, 429):
            with self._state:
                self._not_before = now + self._throttle_pause(answer.retry_after, answer.reset_at)
            logger.info("Release check throttled by the source")
            return
        with self._state:
            self._checked_at = now
            self._not_before = None
            if answer.status == 200:
                self._latest = parse_release(answer.data, self._cfg.repository)
                self._etag = answer.etag
            if answer.remaining == 0:  # quota spent: stop until the window resets
                self._not_before = now + self._throttle_pause(None, answer.reset_at)

    def _throttle_pause(self, retry_after: float | None, reset_at: int | None) -> timedelta:
        pause = DEFAULT_THROTTLE_PAUSE
        if retry_after is not None:
            pause = timedelta(seconds=retry_after)
        elif reset_at is not None:
            pause = datetime.fromtimestamp(reset_at, tz=UTC) - self._clock.now()
        return max(MIN_THROTTLE_PAUSE, min(MAX_THROTTLE_PAUSE, pause))

    # -- approval -----------------------------------------------------------------------------

    def request_update(self, user_id: str, tag: str) -> UpdateStatus:
        """Ask the deploy agent to update to `tag`, which must be the cached latest release and
        newer than the running version. Raises UpdateNotConfigured, UpdateNotAvailable,
        UpdateAlreadyRequested or UpdateNotifyFailed (all generic)."""
        if self._notifier is None or not self._cfg.webhook_configured:
            raise UpdateNotConfigured
        now = self._clock.now()
        with self._state:
            latest = self._latest
            if not self._available() or latest is None or tag != latest.tag:
                raise UpdateNotAvailable
            current = self._request
            if (
                current.state == UpdateStateName.REQUESTED.value
                and current.requested_at is not None
                and now - current.requested_at < REQUEST_COOLDOWN
            ):
                raise UpdateAlreadyRequested
            # Claim before sending, so two admins cannot both send it.
            self._request = UpdateStatus(UpdateStateName.REQUESTED.value, tag, now)
        try:
            self._notifier.notify(UpdateRequest(self._cfg.repository, tag, now))
        except Exception as exc:
            with self._state:
                self._request = UpdateStatus(UpdateStateName.FAILED.value, tag, None)
            self._record("system.update_failed", user_id, tag)
            if isinstance(exc, DomainError):
                raise UpdateNotifyFailed from None
            logger.warning("Update notifier failed (%s)", type(exc).__name__)
            raise UpdateNotifyFailed from None
        self._record("system.update_requested", user_id, tag)
        return UpdateStatus(UpdateStateName.REQUESTED.value, tag, now)

    def _record(self, event: str, user_id: str, tag: str) -> None:
        try:
            self._audit.record(event, user_id=user_id, detail={"tag": tag})  # no URL, no secret
        except Exception as exc:
            logger.warning("Audit of %s failed (%s)", event, type(exc).__name__)
