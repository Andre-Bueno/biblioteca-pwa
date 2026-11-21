"""Composition root: wires adapters into services. Shared by `app.api.deps`, `app.main`, `app.cli`.

Everything is built lazily (first use), so importing the app or serving `/health` never opens the
database or computes a password hash.
"""

import threading
from dataclasses import replace
from datetime import timedelta
from functools import cached_property
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.extractors.registry import book_readers, build_extractors
from app.adapters.http.safe_gateway import DisabledGateway, SafeGateway
from app.adapters.http.webhook_notifier import WebhookNotifier
from app.adapters.metadata.anilist import AniListProvider
from app.adapters.metadata.googlebooks import GoogleBooksProvider
from app.adapters.metadata.mangadex import MangaDexProvider
from app.adapters.metadata.mymemory import MyMemoryTranslator
from app.adapters.metadata.wikipedia import WikipediaProvider
from app.adapters.persistence.audit_log import SqlAlchemyAuditLog
from app.adapters.persistence.db import create_db_engine, create_session_factory
from app.adapters.persistence.item_repository import SqlAlchemyItemRepository
from app.adapters.persistence.login_attempt_store import SqlAlchemyLoginAttemptStore
from app.adapters.persistence.migrator import upgrade
from app.adapters.persistence.preferences_repository import SqlAlchemyPreferencesRepository
from app.adapters.persistence.progress_repository import SqlAlchemyProgressRepository
from app.adapters.persistence.refresh_token_repository import SqlAlchemyRefreshTokenRepository
from app.adapters.persistence.series_repository import SqlAlchemySeriesRepository
from app.adapters.persistence.user_repository import SqlAlchemyUserRepository
from app.adapters.security.argon2_hasher import Argon2Hasher
from app.adapters.security.jwt_tokens import JwtTokenService
from app.adapters.security.rate_limiter import TokenBucketRateLimiter
from app.adapters.security.system_clock import SystemClock
from app.adapters.storage.cover_store import LocalCoverStore
from app.adapters.storage.local import LocalStorage
from app.core.config import Settings, get_settings
from app.core.keys import LABEL_ACCESS_JWT, LABEL_LOGIN_ATTEMPTS, derive_key
from app.domain.errors import LibraryUnavailable
from app.domain.library import ExtractorLimits, ScanReport
from app.domain.lockout import LockoutPolicy
from app.domain.metadata import EnrichReport
from app.ports.book_reader import BookReader
from app.ports.clock import Clock
from app.ports.cover_store import CoverStore
from app.ports.extractor import Extractor
from app.ports.http_gateway import HttpGateway
from app.ports.item_repository import ItemRepository
from app.ports.metadata_provider import MetadataProvider
from app.ports.password_hasher import PasswordHasher
from app.ports.progress_repository import ProgressRepository
from app.ports.rate_limiter import RateLimiter
from app.ports.series_repository import SeriesRepository
from app.ports.storage import StorageBackend
from app.ports.update_notifier import UpdateNotifier
from app.services.auth_service import AuthConfig, AuthService
from app.services.enrich_runner import EnrichRunner
from app.services.metadata_service import MetadataConfig, MetadataService
from app.services.preferences_service import PreferencesService
from app.services.progress_service import ProgressService
from app.services.scan import ProgressCallback, scan_library
from app.services.scan_runner import ScanRunner
from app.services.series_service import SeriesService
from app.services.update_service import UpdateConfig, UpdateService
from app.services.user_service import UserService

CANDIDATES_PER_MINUTE = 10


class _locked_cached_property[T](cached_property[T]):  # noqa: N801
    """`cached_property` whose first build is serialized: without the lock two request threads
    could each build their own service (own login lock, own hasher gate, own caches)."""

    def __get__(self, instance: Any, owner: type | None = None) -> T:  # type: ignore[override]
        if instance is None:
            return self  # type: ignore[return-value]
        with instance._build_lock:
            value: T = super().__get__(instance, owner)
            return value


