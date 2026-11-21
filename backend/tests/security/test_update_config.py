"""Validation of the update settings: the webhook URL is configuration only; the secret never
leaks."""

import pytest
from app.core.config import Settings
from pydantic import SecretStr, ValidationError

from auth_fakes import TEST_SECRET

SECRET = "a-webhook-secret-of-at-least-32-characters-xyz"  # secret-scan:allow (fictitious)


def settings(**kw: object) -> Settings:
    values: dict[str, object] = {"SECRET_KEY": TEST_SECRET} | kw
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_defaults() -> None:
    s = settings()
    assert s.APP_VERSION == "dev" and s.UPDATE_CHECK_ENABLED is True
    assert s.UPDATE_REPOSITORY == "Andre-Bueno/biblioteca-pwa"
    assert s.UPDATE_CHECK_INTERVAL_HOURS == 6
    assert s.UPDATE_WEBHOOK_URL is None and s.UPDATE_WEBHOOK_SECRET is None
    assert s.UPDATE_WEBHOOK_ALLOW_HTTP is False


def test_a_valid_https_webhook() -> None:
    s = settings(
        UPDATE_WEBHOOK_URL="https://deploy.example.com:8443/update", UPDATE_WEBHOOK_SECRET=SECRET
    )
    assert s.UPDATE_WEBHOOK_URL == "https://deploy.example.com:8443/update"
    assert isinstance(s.UPDATE_WEBHOOK_SECRET, SecretStr)
    assert s.UPDATE_WEBHOOK_SECRET.get_secret_value() == SECRET


def test_empty_values_from_compose_mean_unset() -> None:
    s = settings(UPDATE_WEBHOOK_URL="", UPDATE_WEBHOOK_SECRET="  ")
    assert s.UPDATE_WEBHOOK_URL is None and s.UPDATE_WEBHOOK_SECRET is None


@pytest.mark.parametrize("hours", [1, 6, 168])
def test_interval_inside_the_bounds(hours: int) -> None:
    assert hours == settings(UPDATE_CHECK_INTERVAL_HOURS=hours).UPDATE_CHECK_INTERVAL_HOURS


@pytest.mark.parametrize("hours", [0, -1, 169, 10_000])
def test_interval_outside_the_bounds(hours: int) -> None:
    with pytest.raises(ValidationError):
        settings(UPDATE_CHECK_INTERVAL_HOURS=hours)


@pytest.mark.parametrize(
    "repo",
    [
        "",
        "owner",
        "a/b/c",
        "a b/c",
        "../x",
        "a/..",
        "./a",
        "a/b;rm",
        "a/b?x=1",
        "a/" + "b" * 101,
        "é/x",
        "a/b\n",
        "https://github.com/a/b",
    ],
)
def test_repository_must_look_like_owner_slash_name(repo: str) -> None:
    with pytest.raises(ValidationError):
        settings(UPDATE_REPOSITORY=repo)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://deploy.example.com/update",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "deploy.example.com/update",
        "https://",
        "https://user:pass@deploy.example.com/update",
        "https://user@deploy.example.com/update",
        "https://deploy.example.com/update#frag",
        "https://deploy.example.com:0/update",
        "https://deploy.example.com:99999/update",
        "https://deploy.example.com\\@evil.example/update",
        "https://deploy.example.com/up date",
        "https://deploy.example.com/" + "a" * 2100,
        "https://deploy.example.com/\x00",
        "https://dëploy.example.com/update",
    ],
)
def test_bad_webhook_urls_are_refused_without_echoing_them(url: str) -> None:
    with pytest.raises(ValidationError) as info:
        settings(
            UPDATE_WEBHOOK_URL=url, UPDATE_WEBHOOK_SECRET=SECRET, UPDATE_WEBHOOK_ALLOW_HTTP=True
        )
    assert "deploy.example.com" not in str(info.value) and SECRET not in str(info.value)


