import ipaddress
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.release import is_operator_network, valid_repository

KNOWN_PROVIDERS = frozenset({"mangadex", "anilist", "wikipedia", "googlebooks"})
MAX_LANGUAGES = 6
_LANGUAGE_CODE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?")
MIN_SECRET_LENGTH = 32
MIN_SECRET_DISTINCT_CHARS = 12
MAX_REPEATED_BLOCK = 8
MAX_ORIGIN_LENGTH = 255
MAX_WEBHOOK_URL_LENGTH = 2048
MIN_WEBHOOK_SECRET_LENGTH = 32


def _is_repeated_block(value: str) -> bool:
    """True if value is a block of <= MAX_REPEATED_BLOCK chars repeated (last copy may be cut)."""
    return any(
        (value[:n] * (len(value) // n + 1))[: len(value)] == value
        for n in range(1, MAX_REPEATED_BLOCK + 1)
    )


def max_failures_from_one_address(
    max_failures: int, window: int, lockout: int, lockout_max: int
) -> int:
    """Most failures ONE address can record for one account inside one failure window.

    The attacker sends bursts of `F = max_failures` failures; each burst starts a lock, and the
    next burst can only begin after it ends. Lock k lasts `d_k = min(lockout * 2**(k-1),
    lockout_max)`, so burst j starts `s_j = d_1 + ... + d_(j-1)` seconds after burst 1. A burst
    still counts in the window of burst 1 while `s_j < window` (strict: the lock starts at the
    F-th failure, which is always after the 1st, so a burst starting exactly `window` later no
    longer sees the first failure). Result: `F * m`, where `m` = number of bursts with
    `s_j < window`. The account-wide limit (`LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS`) must exceed it,
    so a single address can never trip the lock meant for distributed guessing (which would let
    one attacker lock the owner out from new addresses).
    """
    bursts = 1
    start = 0  # offset of burst `bursts` from burst 1
    duration = lockout
    while duration < lockout_max and start + duration < window:  # doubling phase (<= ~40 steps)
        start += duration
        bursts += 1
        duration = min(duration * 2, lockout_max)
    if start + duration < window:  # capped phase: constant spacing of `lockout_max`
        bursts += (window - start - 1) // duration
    return max_failures * bursts


class Settings(BaseSettings):
    """Application settings, read from environment variables (never committed).

    `hide_input_in_errors` keeps secret values out of validation errors (and thus logs).
    Client IP behind a proxy is decided solely by uvicorn's FORWARDED_ALLOW_IPS.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # No default on purpose: the app must refuse to start without a real secret.
    SECRET_KEY: str = Field(min_length=MIN_SECRET_LENGTH)
    ALLOWED_ORIGINS: list[str] = Field(default_factory=list)
    COOKIE_SECURE: bool = True
    LIBRARY_PATH: Path = Path("/library")
    DATABASE_URL: str = "sqlite:///./data/app.db"
    # Folder with Alembic's env.py. None = MIGRATIONS_DIR env var / repo layout (see migrator.py).
    MIGRATIONS_DIR: Path | None = None
    # Folder with the built frontend (Vite `dist/`) served by the app itself (see api/spa.py).
    # Empty/unset = the app serves no static files (development: Vite serves the frontend).
    FRONTEND_DIST_DIR: Path | None = None

    # Writable folder for server-made files (downloaded covers in `<DATA_DIR>/covers`). Never
    # derived from a client or from the network. In the container it is the volume `/data`.
    DATA_DIR: Path = Path("./data")

    # Public metadata sources (covers + descriptions). The ONLY outbound network use of the app, to
    # a fixed list of hosts (adapters/http/safe_gateway.py). false = no external access at all.
    METADATA_ENABLED: bool = True
    # Comma-separated, in order of preference. mangadex/anilist give cover + description;
    # wikipedia/googlebooks give a Portuguese description only (strong match required).
    METADATA_PROVIDERS: str = "mangadex,anilist,wikipedia,googlebooks"
    # Last resort for the description: automatic English -> Portuguese translation of the public
    # synopsis (marked as translated). METADATA_ENABLED=false still switches off everything.
    METADATA_TRANSLATE_ENABLED: bool = True
    METADATA_LANGUAGES: str = "pt-br,pt,en"  # description language preference, best first
    METADATA_HTTP_TIMEOUT_SECONDS: int = Field(default=15, gt=0, le=60)  # whole request
    METADATA_MAX_PER_RUN: int = Field(default=25, gt=0, le=1000)  # series per enrichment run

    # Version of the running image (build-arg of the release workflow). "dev" or anything that is
    # not a semantic version switches the release check off (state "unknown", no network).
    APP_VERSION: str = Field(default="dev", max_length=64)
    # New-release notice for admins + approval by webhook. The app never touches Docker: it asks
    # the operator's deploy agent (infra/deploy-hook) through a signed webhook. The webhook URL is
    # configuration ONLY (no endpoint can change it); the secret never appears in logs or errors.
    UPDATE_CHECK_ENABLED: bool = True
    UPDATE_REPOSITORY: str = "Andre-Bueno/biblioteca-pwa"
    UPDATE_CHECK_INTERVAL_HOURS: int = Field(default=6, ge=1, le=168)
    UPDATE_WEBHOOK_URL: str | None = None
    UPDATE_WEBHOOK_SECRET: SecretStr | None = None
    # http is accepted only for loopback / private / CGNAT (Tailscale) destinations, checked after
    # the name is resolved; https is always accepted.
    UPDATE_WEBHOOK_ALLOW_HTTP: bool = False

    # Safety limits for archive/folder readers (see domain.library.ExtractorLimits).
    EXTRACTOR_MAX_ENTRIES: int = Field(default=10_000, gt=0)
    EXTRACTOR_MAX_TOTAL_UNCOMPRESSED_BYTES: int = Field(default=4 * 1024**3, gt=0)
    EXTRACTOR_MAX_PAGE_BYTES: int = Field(default=64 * 1024**2, gt=0)
    EXTRACTOR_MAX_COMPRESSION_RATIO: int = Field(default=100, gt=0)

    # Request bodies under /api larger than this are refused with 413 (the API only takes small
    # JSON documents).
    MAX_BODY_BYTES: int = Field(default=64 * 1024, gt=0)

    # Audit log rows older than this are deleted opportunistically (login, refresh) or by the
    # `purge` CLI command.
    AUDIT_RETENTION_DAYS: int = Field(default=180, gt=0)

    # Read only to warn at startup (uvicorn itself consumes this variable): empty or "*" means the
    # client IP seen by the app may be wrong or forgeable. Never used to derive a client IP here.
    FORWARDED_ALLOW_IPS: str = ""

    # Sessions. The access token is short; the refresh token rotates on every use; the session
    # (refresh family) has an absolute lifetime no matter how often it is refreshed.
    ACCESS_TOKEN_TTL_SECONDS: int = Field(default=900, gt=0)
    REFRESH_TOKEN_TTL_SECONDS: int = Field(default=2_592_000, gt=0)
    SESSION_ABSOLUTE_TTL_SECONDS: int = Field(default=7_776_000, gt=0)
    # A refresh token presented again within this many seconds of its first use (two tabs, a
    # retry after a lost response) gets a sibling session instead of being treated as theft.
    # Reuse after the window revokes the whole session. 0 disables the tolerance.
    REFRESH_REUSE_GRACE_SECONDS: int = Field(default=10, ge=0, le=60)

    # Login lockout: failures counted inside the window trigger a lockout that grows
    # progressively (starting at LOGIN_LOCKOUT_SECONDS, capped at LOGIN_LOCKOUT_MAX_SECONDS).
    # Per (client address, account) pair: the PRIMARY per-account limit.
    LOGIN_MAX_FAILURES_ACCOUNT: int = Field(default=5, gt=0)
    # Per account across ALL addresses (distributed guessing). Higher than the pair limit so one
    # address alone cannot trip it; it only applies to addresses without a recent success.
    LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS: int = Field(default=15, gt=0)
    LOGIN_MAX_FAILURES_IP: int = Field(default=20, gt=0)
    LOGIN_FAILURE_WINDOW_SECONDS: int = Field(default=900, gt=0)
    LOGIN_LOCKOUT_SECONDS: int = Field(default=300, gt=0)
    LOGIN_LOCKOUT_MAX_SECONDS: int = Field(default=3600, gt=0)
    # An address with a successful login for an account in this period is "trusted" for it and
    # is not subject to the account-wide (all addresses) lock; see services/auth_service.py.
    LOGIN_TRUSTED_IP_WINDOW_SECONDS: int = Field(default=2_592_000, gt=0)

    # Rate limit per client IP (token bucket, in memory; see adapters/security/rate_limiter.py).
    # `*_PER_MINUTE` is the sustained rate, `*_BURST` the bucket size. /api/v1/auth/* is
    # stricter and is counted in addition to the global /api limit.
    RATE_LIMIT_API_PER_MINUTE: int = Field(default=600, gt=0)
    RATE_LIMIT_API_BURST: int = Field(default=200, gt=0)
    RATE_LIMIT_AUTH_PER_MINUTE: int = Field(default=20, gt=0)
    RATE_LIMIT_AUTH_BURST: int = Field(default=10, gt=0)

    @field_validator("METADATA_PROVIDERS")
    @classmethod
    def _known_providers(cls, value: str) -> str:
        names = [n.strip().lower() for n in value.split(",") if n.strip()]
        if not names or len(set(names)) != len(names) or not set(names) <= KNOWN_PROVIDERS:
            raise ValueError(
                "METADATA_PROVIDERS must be a comma-separated list of: "
                + ", ".join(sorted(KNOWN_PROVIDERS))
            )
        return ",".join(names)

    @field_validator("METADATA_LANGUAGES")
    @classmethod
    def _language_codes(cls, value: str) -> str:
        codes = [c.strip().lower() for c in value.split(",") if c.strip()]
        if (
            not codes
            or len(codes) > MAX_LANGUAGES
            or not all(_LANGUAGE_CODE.fullmatch(c) for c in codes)
        ):
            raise ValueError("METADATA_LANGUAGES must be language codes like pt-br,pt,en")
        return ",".join(codes)

    @property
    def metadata_providers(self) -> tuple[str, ...]:
        return tuple(self.METADATA_PROVIDERS.split(","))

    @property
    def metadata_languages(self) -> tuple[str, ...]:
        return tuple(self.METADATA_LANGUAGES.split(","))

    @field_validator("UPDATE_WEBHOOK_URL", "UPDATE_WEBHOOK_SECRET", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        # compose passes "" for an unset variable
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("UPDATE_REPOSITORY")
    @classmethod
    def _repository(cls, value: str) -> str:
        if not valid_repository(value):
            raise ValueError("UPDATE_REPOSITORY must look like owner/name")
        return value

    @field_validator("UPDATE_WEBHOOK_URL")
    @classmethod
    def _webhook_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # Messages never include the URL (it may carry a path token).
        if len(value) > MAX_WEBHOOK_URL_LENGTH or any(not 32 < ord(c) < 127 for c in value):
            raise ValueError("UPDATE_WEBHOOK_URL must be a plain ASCII URL of at most 2048 chars")
        try:
            parts = urlsplit(value)
            port = parts.port
            valid = (
                parts.scheme in ("http", "https")
                and bool(parts.hostname)
                and parts.username is None
                and parts.password is None
                and "@" not in parts.netloc
                and "\\" not in value
                and not parts.fragment
                and port != 0
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(
                "UPDATE_WEBHOOK_URL must be http(s)://host[:port]/path without credentials"
            )
        return value

    @field_validator("UPDATE_WEBHOOK_SECRET")
    @classmethod
    def _webhook_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value()
        if len(secret) < MIN_WEBHOOK_SECRET_LENGTH:
            raise ValueError(
                f"UPDATE_WEBHOOK_SECRET must have at least {MIN_WEBHOOK_SECRET_LENGTH} characters"
            )
        if secret != secret.strip():
            raise ValueError("UPDATE_WEBHOOK_SECRET must not have leading or trailing whitespace")
        return value

    @model_validator(mode="after")
    def _webhook_consistent(self) -> "Settings":
        if (self.UPDATE_WEBHOOK_URL is None) != (self.UPDATE_WEBHOOK_SECRET is None):
            raise ValueError("UPDATE_WEBHOOK_URL and UPDATE_WEBHOOK_SECRET must be set together")
        if self.UPDATE_WEBHOOK_URL is not None:
            parts = urlsplit(self.UPDATE_WEBHOOK_URL)
            if parts.scheme == "http":
                if not self.UPDATE_WEBHOOK_ALLOW_HTTP:
                    raise ValueError("UPDATE_WEBHOOK_URL must be https unless ALLOW_HTTP is set")
                host = parts.hostname or ""
                try:
                    ipaddress.ip_address(host)
                except ValueError:
                    pass  # a name: its address is checked when the request is made
                else:
                    if not is_operator_network(host):
                        raise ValueError(
                            "UPDATE_WEBHOOK_URL over http must point to a loopback, private or "
                            "CGNAT address"
                        )
        return self

    @field_validator("FRONTEND_DIST_DIR", mode="before")
    @classmethod
    def _frontend_dist(cls, value: object) -> object:
        # An empty variable (compose passes "") means "serve nothing"; Path("") would be ".".
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("FRONTEND_DIST_DIR")
    @classmethod
    def _frontend_dist_exists(cls, value: Path | None) -> Path | None:
        if value is not None and not (value / "index.html").is_file():
            raise ValueError("FRONTEND_DIST_DIR must be a folder containing index.html")
        return value

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def _exact_origins(cls, value: list[str]) -> list[str]:
        # Credentials (cookies) are always on, so "*" (or any pattern) is never acceptable.
        normalized: list[str] = []
        for origin in value:
            if len(origin) > MAX_ORIGIN_LENGTH or "*" in origin:
                raise ValueError("ALLOWED_ORIGINS must be exact origins (no wildcards)")
            try:
                parts = urlsplit(origin)
                valid = (
                    parts.scheme in ("http", "https")
                    and bool(parts.hostname)
                    and parts.username is None
                    and parts.password is None
                    and parts.path == ""
                    and not parts.query
                    and not parts.fragment
                    and origin == f"{parts.scheme}://{parts.netloc}"
                    and parts.port != 0
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(
                    "ALLOWED_ORIGINS entries must be exact origins like https://host[:port] "
                    "(no path, query or trailing slash)"
                )
            normalized.append(origin.lower())
        return normalized

    @model_validator(mode="after")
    def _consistent_limits(self) -> "Settings":
        if self.LOGIN_LOCKOUT_MAX_SECONDS < self.LOGIN_LOCKOUT_SECONDS:
            raise ValueError("LOGIN_LOCKOUT_MAX_SECONDS must be >= LOGIN_LOCKOUT_SECONDS")
        if self.SESSION_ABSOLUTE_TTL_SECONDS < self.REFRESH_TOKEN_TTL_SECONDS:
            raise ValueError("SESSION_ABSOLUTE_TTL_SECONDS must be >= REFRESH_TOKEN_TTL_SECONDS")
        self._check_login_lockout_limits()
        return self

    def _check_login_lockout_limits(self) -> None:
        account = self.LOGIN_MAX_FAILURES_ACCOUNT
        if account >= self.LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS:
            raise ValueError(
                "LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS must be > LOGIN_MAX_FAILURES_ACCOUNT"
            )
        if account > self.LOGIN_MAX_FAILURES_IP:
            raise ValueError("LOGIN_MAX_FAILURES_IP must be >= LOGIN_MAX_FAILURES_ACCOUNT")
        worst = max_failures_from_one_address(
            account,
            self.LOGIN_FAILURE_WINDOW_SECONDS,
            self.LOGIN_LOCKOUT_SECONDS,
            self.LOGIN_LOCKOUT_MAX_SECONDS,
        )
        if worst >= self.LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS:
            raise ValueError(
                "a single address could trip the account-wide lock: with these "
                "LOGIN_MAX_FAILURES_ACCOUNT / LOGIN_FAILURE_WINDOW_SECONDS / LOGIN_LOCKOUT_SECONDS "
                f"/ LOGIN_LOCKOUT_MAX_SECONDS it can make {worst} failures inside one window; "
                "LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS must be greater than that"
            )

    @field_validator("SECRET_KEY")
    @classmethod
    def _reject_weak_secret(cls, value: str) -> str:
        # Messages must never include the value itself.
        if value != value.strip():
            raise ValueError("SECRET_KEY must not have leading or trailing whitespace")
        if len(set(value)) < MIN_SECRET_DISTINCT_CHARS:
            raise ValueError(
                f"SECRET_KEY must contain at least {MIN_SECRET_DISTINCT_CHARS} distinct characters"
            )
        if _is_repeated_block(value):
            raise ValueError(
                f"SECRET_KEY must not be a block of {MAX_REPEATED_BLOCK} or fewer characters "
                "repeated"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
