"""UpdateService: lazy cache, ETag, throttling, failures, `dev` builds, approval rules."""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from app.domain.errors import (
    ExternalFetchError,
    UpdateAlreadyRequested,
    UpdateNotAvailable,
    UpdateNotConfigured,
    UpdateNotifyFailed,
)
from app.domain.release import ConditionalJson
from app.services.update_service import (
    FAILURE_PAUSE,
    MAX_THROTTLE_PAUSE,
    MIN_THROTTLE_PAUSE,
    UpdateService,
)

from update_fakes import (
    ETAG,
    REPO,
    FakeAudit,
    FakeClock,
    FakeNotifier,
    FakeReleaseGateway,
    config,
    release_doc,
)

URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def make(
    gateway: FakeReleaseGateway | None = None,
    notifier: FakeNotifier | None = None,
    **cfg: object,
) -> tuple[UpdateService, FakeReleaseGateway, FakeNotifier, FakeAudit, FakeClock]:
    gw = gateway or FakeReleaseGateway()
    note = notifier or FakeNotifier()
    audit, clock = FakeAudit(), FakeClock()
    service = UpdateService(gw, note, audit, clock, config(**cfg))  # type: ignore[arg-type]
    return service, gw, note, audit, clock


# ---------------------------------------------------------------- lookup and cache


def test_first_call_looks_up_and_reports_a_newer_release() -> None:
    service, gateway, _, _, clock = make()
    info = service.info()
    assert gateway.calls == [(URL, None)]
    assert info.update_available is True and info.current == "1.0.0"
    assert info.latest is not None and info.latest.tag == "v1.1.0"
    assert info.checked_at == clock.now()
    assert info.webhook_configured is True
    assert (info.update.state, info.update.tag, info.update.requested_at) == ("idle", None, None)


def test_cache_is_served_until_the_interval_passes() -> None:
    service, gateway, _, _, clock = make()
    service.info()
    clock.advance(5 * 3600)
    service.info()
    assert len(gateway.calls) == 1
    clock.advance(3600 + 1)
    service.info()
    assert len(gateway.calls) == 2


def test_the_stored_etag_is_sent_and_a_304_only_refreshes_the_timestamp() -> None:
    service, gateway, _, _, clock = make()
    service.info()
    first_checked = service.snapshot().checked_at
    gateway.queue.append(ConditionalJson(304, None, ETAG))
    clock.advance(7 * 3600)
    info = service.info()
    assert gateway.calls[1] == (URL, ETAG)
    assert info.latest is not None and info.latest.tag == "v1.1.0"  # kept
    assert info.checked_at != first_checked and info.checked_at == clock.now()


def test_a_newer_document_replaces_the_cache_and_the_etag() -> None:
    service, gateway, _, _, clock = make()
    service.info()
    gateway.queue.append(ConditionalJson(200, release_doc("v1.2.0"), '"def"'))
    clock.advance(7 * 3600)
    assert service.info().latest.tag == "v1.2.0"  # type: ignore[union-attr]
    clock.advance(7 * 3600)
    service.info()
    assert gateway.calls[-1][1] == '"def"'


@pytest.mark.parametrize(
    "current, tag, available",
    [
        ("1.0.0", "v1.0.1", True),
        ("1.0.0", "v1.0.0", False),
        ("1.2.0", "v1.1.9", False),
        ("1.0.0-rc.1", "v1.0.0", True),  # a release is newer than its own pre-release
        ("v1.0.0", "v2.0.0", True),
        ("1.9.0", "v1.10.0", True),
    ],
)
def test_update_available_compares_versions(current: str, tag: str, available: bool) -> None:
    gateway = FakeReleaseGateway(ConditionalJson(200, release_doc(tag), ETAG))
    service, *_ = make(gateway, current=current)
    assert service.info().update_available is available


def test_unusable_release_documents_mean_no_update() -> None:
    for doc in (
        release_doc(draft=True),
        release_doc(prerelease=True),
        release_doc("1.2"),
        [],
        None,
    ):
        service, *_ = make(FakeReleaseGateway(ConditionalJson(200, doc, ETAG)))
        info = service.info()
        assert (
            info.latest is None and info.update_available is False and info.checked_at is not None
        )


# ---------------------------------------------------------------- off switches


@pytest.mark.parametrize("current", ["dev", "", "latest", "1.2", "main", "1.0.0; x"])
def test_dev_and_non_semver_builds_switch_everything_off(current: str) -> None:
    service, gateway, notifier, _, _ = make(current=current)
    info = service.info()
    service.refresh(force=True)
    assert gateway.calls == []  # no network at all
    assert (info.update_available, info.latest, info.checked_at) == (False, None, None)
    assert service.current == current
    with pytest.raises(UpdateNotAvailable):
        service.request_update("u1", "v9.9.9")
    assert notifier.sent == []


