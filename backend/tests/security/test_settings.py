from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.core.config import Settings, get_settings, max_failures_from_one_address
from app.domain.lockout import LockoutPolicy, locked_until
from app.main import create_app
from pydantic import ValidationError

STRONG_KEY = "Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0"


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)  # avoid picking up a stray .env
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_create_app_fails_without_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        create_app()


def test_create_app_fails_with_short_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "short-key-1234")
    with pytest.raises(ValidationError):
        create_app()


@pytest.mark.parametrize(
    "key",
    [
        "a" * 64,
        "ab" * 32,
        "abcd" * 16,
        "0" * 40,
        "abcdefgh" * 4,  # 8 distinct chars, repeated block
        "Zk3!pQ9v" * 5,  # 8 distinct chars, repeated block
        "abcdefghijk" * 3,  # 11 distinct chars (< 12)
    ],
)
def test_create_app_fails_with_low_entropy_secret_key(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    monkeypatch.setenv("SECRET_KEY", key)
    with pytest.raises(ValidationError):
        create_app()


@pytest.mark.parametrize(
    "key",
    [
        " Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0",
        "Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0 ",
        "Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0\n",
    ],
)
def test_create_app_rejects_secret_key_with_edge_whitespace(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    monkeypatch.setenv("SECRET_KEY", key)
    with pytest.raises(ValidationError) as info:
        create_app()
    assert "Zk3!pQ9v" not in str(info.value)


def test_create_app_accepts_strong_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0")
    assert create_app().state.settings.SECRET_KEY.startswith("Zk3")


def test_new_limits_have_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0")
    cfg = create_app().state.settings
    assert cfg.MAX_BODY_BYTES == 64 * 1024
    assert cfg.AUDIT_RETENTION_DAYS == 180
    assert cfg.EXTRACTOR_MAX_COMPRESSION_RATIO == 100
    assert cfg.MIGRATIONS_DIR is None


@pytest.mark.parametrize(
    "name",
    [
        "EXTRACTOR_MAX_ENTRIES",
        "EXTRACTOR_MAX_TOTAL_UNCOMPRESSED_BYTES",
        "EXTRACTOR_MAX_PAGE_BYTES",
        "EXTRACTOR_MAX_COMPRESSION_RATIO",
        "MAX_BODY_BYTES",
        "AUDIT_RETENTION_DAYS",
    ],
)
@pytest.mark.parametrize("value", ["0", "-5"])
def test_limits_must_be_positive(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv("SECRET_KEY", "Zk3!pQ9vL2#xW7mR5tY8uB1nC4dF6gH0")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        create_app()


# --- login lockout consistency ------------------------------------------------------------


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"SECRET_KEY": STRONG_KEY, **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_default_lockout_limits_are_consistent() -> None:
    cfg = _settings()
    assert cfg.LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS > cfg.LOGIN_MAX_FAILURES_ACCOUNT
    assert cfg.LOGIN_MAX_FAILURES_IP >= cfg.LOGIN_MAX_FAILURES_ACCOUNT


@pytest.mark.parametrize("all_ips", [5, 4, 1])
def test_account_wide_limit_must_exceed_the_pair_limit(all_ips: int) -> None:
    with pytest.raises(ValidationError, match="LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS"):
        _settings(LOGIN_MAX_FAILURES_ACCOUNT=5, LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS=all_ips)


def test_ip_limit_must_not_be_below_the_pair_limit() -> None:
    with pytest.raises(ValidationError, match="LOGIN_MAX_FAILURES_IP"):
        _settings(LOGIN_MAX_FAILURES_ACCOUNT=5, LOGIN_MAX_FAILURES_IP=4)
    assert _settings(LOGIN_MAX_FAILURES_ACCOUNT=5, LOGIN_MAX_FAILURES_IP=5)


def test_one_address_must_not_be_able_to_trip_the_account_wide_lock() -> None:
    # Defaults: bursts of 5 at t=0 and t=300 s (lock 300), the next one at t=900 s is outside
    # the 900 s window => at most 10 failures from one address, below 15.
    assert max_failures_from_one_address(5, 900, 300, 3600) == 10
    # A window of 2000 s fits a third (t=900) and a fourth (t=2100 is not < 2000) burst: 15.
    assert max_failures_from_one_address(5, 2000, 300, 3600) == 15
    with pytest.raises(ValidationError, match="single address"):
        _settings(LOGIN_FAILURE_WINDOW_SECONDS=2000)  # 15 failures possible, limit is 15
    assert _settings(LOGIN_FAILURE_WINDOW_SECONDS=2000, LOGIN_MAX_FAILURES_ACCOUNT_ALL_IPS=16)


def test_error_message_states_the_numbers_without_secrets() -> None:
    with pytest.raises(ValidationError) as info:
        _settings(LOGIN_LOCKOUT_SECONDS=10, LOGIN_LOCKOUT_MAX_SECONDS=10)
    assert "Zk3!pQ9v" not in str(info.value)
    assert "failures inside one window" in str(info.value)


@pytest.mark.parametrize(
    ("failures", "window", "lockout", "lockout_max"),
    [
        (5, 900, 300, 3600),
        (5, 900, 60, 3600),
        (3, 600, 30, 120),  # lock capped: constant spacing after the doubling phase
        (4, 300, 10, 10),  # no doubling at all
        (5, 100, 300, 3600),  # window shorter than the lock: a single burst
    ],
)
def test_formula_bounds_a_real_single_address_attack(
    failures: int, window: int, lockout: int, lockout_max: int
) -> None:
    """Simulate the worst attacker (bursts the instant a lock ends) against the real policy."""
    pair = LockoutPolicy(
        failures,
        timedelta(seconds=window),
        timedelta(seconds=lockout),
        timedelta(seconds=lockout_max),
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    recorded: list[datetime] = []
    for second in range(window * 3):
        for tick in range(failures):
            now = start + timedelta(seconds=second, milliseconds=tick)
            if locked_until(recorded, pair, now) is None:
                recorded.append(now)  # failures made while locked are not recorded
    # Most failures inside any span shorter than `window` (what the account-wide counter sees).
    most = max(
        sum(1 for other in recorded if at <= other < at + timedelta(seconds=window))
        for at in recorded
    )
    assert most <= max_failures_from_one_address(failures, window, lockout, lockout_max)


# ------------------------------------------------------------------ metadata (external sources)


def _settings(**values: object) -> Settings:
    merged: dict[str, object] = {"SECRET_KEY": STRONG_KEY, **values}
    return Settings(_env_file=None, **merged)  # type: ignore[arg-type]


def test_metadata_defaults() -> None:
    cfg = _settings()
    assert cfg.METADATA_ENABLED is True
    assert cfg.metadata_providers == ("mangadex", "anilist", "wikipedia", "googlebooks")
    assert cfg.METADATA_TRANSLATE_ENABLED is True
    assert cfg.metadata_languages == ("pt-br", "pt", "en")
    assert (cfg.METADATA_HTTP_TIMEOUT_SECONDS, cfg.METADATA_MAX_PER_RUN) == (15, 25)
    assert Path("./data") == cfg.DATA_DIR


def test_metadata_can_be_switched_off_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("METADATA_ENABLED", "false")
    assert Settings(_env_file=None).METADATA_ENABLED is False  # type: ignore[call-arg]


@pytest.mark.parametrize("field", ["METADATA_HTTP_TIMEOUT_SECONDS", "METADATA_MAX_PER_RUN"])
@pytest.mark.parametrize("value", [0, -1])
def test_metadata_numbers_must_be_positive(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [("METADATA_HTTP_TIMEOUT_SECONDS", 61), ("METADATA_MAX_PER_RUN", 1001)],
)
def test_metadata_numbers_have_an_upper_bound(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: value})


@pytest.mark.parametrize(
    "value",
    [
        "",
        " , ",
        "unknown",
        "mangadex,evil",
        "mangadex,mangadex",
        "https://evil.example",
        "mangadex;anilist",
    ],
)
def test_metadata_providers_must_be_known_names(value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(METADATA_PROVIDERS=value)


def test_metadata_providers_are_normalized_and_may_be_a_subset() -> None:
    assert _settings(METADATA_PROVIDERS=" AniList ").metadata_providers == ("anilist",)
    assert _settings(METADATA_PROVIDERS="anilist, mangadex").metadata_providers == (
        "anilist",
        "mangadex",
    )


@pytest.mark.parametrize(
    "value", ["", "x", "pt_BR!", "../x", "pt-br," + ",".join(["en"] * 6), "a" * 30, "pt br"]
)
def test_metadata_languages_must_be_language_codes(value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(METADATA_LANGUAGES=value)


def test_metadata_languages_are_normalized() -> None:
    assert _settings(METADATA_LANGUAGES="PT-BR, en").metadata_languages == ("pt-br", "en")


def test_metadata_translation_switch_and_new_provider_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("METADATA_TRANSLATE_ENABLED", "false")
    assert Settings(_env_file=None).METADATA_TRANSLATE_ENABLED is False  # type: ignore[call-arg]
    cfg = _settings(METADATA_PROVIDERS="mangadex, WikiPedia,googlebooks")
    assert cfg.metadata_providers == ("mangadex", "wikipedia", "googlebooks")
    for bad in ("wikipedia,wikipedia", "google", "mymemory", "wikipedia,en.wikipedia.org"):
        with pytest.raises(ValidationError):
            _settings(METADATA_PROVIDERS=bad)
