"""REG-006 (FIND-2026-001): a guessed FORWARDED_ALLOW_IPS default collapsed all clients into one IP.

Bug: compose defaulted FORWARDED_ALLOW_IPS to 172.17.0.1 (the default Docker bridge gateway) while
the compose project network has another gateway, and the Dockerfile had a different default
(127.0.0.1). Behind a host proxy the app then saw ONE client IP, so 20 bad logins from anyone
locked the login of everybody. Fix: no default anywhere (compose and image refuse to start without
it), plus a startup warning when it is empty or "*".
"""

import logging
import re
from pathlib import Path

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

from auth_fakes import Env, make_settings

ROOT = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_compose_requires_the_variable_and_has_no_guessed_default() -> None:
    lines = [
        line.strip()
        for line in _read("infra/compose.example.yml").splitlines()
        if line.strip().startswith("FORWARDED_ALLOW_IPS:")
    ]
    assert len(lines) == 1
    assert "${FORWARDED_ALLOW_IPS:?" in lines[0]
    assert ":-" not in lines[0]


@pytest.mark.parametrize(
    "path",
    ["infra/compose.example.yml", ".env.example", "infra/Dockerfile", "infra/entrypoint.sh"],
)
def test_no_guessed_gateway_address_in_deploy_files(path: str) -> None:
    assert "172.17.0.1" not in _read(path)


def test_image_has_no_second_default_and_the_entrypoint_requires_the_variable() -> None:
    assert "FORWARDED_ALLOW_IPS=" not in _read("infra/Dockerfile")  # no ENV default
    entrypoint = _read("infra/entrypoint.sh")
    assert "FORWARDED_ALLOW_IPS=" not in entrypoint  # no default assigned either
    assert ":-}" in entrypoint and "FORWARDED_ALLOW_IPS" in entrypoint
    # the container refuses to start without it, and hands the value to uvicorn
    assert re.search(r'\[ -n "\$\{FORWARDED_ALLOW_IPS:-\}" \] \|\| fail', entrypoint)
    assert '--forwarded-allow-ips "${FORWARDED_ALLOW_IPS}"' in entrypoint


def test_env_example_leaves_the_variable_empty_so_it_must_be_chosen() -> None:
    assert re.search(r"^FORWARDED_ALLOW_IPS=\s*$", _read(".env.example"), re.MULTILINE)


@pytest.mark.parametrize("value", ["", "*"])
def test_startup_warns_when_proxy_trust_is_empty_or_wildcard(
    value: str, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(make_settings("sqlite:///unused.db", FORWARDED_ALLOW_IPS=value))
    with caplog.at_level(logging.WARNING, logger="app.main"), TestClient(app):
        pass
    warned = [r.getMessage() for r in caplog.records if "FORWARDED_ALLOW_IPS" in r.getMessage()]
    assert warned
    assert "unused.db" not in " ".join(warned)  # generic message, no configuration echoed


def test_startup_does_not_warn_with_an_explicit_proxy_address(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(make_settings("sqlite:///unused.db", FORWARDED_ALLOW_IPS="172.28.0.1"))
    with caplog.at_level(logging.WARNING, logger="app.main"), TestClient(app):
        pass
    assert not [r for r in caplog.records if "FORWARDED_ALLOW_IPS" in r.getMessage()]


def test_private_client_address_logs_one_generic_warning(
    env: Env, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.api.auth as auth_api

    monkeypatch.setattr(auth_api, "_private_client_warned", False)
    with caplog.at_level(logging.WARNING, logger="app.api.auth"):
        env.client("10.0.0.1").login()
        env.client("10.0.0.1").login()
    warned = [r.getMessage() for r in caplog.records if "FORWARDED_ALLOW_IPS" in r.getMessage()]
    assert len(warned) == 1
    assert "10.0.0.1" not in warned[0]
