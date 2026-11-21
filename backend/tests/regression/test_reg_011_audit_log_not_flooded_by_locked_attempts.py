"""REG-011 (FIND-2026-006): anonymous clients could grow audit_log without bound.

Bug: every locked attempt wrote a `login.locked` row (543 rows against 228 real failures in the
audit), and the retention purge ran only after a successful login. Fix: at most one `login.locked`
event per client address per window, the purge is isolated (never breaks a good login), marked
done only on success, retried later after a failure, runs from login failures, refresh and the
`purge` CLI command too.
"""

import logging
from datetime import UTC

import pytest
from app import cli
from app.core.config import get_settings
from app.domain.auth import LoginLockedError
from app.domain.errors import DataAccessError

from auth_fakes import PASSWORD, Rig


def _locked_rig() -> Rig:
    rig = Rig()
    rig.fail(5)  # locks (9.9.9.9, alice)
    return rig


def test_many_locked_attempts_write_one_audit_row_per_window() -> None:
    rig = _locked_rig()
    for _ in range(200):
        with pytest.raises(LoginLockedError):
            rig.service.login("alice", PASSWORD, "9.9.9.9")
    assert rig.audit.names().count("login.locked") == 1
    rig.clock.advance(61)
    with pytest.raises(LoginLockedError):
        rig.service.login("alice", PASSWORD, "9.9.9.9")
    assert rig.audit.names().count("login.locked") == 2


def test_locked_events_are_deduplicated_per_address_even_when_the_username_changes() -> None:
    rig = Rig()
    for i in range(20):  # 20 different usernames from one address trips the address lock
        rig.fail(1, ip="6.6.6.6", username=f"user{i}")
    for i in range(100):
        with pytest.raises(LoginLockedError):
            rig.service.login(f"user{i}", PASSWORD, "6.6.6.6")
    assert rig.audit.names().count("login.locked") == 1


def test_a_failing_purge_never_breaks_a_successful_login(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = Rig()
    calls = 0

    def boom(*_args: object) -> int:
        nonlocal calls
        calls += 1
        raise DataAccessError("database error: secret detail")

    rig.attempts.purge = boom  # type: ignore[method-assign]
    with caplog.at_level(logging.WARNING, logger="app.services.auth_service"):
        session = rig.service.login("alice", PASSWORD, "1.1.1.1")
    assert session.access_token
    assert "secret detail" not in caplog.text  # generic message only
    assert calls == 1
    # Not marked as done: it is tried again once the retry delay has passed.
    rig.clock.advance(6 * 60)
    rig.service.login("alice", PASSWORD, "1.1.1.1")
    assert calls == 2


def test_purge_runs_on_failed_login_and_on_refresh_too() -> None:
    rig = Rig()
    rig.fail(1)  # first purge happens here (no successful login yet)
    assert len(rig.audit.purged_before) == 1
    session = rig.service.login("alice", PASSWORD, "1.1.1.1")
    rig.clock.advance(2 * 3600)
    rig.service.refresh(session.refresh_token)
    assert len(rig.audit.purged_before) == 2


def test_purge_command_removes_old_audit_rows(
    db_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from datetime import datetime

    from sqlalchemy import text

    from auth_fakes import Env

    env = Env(db_url)
    with env.container.session_factory() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO audit_log (at, event) VALUES (:at, 'old.event'), (:now, 'new.event')"
            ),
            {"at": datetime(2000, 1, 1), "now": datetime.now(UTC).replace(tzinfo=None)},
        )
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        assert cli.main(["purge"]) == 0
    finally:
        get_settings.cache_clear()
    assert "purge" in capsys.readouterr().out.lower()
    with env.container.session_factory() as session:
        events = [r[0] for r in session.execute(text("SELECT event FROM audit_log"))]
    assert events == ["new.event"]