class Container:
    """Lazily built services for one `Settings`. Tests inject a fast hasher and a fake clock."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        hasher: PasswordHasher | None = None,
        clock: Clock | None = None,
        gateway: HttpGateway | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._hasher = hasher
        self._clock = clock
        self._gateway = gateway  # tests: a fake instead of the real network
        self._build_lock = threading.RLock()

    @_locked_cached_property
    def clock(self) -> Clock:
        return self._clock or SystemClock()

    @_locked_cached_property
    def hasher(self) -> PasswordHasher:
        return self._hasher or Argon2Hasher()

    @_locked_cached_property
    def session_factory(self) -> sessionmaker[Session]:
        return create_session_factory(create_db_engine(self.settings.DATABASE_URL))

    @_locked_cached_property
    def user_service(self) -> UserService:
        return UserService(
            users=SqlAlchemyUserRepository(self.session_factory),
            hasher=self.hasher,
            audit=SqlAlchemyAuditLog(self.session_factory, self.clock),
            clock=self.clock,
        )

    @_locked_cached_property
    def item_repository(self) -> ItemRepository:
        return SqlAlchemyItemRepository(self.session_factory, self.clock)

    @_locked_cached_property
    def progress_repository(self) -> ProgressRepository:
        return SqlAlchemyProgressRepository(self.session_factory)

    @_locked_cached_property
    def progress_service(self) -> ProgressService:
        return ProgressService(
            items=self.item_repository, progress=self.progress_repository, clock=self.clock
        )

    @_locked_cached_property
    def series_repository(self) -> SeriesRepository:
        return SqlAlchemySeriesRepository(self.session_factory, self.clock)

    @_locked_cached_property
    def series_service(self) -> SeriesService:
        return SeriesService(self.series_repository, self.progress_repository)

    @_locked_cached_property
    def http_gateway(self) -> HttpGateway:
        """Outbound HTTP. With `METADATA_ENABLED=false` it is a stub that opens no socket."""
        if self._gateway is not None:
            return self._gateway
        if not self.settings.METADATA_ENABLED:
            return DisabledGateway()
        return SafeGateway(total_timeout=float(self.settings.METADATA_HTTP_TIMEOUT_SECONDS))

    @_locked_cached_property
    def cover_store(self) -> CoverStore:
        return LocalCoverStore(self.settings.DATA_DIR)

    @_locked_cached_property
    def metadata_service(self) -> MetadataService:
        cfg = self.settings
        gateway = self.http_gateway
        providers: list[MetadataProvider] = []
        if cfg.METADATA_ENABLED:
            known: dict[str, MetadataProvider] = {
                "mangadex": MangaDexProvider(gateway),
                "anilist": AniListProvider(gateway),
                "wikipedia": WikipediaProvider(gateway),
                "googlebooks": GoogleBooksProvider(gateway),
            }
            providers = [known[name] for name in cfg.metadata_providers if name in known]
        return MetadataService(
            self.series_repository,
            providers,
            gateway,
            self.cover_store,
            self.clock,
            MetadataConfig(
                enabled=cfg.METADATA_ENABLED,
                languages=cfg.metadata_languages,
                max_per_run=cfg.METADATA_MAX_PER_RUN,
                translate_enabled=cfg.METADATA_TRANSLATE_ENABLED,
            ),
            MyMemoryTranslator(gateway) if cfg.METADATA_ENABLED else None,
        )

    @_locked_cached_property
    def enrich_runner(self) -> EnrichRunner:
        service = self.metadata_service

        def job(force: bool, series_id: str | None) -> EnrichReport:
            return service.enrich_all(force=force, series_id=series_id)

        return EnrichRunner(job, self.clock)

    @_locked_cached_property
    def candidates_limiter(self) -> RateLimiter:
        """Per user (key = user id): 10 live source searches per minute."""
        return TokenBucketRateLimiter(
            capacity=CANDIDATES_PER_MINUTE, per_minute=CANDIDATES_PER_MINUTE
        )

    @_locked_cached_property
    def update_check_limiter(self) -> RateLimiter:
        """Per admin (key = user id): 3 forced release checks per minute."""
        return TokenBucketRateLimiter(capacity=3, per_minute=3)

    @_locked_cached_property
    def update_gateway(self) -> HttpGateway:
        """Outbound HTTP of the release check only. Independent of METADATA_ENABLED (it has its own
        switch, UPDATE_CHECK_ENABLED) and of the metadata gateway's lock."""
        if self._gateway is not None:
            return self._gateway
        if not self.settings.UPDATE_CHECK_ENABLED:
            return DisabledGateway()
        return SafeGateway()

    @_locked_cached_property
    def update_notifier(self) -> UpdateNotifier | None:
        cfg = self.settings
        if cfg.UPDATE_WEBHOOK_URL is None or cfg.UPDATE_WEBHOOK_SECRET is None:
            return None
        return WebhookNotifier(
            cfg.UPDATE_WEBHOOK_URL,
            cfg.UPDATE_WEBHOOK_SECRET.get_secret_value(),
            allow_http=cfg.UPDATE_WEBHOOK_ALLOW_HTTP,
        )

    @_locked_cached_property
    def update_service(self) -> UpdateService:
        cfg = self.settings
        notifier = self.update_notifier
        return UpdateService(
            self.update_gateway,
            notifier,
            SqlAlchemyAuditLog(self.session_factory, self.clock),
            self.clock,
            UpdateConfig(
                current=cfg.APP_VERSION,
                repository=cfg.UPDATE_REPOSITORY,
                check_enabled=cfg.UPDATE_CHECK_ENABLED,
                interval=timedelta(hours=cfg.UPDATE_CHECK_INTERVAL_HOURS),
                webhook_configured=notifier is not None,
            ),
        )

    @_locked_cached_property
    def preferences_service(self) -> PreferencesService:
        return PreferencesService(SqlAlchemyPreferencesRepository(self.session_factory))

    @_locked_cached_property
    def storage(self) -> StorageBackend:
        """The library on disk. Built on first use so a missing folder is reported when the
        library is first needed (scan, page), never at import or start-up of the API."""
        try:
            return LocalStorage(self.settings.LIBRARY_PATH)
        except OSError:  # missing, not a directory, unreadable; never echo the path
            raise LibraryUnavailable("library folder is not available") from None

    @_locked_cached_property
    def extractors(self) -> list[Extractor]:
        cfg = self.settings
        limits = ExtractorLimits(
            max_entries=cfg.EXTRACTOR_MAX_ENTRIES,
            max_total_uncompressed_bytes=cfg.EXTRACTOR_MAX_TOTAL_UNCOMPRESSED_BYTES,
            max_page_bytes=cfg.EXTRACTOR_MAX_PAGE_BYTES,
            max_compression_ratio=cfg.EXTRACTOR_MAX_COMPRESSION_RATIO,
        )
        return build_extractors(self.storage, limits)

    @_locked_cached_property
    def book_readers(self) -> list[BookReader]:
        """The extractors that also read books (same instances as in `extractors`)."""
        return book_readers(self.extractors)

    @_locked_cached_property
    def scan_runner(self) -> ScanRunner:
        # Resolve the library now: a missing folder fails here (clear error), not in the thread.
        storage = self.storage
        extractors = self.extractors
        repo = self.item_repository
        series = self.series_repository
        clock = self.clock

        def job(progress: ProgressCallback) -> ScanReport:
            return scan_library(
                storage, repo, extractors, clock=clock, progress=progress, series=series
            )

        return ScanRunner(job, clock)

    @_locked_cached_property
    def auth_service(self) -> AuthService:
        cfg = self.settings
        ip_policy = LockoutPolicy(
            max_failures=cfg.LOGIN_MAX_FAILURES_IP,
            window=timedelta(seconds=cfg.LOGIN_FAILURE_WINDOW_SECONDS),
            base_lockout=timedelta(seconds=cfg.LOGIN_LOCKOUT_SECONDS),
            max_lockout=timedelta(seconds=cfg.LOGIN_LOCKOUT_MAX_SECONDS),
        )
        ip_account_policy = replace(ip_policy, max_failures=cfg.LOGIN_MAX_FAILURES_ACCOUNT)
        account_policy = replace(ip_policy, max_failures=cfg.LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS)
        return AuthService(
            users=SqlAlchemyUserRepository(self.session_factory),
            refresh_tokens=SqlAlchemyRefreshTokenRepository(self.session_factory),
            attempts=SqlAlchemyLoginAttemptStore(
                self.session_factory, derive_key(cfg.SECRET_KEY, LABEL_LOGIN_ATTEMPTS)
            ),
            tokens=JwtTokenService(derive_key(cfg.SECRET_KEY, LABEL_ACCESS_JWT)),
            hasher=self.hasher,
            audit=SqlAlchemyAuditLog(self.session_factory, self.clock),
            clock=self.clock,
            config=AuthConfig(
                access_ttl=timedelta(seconds=cfg.ACCESS_TOKEN_TTL_SECONDS),
                refresh_ttl=timedelta(seconds=cfg.REFRESH_TOKEN_TTL_SECONDS),
                session_absolute_ttl=timedelta(seconds=cfg.SESSION_ABSOLUTE_TTL_SECONDS),
                ip_policy=ip_policy,
                ip_account_policy=ip_account_policy,
                account_policy=account_policy,
                trusted_ip_window=timedelta(seconds=cfg.LOGIN_TRUSTED_IP_WINDOW_SECONDS),
                audit_retention=timedelta(days=cfg.AUDIT_RETENTION_DAYS),
                refresh_reuse_grace=timedelta(seconds=cfg.REFRESH_REUSE_GRACE_SECONDS),
            ),
        )


def build_container(settings: Settings | None = None) -> Container:
    return Container(settings)


def build_user_service(
    settings: Settings | None = None, *, hasher: PasswordHasher | None = None
) -> UserService:
    return Container(settings, hasher=hasher).user_service


def build_rate_limiters(
    settings: Settings,
) -> tuple[TokenBucketRateLimiter, TokenBucketRateLimiter]:
    """(global /api limiter, stricter /api/v1/auth limiter), in-memory per process."""
    api = TokenBucketRateLimiter(
        capacity=settings.RATE_LIMIT_API_BURST, per_minute=settings.RATE_LIMIT_API_PER_MINUTE
    )
    auth = TokenBucketRateLimiter(
        capacity=settings.RATE_LIMIT_AUTH_BURST, per_minute=settings.RATE_LIMIT_AUTH_PER_MINUTE
    )
    return api, auth


def run_migrations(settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    upgrade(cfg.DATABASE_URL, migrations_dir=cfg.MIGRATIONS_DIR)
