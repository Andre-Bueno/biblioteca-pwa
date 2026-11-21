"""Progress and preferences use cases over in-memory fakes (no FastAPI, no database)."""

import pytest
from app.domain.errors import ItemNotFound
from app.domain.item import Item, ItemType
from app.domain.preferences import InvalidPreferences, Preferences
from app.domain.progress import ContinueEntry, InvalidLocator, Progress, compute_position
from app.domain.user import UserNotFoundError
from app.services.preferences_service import PreferencesService
from app.services.progress_service import MAX_CONTINUE_LIMIT, ProgressService

from auth_fakes import START, FakeClock


def _item(item_id: str = "i1", pages: int = 10) -> Item:
    return Item(
        id=item_id,
        type=ItemType.MANGA,
        title="t",
        rel_path="a.cbz",
        format="cbz",
        page_count=pages,
        size=1,
        mtime_ns=1,
        added_at=START,
    )


class FakeItems:
    def __init__(self, *items: Item) -> None:
        self.items = {i.id: i for i in items}

    def get(self, item_id: str) -> Item | None:
        return self.items.get(item_id)


class FakeProgress:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], Progress] = {}
        self.last_limit = 0

    def upsert(self, progress: Progress) -> None:
        self.rows[(progress.user_id, progress.item_id)] = progress

    def get(self, user_id: str, item_id: str) -> Progress | None:
        return self.rows.get((user_id, item_id))

    def delete(self, user_id: str, item_id: str) -> None:
        self.rows.pop((user_id, item_id), None)

    def list_continue(self, user_id: str, limit: int) -> list[ContinueEntry]:
        self.last_limit = limit
        return []


def _service(*items: Item) -> tuple[ProgressService, FakeProgress, FakeClock]:
    repo, clock = FakeProgress(), FakeClock()
    return ProgressService(FakeItems(*items), repo, clock), repo, clock  # type: ignore[arg-type]


def test_compute_position() -> None:
    assert compute_position(0, 4) == (25.0, False)
    assert compute_position(1, 4) == (50.0, False)
    assert compute_position(3, 4) == (100.0, True)
    assert compute_position(0, 1) == (100.0, True)


@pytest.mark.parametrize(("locator", "pages"), [(-1, 4), (4, 4), (5, 4), (0, 0)])
def test_compute_position_rejects_locator_outside_the_item(locator: int, pages: int) -> None:
    with pytest.raises(InvalidLocator):
        compute_position(locator, pages)


def test_save_derives_percent_and_finished_and_uses_the_server_clock() -> None:
    service, repo, clock = _service(_item(pages=10))
    saved = service.save("u1", "i1", 4, "phone")
    assert (saved.percent, saved.finished, saved.updated_at) == (50.0, False, clock.now())
    assert repo.rows[("u1", "i1")] == saved
    clock.advance(5)
    last = service.save("u1", "i1", 9)
    assert last.finished and last.percent == 100.0
    assert len(repo.rows) == 1 and last.device_id is None


def test_save_unknown_item_and_bad_locator_write_nothing() -> None:
    service, repo, _ = _service(_item(pages=3))
    with pytest.raises(ItemNotFound):
        service.save("u1", "nope", 0)
    with pytest.raises(InvalidLocator):
        service.save("u1", "i1", 3)
    assert repo.rows == {}


def test_get_missing_progress_is_not_found_and_clear_is_idempotent() -> None:
    service, repo, _ = _service(_item())
    with pytest.raises(ItemNotFound):
        service.get("u1", "i1")
    service.save("u1", "i1", 1)
    service.clear("u1", "i1")
    service.clear("u1", "i1")
    assert repo.rows == {}


def test_progress_is_scoped_by_user() -> None:
    service, _, _ = _service(_item())
    service.save("u1", "i1", 1)
    with pytest.raises(ItemNotFound):
        service.get("u2", "i1")


@pytest.mark.parametrize(("asked", "effective"), [(10, 10), (500, MAX_CONTINUE_LIMIT), (0, 1)])
def test_continue_limit_is_capped(asked: int, effective: int) -> None:
    service, repo, _ = _service()
    service.continue_reading("u1", asked)
    assert repo.last_limit == effective


class FakePrefs:
    def __init__(self) -> None:
        self.rows: dict[str, Preferences] = {"u1": Preferences("system", "rtl")}

    def get(self, user_id: str) -> Preferences | None:
        return self.rows.get(user_id)

    def set(self, user_id: str, preferences: Preferences) -> bool:
        if user_id not in self.rows:
            return False
        self.rows[user_id] = preferences
        return True


def test_preferences_round_trip_and_unknown_user() -> None:
    service = PreferencesService(FakePrefs())
    assert service.get("u1") == Preferences("system", "rtl")
    assert service.update("u1", Preferences("dark", "vertical")) == Preferences("dark", "vertical")
    assert service.get("u1") == Preferences("dark", "vertical")
    with pytest.raises(UserNotFoundError):
        service.get("ghost")
    with pytest.raises(UserNotFoundError):
        service.update("ghost", Preferences("dark", "ltr"))


@pytest.mark.parametrize(("theme", "direction"), [("blue", "rtl"), ("dark", "up"), ("", "")])
def test_preferences_domain_rejects_unknown_values(theme: str, direction: str) -> None:
    with pytest.raises(InvalidPreferences):
        Preferences(theme, direction)
