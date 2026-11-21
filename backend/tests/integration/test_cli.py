import getpass
from collections.abc import Iterator

import pytest
from app import cli
from app.core.config import get_settings


@pytest.fixture
def cli_env(db_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    yield db_url
    get_settings.cache_clear()


def _answers(monkeypatch: pytest.MonkeyPatch, *answers: str) -> list[str]:
    """Replace getpass; returns the list of prompts shown."""
    prompts: list[str] = []
    it = iter(answers)

    def fake(prompt: str = "Password: ", stream: object = None) -> str:
        prompts.append(prompt)
        return next(it)

    monkeypatch.setattr(getpass, "getpass", fake)
    return prompts


def test_migrate_then_create_list_reset_deactivate(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["migrate"]) == 0
    prompts = _answers(monkeypatch, "first good passphrase", "first good passphrase")
    assert cli.main(["create-user", "Alice", "--admin"]) == 0
    assert prompts == ["Password: ", "Repeat password: "]

    capsys.readouterr()
    assert cli.main(["list-users"]) == 0
    assert capsys.readouterr().out.strip() == "alice\tadmin\tactive"

    _answers(monkeypatch, "second good passphrase", "second good passphrase")
    assert cli.main(["reset-password", "alice"]) == 0
    assert cli.main(["deactivate-user", "alice"]) == 0
    capsys.readouterr()
    assert cli.main(["list-users"]) == 0
    assert capsys.readouterr().out.strip() == "alice\tadmin\tinactive"


def test_password_never_echoed_or_in_output(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["migrate"])
    _answers(monkeypatch, "very secret passphrase", "very secret passphrase")
    cli.main(["create-user", "bob"])
    out = capsys.readouterr()
    assert "very secret passphrase" not in out.out + out.err


def test_weak_password_rejected(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["migrate"])
    _answers(monkeypatch, "short", "short")
    assert cli.main(["create-user", "bob"]) == 1
    err = capsys.readouterr().err
    assert "at least 12" in err
    assert "short" not in err.replace("at least", "")  # message does not echo the password
    capsys.readouterr()
    assert cli.main(["list-users"]) == 0
    assert capsys.readouterr().out == ""


def test_mismatched_confirmation_rejected(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["migrate"])
    _answers(monkeypatch, "first good passphrase", "other good passphrase")
    assert cli.main(["create-user", "bob"]) == 1
    assert "do not match" in capsys.readouterr().err


def test_duplicate_and_unknown_user(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["migrate"])
    _answers(monkeypatch, *(["first good passphrase"] * 6))
    assert cli.main(["create-user", "bob"]) == 0
    assert cli.main(["create-user", "BOB"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert cli.main(["reset-password", "ghost"]) == 1
    assert cli.main(["deactivate-user", "ghost"]) == 1


def test_without_migration_gives_hint(cli_env: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["list-users"]) == 1
    assert "migrate" in capsys.readouterr().err


def test_password_cannot_be_passed_as_argument() -> None:
    with pytest.raises(SystemExit):
        cli.main(["create-user", "bob", "--password", "x" * 20])


def test_audit_trail_written(cli_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlite3

    cli.main(["migrate"])
    _answers(monkeypatch, "first good passphrase", "first good passphrase")
    cli.main(["create-user", "bob"])
    with sqlite3.connect(cli_env.removeprefix("sqlite:///")) as conn:
        events = [r[0] for r in conn.execute("SELECT event FROM audit_log")]
    assert events == ["user.created"]