def test_check_disabled_by_configuration() -> None:
    service, gateway, _, _, _ = make(check_enabled=False)
    assert service.info().update_available is False
    service.refresh(force=True)
    assert gateway.calls == []


# ---------------------------------------------------------------- failures never break anything


@pytest.mark.parametrize("reason", ["network", "timeout", "bad_status", "invalid_json", "busy"])
def test_a_failed_lookup_keeps_the_old_value_and_pauses(reason: str) -> None:
    service, gateway, _, _, clock = make()
    service.info()
    gateway.queue.append(ExternalFetchError(reason))
    clock.advance(7 * 3600)
    info = service.info()  # does not raise
    assert info.latest is not None and info.latest.tag == "v1.1.0"
    calls = len(gateway.calls)
    service.info()
    assert len(gateway.calls) == calls  # paused: no hammering after a failure
    clock.advance(FAILURE_PAUSE.total_seconds() + 1)
    service.info()
    assert len(gateway.calls) == calls + 1


def test_an_unexpected_error_in_the_gateway_is_contained() -> None:
    service, *_ = make(FakeReleaseGateway(RuntimeError("boom")))
    assert service.info().update_available is False


def test_first_failure_leaves_an_empty_state() -> None:
    service, *_ = make(FakeReleaseGateway(ExternalFetchError("network")))
    info = service.info()
    assert (info.latest, info.checked_at, info.update_available) == (None, None, False)


# ---------------------------------------------------------------- GitHub rate limit


@pytest.mark.parametrize("status", [403, 429])
def test_throttled_answers_stop_the_lookups_until_the_reset(status: int) -> None:
    clock_now = datetime(2026, 11, 19, 12, 0, 0, 500_000, tzinfo=UTC)
    reset = int((clock_now + timedelta(minutes=30)).timestamp())
    gateway = FakeReleaseGateway(ConditionalJson(status, None, None, remaining=0, reset_at=reset))
    service, _, _, _, clock = make(gateway)
    assert service.info().latest is None
    assert len(gateway.calls) == 1
    clock.advance(20 * 60)
    service.refresh(force=True)  # even a forced check respects the pause
    service.info()
    assert len(gateway.calls) == 1
    clock.advance(11 * 60)
    service.info()
    assert len(gateway.calls) == 2


def test_retry_after_wins_and_is_bounded() -> None:
    gateway = FakeReleaseGateway(ConditionalJson(429, retry_after=120.0))
    service, _, _, _, clock = make(gateway)
    service.info()
    clock.advance(119)
    service.info()
    assert len(gateway.calls) == 1
    clock.advance(2)
    service.info()
    assert len(gateway.calls) == 2


def test_pause_bounds() -> None:
    for answer, low, high in (
        (ConditionalJson(403, retry_after=1.0), MIN_THROTTLE_PAUSE, MIN_THROTTLE_PAUSE),
        (ConditionalJson(403, retry_after=10**9), MAX_THROTTLE_PAUSE, MAX_THROTTLE_PAUSE),
        (ConditionalJson(403), timedelta(hours=1), timedelta(hours=1)),
    ):
        service, gateway, _, _, clock = make(FakeReleaseGateway(answer))
        service.info()
        clock.advance(low.total_seconds() - 1)
        service.refresh(force=True)
        assert len(gateway.calls) == 1
        clock.advance(high.total_seconds() - low.total_seconds() + 2)
        service.refresh(force=True)
        assert len(gateway.calls) == 2


def test_an_exhausted_quota_on_a_good_answer_stops_further_lookups() -> None:
    reset = int((datetime(2026, 11, 19, 12, 0, tzinfo=UTC) + timedelta(minutes=45)).timestamp())
    gateway = FakeReleaseGateway(
        ConditionalJson(200, release_doc(), ETAG, remaining=0, reset_at=reset)
    )
    service, _, _, _, clock = make(gateway)
    assert service.info().latest is not None  # the answer itself is used
    clock.advance(30 * 60)
    service.refresh(force=True)
    assert len(gateway.calls) == 1


def test_forced_check_refreshes_a_fresh_cache() -> None:
    service, gateway, _, _, _ = make()
    service.info()
    service.refresh(force=True)
    assert len(gateway.calls) == 2


# ---------------------------------------------------------------- single flight


def test_concurrent_callers_share_one_lookup() -> None:
    service, gateway, _, _, _ = make()
    release = threading.Event()
    started = threading.Event()

    def slow() -> None:
        started.set()
        release.wait(2)

    gateway.on_call = slow
    results: list[bool] = []
    first = threading.Thread(target=lambda: results.append(service.info().update_available))
    first.start()
    assert started.wait(2)
    second = threading.Thread(target=lambda: results.append(service.info().update_available))
    second.start()
    release.set()
    first.join(5)
    second.join(5)
    assert len(gateway.calls) == 1 and results == [True, True]


# ---------------------------------------------------------------- approval


def approved(service: UpdateService) -> None:
    service.info()