@pytest.mark.parametrize(
    "url", ["http://deploy.example.com/update", "http://127.0.0.1:9110/update"]
)
def test_http_needs_the_explicit_flag(url: str) -> None:
    with pytest.raises(ValidationError):
        settings(UPDATE_WEBHOOK_URL=url, UPDATE_WEBHOOK_SECRET=SECRET)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9110/update",
        "http://[::1]:9110/update",
        "http://10.0.0.5/update",
        "http://192.168.1.2:8080/update",
        "http://100.64.0.9/update",
        "http://100.101.102.103/update",
        "http://hook.tailnet.example/update",  # a name: its address is checked per request
        "http://localhost:9110/update",
    ],
)
def test_http_with_the_flag_for_operator_networks(url: str) -> None:
    s = settings(
        UPDATE_WEBHOOK_URL=url, UPDATE_WEBHOOK_SECRET=SECRET, UPDATE_WEBHOOK_ALLOW_HTTP=True
    )
    assert url == s.UPDATE_WEBHOOK_URL


@pytest.mark.parametrize(
    "url",
    [
        "http://8.8.8.8/update",
        "http://169.254.169.254/latest",
        "http://100.63.0.1/x",
        "http://172.32.0.1/x",
        "http://0.0.0.0/x",
    ],
)
def test_http_to_a_public_or_special_address_is_refused_even_with_the_flag(url: str) -> None:
    with pytest.raises(ValidationError):
        settings(
            UPDATE_WEBHOOK_URL=url, UPDATE_WEBHOOK_SECRET=SECRET, UPDATE_WEBHOOK_ALLOW_HTTP=True
        )


def test_https_to_a_public_address_is_fine() -> None:
    settings(UPDATE_WEBHOOK_URL="https://8.8.8.8/update", UPDATE_WEBHOOK_SECRET=SECRET)


@pytest.mark.parametrize("secret", ["short", "x" * 31, " " + "y" * 40, "z" * 40 + " "])
def test_weak_secrets_are_refused_and_never_echoed(secret: str) -> None:
    with pytest.raises(ValidationError) as info:
        settings(UPDATE_WEBHOOK_URL="https://deploy.example.com/u", UPDATE_WEBHOOK_SECRET=secret)
    # str()/repr() of the error (what start-up logs) never contains the value, like SECRET_KEY.
    # (`.errors()` is the programmatic view and carries `input`; nothing logs it.)
    assert secret.strip() not in str(info.value) and secret.strip() not in repr(info.value)


def test_exactly_32_characters_is_enough() -> None:
    settings(UPDATE_WEBHOOK_URL="https://deploy.example.com/u", UPDATE_WEBHOOK_SECRET="k" * 32)


def test_url_and_secret_come_together() -> None:
    with pytest.raises(ValidationError) as only_url:
        settings(UPDATE_WEBHOOK_URL="https://deploy.example.com/u")
    with pytest.raises(ValidationError) as only_secret:
        settings(UPDATE_WEBHOOK_SECRET=SECRET)
    assert SECRET not in str(only_secret.value) and "deploy.example.com" not in str(only_url.value)


def test_the_secret_never_appears_in_repr_or_dumps() -> None:
    s = settings(UPDATE_WEBHOOK_URL="https://deploy.example.com/u", UPDATE_WEBHOOK_SECRET=SECRET)
    for text in (repr(s), str(s), repr(s.UPDATE_WEBHOOK_SECRET), s.model_dump_json()):
        assert SECRET not in text
    assert SECRET not in str(s.model_dump())


def test_secret_from_the_environment_is_not_echoed_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPDATE_WEBHOOK_SECRET", "tiny-but-secret")
    monkeypatch.setenv("UPDATE_WEBHOOK_URL", "https://deploy.example.com/u")
    with pytest.raises(ValidationError) as info:
        Settings(_env_file=None)  # type: ignore[call-arg]
    assert "tiny-but-secret" not in str(info.value)
