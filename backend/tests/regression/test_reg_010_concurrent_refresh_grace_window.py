"""REG-010 (FIND-2026-005): two simultaneous refreshes with the same cookie killed the session.

Bug: the loser of the `mark_used` race was treated as token theft and revoked the whole family,
including the winner's fresh token (SPA with two tabs, or a retry after a lost response, logged
the user out). Fix: `rotate` marks the token used and stores its successor in ONE transaction, and a
short, configurable grace window (REFRESH_REUSE_GRACE_SECONDS, default 10) lets a second
presentation of a just-used token receive a sibling session. Reuse after the window still revokes
the family and is audited.
"""

import threading
from dataclasses import replace
from datetime import timedelta

import pytest
from app.domain.auth import InvalidSessionError, NotAuthenticatedError
from app.services.auth_service import IssuedSession

from auth_fakes import DEFAULT_CONFIG, PASSWORD, Env, Rig

GRACE = timedelta(seconds=10)


def _rig() -> Rig:
    return Rig(replace(DEFAULT_CONFIG, refresh_reuse_grace=GRACE))


def test_second_presentation_inside_the_window_gets_a_working_session() -> None:
    rig = _rig()
    first = rig.service.login("alice", PASSWORD, "1.1.1.1")
    a = rig.service.refresh(first.refresh_token)
    rig.clock.advance(5)
    b = rig.service.refresh(first.refresh_token)
    assert a.refresh_token != b.refresh_token
    for session in (a, b):
        assert rig.service.current_user(session.access_token).id == "id-alice"
    rig.service.refresh(a.refresh_token)
    rig.service.refresh(b.refresh_token)
    assert "token.reuse_detected" not in rig.audit.names()


def test_reuse_after_the_window_still_revokes_the_family_and_is_audited() -> None:
    rig = _rig()
    first = rig.service.login("alice", PASSWORD, "1.1.1.1")
    newest = rig.service.refresh(first.refresh_token)
    rig.clock.advance(GRACE.total_seconds() + 1)
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(first.refresh_token)
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(newest.refresh_token)
    with pytest.raises(NotAuthenticatedError):
        rig.service.current_user(newest.access_token)
    assert "token.reuse_detected" in rig.audit.names()


def test_window_is_disabled_when_zero() -> None:
    rig = Rig()  # DEFAULT_CONFIG: no tolerance
    first = rig.service.login("alice", PASSWORD, "1.1.1.1")
    rig.service.refresh(first.refresh_token)
    with pytest.raises(InvalidSessionError):
        rig.service.refresh(first.refresh_token)


def test_concurrent_refresh_with_the_real_repository_keeps_the_session(db_url: str) -> None:
    env = Env(db_url, REFRESH_REUSE_GRACE_SECONDS=10)
    env.create_user()
    service = env.container.auth_service
    first = service.login("alice", PASSWORD, "1.1.1.1")
    results: list[IssuedSession | None] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        barrier.wait()
        try:
            results.append(service.refresh(first.refresh_token))
        except InvalidSessionError:
            results.append(None)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)

    assert len(results) == 4
    assert all(r is not None for r in results)
    sessions = [r for r in results if r is not None]
    assert len({s.refresh_token for s in sessions}) == 4
    for session in sessions:
        assert service.current_user(session.access_token).username == "alice"
        service.refresh(session.refresh_token)  # every successor is alive


def test_concurrent_refresh_then_late_reuse_is_still_detected(db_url: str) -> None:
    env = Env(db_url, REFRESH_REUSE_GRACE_SECONDS=10)
    env.create_user()
    service = env.container.auth_service
    first = service.login("alice", PASSWORD, "1.1.1.1")
    winner = service.refresh(first.refresh_token)
    env.clock.advance(11)
    with pytest.raises(InvalidSessionError):
        service.refresh(first.refresh_token)
    with pytest.raises(InvalidSessionError):
        service.refresh(winner.refresh_token)
