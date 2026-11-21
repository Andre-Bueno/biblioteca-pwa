"""Fakes for the update feature: a gateway that answers release lookups from memory (no socket), a
notifier and an audit log that record what they are given."""

from collections.abc import Callable
from datetime import timedelta

from app.domain.errors import ExternalFetchError, UpdateNotifyFailed
from app.domain.release import ConditionalJson, UpdateRequest
from app.services.update_service import UpdateConfig

from auth_fakes import FakeAudit, FakeClock

REPO = "Andre-Bueno/biblioteca-pwa"
ETAG = '"abc123"'


def release_doc(tag: str = "v1.1.0", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "tag_name": tag,
        "name": f"Release {tag}",
        "body": "- fixed things",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-11-21T12:00:00Z",
        "html_url": f"https://github.com/{REPO}/releases/tag/{tag}",
    }
    return base | over


class FakeReleaseGateway:
    """Queue of answers for `get_json_conditional`; an Exception in the queue is raised."""

    def __init__(self, *answers: ConditionalJson | Exception) -> None:
        self.queue: list[ConditionalJson | Exception] = list(answers)
        self.calls: list[tuple[str, str | None]] = []
        self.default: ConditionalJson | Exception = ConditionalJson(200, release_doc(), ETAG)
        self.on_call: Callable[[], None] | None = None

    def get_json_conditional(self, url: str, etag: str | None) -> ConditionalJson:
        self.calls.append((url, etag))
        if self.on_call is not None:
            self.on_call()
        item = self.queue.pop(0) if self.queue else self.default
        if isinstance(item, Exception):
            raise item
        return item

    # The rest of `HttpGateway` is never used by the update feature.
    def get_json(self, url: str) -> object:
        raise ExternalFetchError("unexpected")

    def post_json(self, url: str, payload: dict[str, object]) -> object:
        raise ExternalFetchError("unexpected")

    def get_image(self, url: str) -> object:
        raise ExternalFetchError("unexpected")


class FakeNotifier:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[UpdateRequest] = []
        self.fail = fail

    def notify(self, request: UpdateRequest) -> None:
        if self.fail:
            raise UpdateNotifyFailed
        self.sent.append(request)


def config(**over: object) -> UpdateConfig:
    values: dict[str, object] = {
        "current": "1.0.0",
        "repository": REPO,
        "check_enabled": True,
        "interval": timedelta(hours=6),
        "webhook_configured": True,
    }
    values.update(over)
    return UpdateConfig(**values)  # type: ignore[arg-type]


__all__ = [
    "ETAG",
    "REPO",
    "FakeAudit",
    "FakeClock",
    "FakeNotifier",
    "FakeReleaseGateway",
    "config",
    "release_doc",
]