def test_request_sends_the_notice_and_audits_without_secrets() -> None:
    service, _, notifier, audit, clock = make()
    approved(service)
    status = service.request_update("admin-1", "v1.1.0")
    assert (status.state, status.tag, status.requested_at) == ("requested", "v1.1.0", clock.now())
    assert [(r.repository, r.tag, r.requested_at) for r in notifier.sent] == [
        (REPO, "v1.1.0", clock.now())
    ]
    assert audit.events == [("system.update_requested", "admin-1", None, {"tag": "v1.1.0"})]
    snapshot = service.snapshot().update
    assert (snapshot.state, snapshot.tag) == ("requested", "v1.1.0")


def test_a_tag_that_is_not_the_cached_latest_is_refused() -> None:
    service, _, notifier, audit, _ = make()
    approved(service)
    for tag in ("v1.0.9", "v9.9.9", "v1.1.0-rc.1", "v1.1.1", "1.1.0", ""):
        with pytest.raises(UpdateNotAvailable):
            service.request_update("u", tag)
    assert notifier.sent == [] and audit.events == []


def test_nothing_to_update_to_is_refused() -> None:
    service, _, notifier, _, _ = make(current="1.1.0")
    approved(service)
    with pytest.raises(UpdateNotAvailable):
        service.request_update("u", "v1.1.0")
    fresh, _, _, _, _ = make()  # never looked up: no latest known
    with pytest.raises(UpdateNotAvailable):
        fresh.request_update("u", "v1.1.0")
    assert notifier.sent == []


def test_second_request_within_ten_minutes_is_a_conflict_then_allowed() -> None:
    service, _, notifier, _, clock = make()
    approved(service)
    service.request_update("a", "v1.1.0")
    clock.advance(9 * 60)
    with pytest.raises(UpdateAlreadyRequested):
        service.request_update("b", "v1.1.0")
    assert len(notifier.sent) == 1
    clock.advance(61)
    service.request_update("b", "v1.1.0")
    assert len(notifier.sent) == 2


def test_no_webhook_is_not_configured() -> None:
    gateway = FakeReleaseGateway()
    service = UpdateService(
        gateway, None, FakeAudit(), FakeClock(), config(webhook_configured=False)
    )
    service.info()
    assert service.snapshot().webhook_configured is False
    with pytest.raises(UpdateNotConfigured):
        service.request_update("u", "v1.1.0")


def test_a_failing_webhook_is_reported_audited_and_can_be_retried() -> None:
    service, _, notifier, audit, _ = make(notifier=FakeNotifier(fail=True))
    approved(service)
    with pytest.raises(UpdateNotifyFailed):
        service.request_update("admin-1", "v1.1.0")
    assert audit.events == [("system.update_failed", "admin-1", None, {"tag": "v1.1.0"})]
    state = service.snapshot().update
    assert (state.state, state.tag, state.requested_at) == ("failed", "v1.1.0", None)
    notifier.fail = False  # failed does not start the ten minute lock
    assert service.request_update("admin-1", "v1.1.0").state == "requested"


def test_an_unexpected_notifier_error_is_generic() -> None:
    class Boom:
        def notify(self, request: object) -> None:
            raise RuntimeError("secret https://hook.example/x?token=abc")

    service = UpdateService(FakeReleaseGateway(), Boom(), FakeAudit(), FakeClock(), config())
    service.info()
    with pytest.raises(UpdateNotifyFailed) as info:
        service.request_update("u", "v1.1.0")
    assert "secret" not in str(info.value) and info.value.__cause__ is None


def test_a_broken_audit_log_never_blocks_the_update() -> None:
    class BrokenAudit(FakeAudit):
        def record(self, *args: object, **kwargs: object) -> None:  # type: ignore[override]
            raise RuntimeError("db down")

    notifier = FakeNotifier()
    service = UpdateService(FakeReleaseGateway(), notifier, BrokenAudit(), FakeClock(), config())
    service.info()
    assert service.request_update("u", "v1.1.0").state == "requested"
    assert len(notifier.sent) == 1


def test_two_admins_at_once_send_a_single_request() -> None:
    service, _, notifier, _, _ = make()
    approved(service)
    gate = threading.Barrier(2)
    outcomes: list[str] = []

    class Slow(FakeNotifier):
        def notify(self, request) -> None:  # type: ignore[no-untyped-def]
            gate_wait = threading.Event()
            gate_wait.wait(0.2)
            super().notify(request)

    service._notifier = slow = Slow()  # type: ignore[assignment]  # noqa: SLF001

    def attempt() -> None:
        gate.wait(2)
        try:
            service.request_update("u", "v1.1.0")
            outcomes.append("ok")
        except UpdateAlreadyRequested:
            outcomes.append("conflict")

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert sorted(outcomes) == ["conflict", "ok"] and len(slow.sent) == 1 and notifier.sent == []
