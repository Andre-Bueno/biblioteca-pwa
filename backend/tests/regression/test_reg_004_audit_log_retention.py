"""REG-004: the audit log grew forever.

Bug: audit_log rows were never deleted. Cause: only refresh tokens and login attempts had an
opportunistic purge. Now a login purges events older than AUDIT_RETENTION_DAYS (default 180).
"""

from datetime import timedelta

from sqlalchemy import create_engine, text

from auth_fakes import Env


def _events(url: str) -> list[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return [r[0] for r in conn.execute(text("SELECT event FROM audit_log ORDER BY id"))]
    finally:
        engine.dispose()


def test_old_audit_events_are_purged_on_login_and_recent_ones_kept(db_url: str) -> None:
    env = Env(db_url)
    env.create_user()  # audit event "user.created" at the clock's start
    env.clock.current += timedelta(days=100)
    env.container.user_service.create_user("bob", "another good passphrase")  # 100 days old later
    env.clock.current += timedelta(days=100)  # now: first event is 200d old, second is 100d old
    assert env.client().login().status_code == 200
    events = _events(db_url)
    assert events.count("user.created") == 1  # only the 100-day-old one survived
    assert "login.success" in events
