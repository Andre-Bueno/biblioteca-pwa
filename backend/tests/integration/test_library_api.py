"""End to end: temp library -> scan -> login -> list -> open a page; scan API and CLI."""

import sqlite3
import threading
from pathlib import Path

import pytest
from app import cli
from app.core.config import get_settings
from app.domain.errors import LibraryUnavailable
from app.domain.library import ScanReport
from app.domain.user import Role
from app.services.scan import ProgressCallback
from app.services.scan_runner import ScanRunner

from auth_fakes import Env
from fakes import png
from library_env import add_item, library_env, logged_in


def test_end_to_end_login_scan_list_open_page(db_url: str, tmp_path: Path) -> None:
    env, lib = library_env(db_url, tmp_path, scan=False)
    client = env.client()
    assert client.get("/api/v1/items").status_code == 401  # nothing before login
    assert client.login("root").status_code == 200

    assert client.get("/api/v1/items").json()["items"] == []  # empty until a scan runs
    started = client.post("/api/v1/library/scan")
    assert started.status_code == 202
    assert env.container.scan_runner.wait(10)

    status = client.get("/api/v1/library/scan/status").json()
    assert status["state"] == "finished"
    assert (status["added"], status["skipped"], status["error_count"]) == (2, 3, 1)
    assert status["errors_by_reason"] == {"CorruptArchive": 1}
    assert "broken" not in str(status) and str(lib) not in str(status)  # no paths, no file names
    assert status["processed"] == status["total"] == 6

    listing = client.get("/api/v1/items?q=vol").json()
    assert [i["title"] for i in listing["items"]] == ["Vol 1"]
    item = listing["items"][0]
    assert (item["format"], item["type"], item["page_count"]) == ("cbz", "manga", 3)

    detail = client.get(f"/api/v1/items/{item['id']}")
    assert detail.status_code == 200
    assert detail.json() == item
    page = client.get(f"/api/v1/items/{item['id']}/pages/2")
    assert (page.status_code, page.content) == (200, png(3))

    folder = next(i for i in client.get("/api/v1/items").json()["items"] if i["format"] == "folder")
    assert client.get(f"/api/v1/items/{folder['id']}/pages/0").content == png(1)  # natural order


def test_a_rescan_picks_up_new_and_removed_files(db_url: str, tmp_path: Path) -> None:
    env, lib = library_env(db_url, tmp_path)
    client = logged_in(env, "root")
    (lib / "Vol 1.cbz").unlink()
    from fakes import make_cbz

    (lib / "New Vol.cbz").write_bytes(make_cbz({"1.png": png(9)}))
    assert client.post("/api/v1/library/scan").status_code == 202
    assert env.container.scan_runner.wait(10)
    titles = {i["title"] for i in client.get("/api/v1/items").json()["items"]}
    assert titles == {"Folder Manga", "New Vol"}
    status = client.get("/api/v1/library/scan/status").json()
    assert (status["added"], status["removed"]) == (1, 1)


def test_second_scan_while_running_is_409_and_does_not_block_the_api(
    db_url: str, tmp_path: Path
) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)
    started, release = threading.Event(), threading.Event()

    def slow(progress: ProgressCallback) -> ScanReport:
        started.set()
        assert release.wait(10)
        return ScanReport(added=1)

    env.container.scan_runner = ScanRunner(slow, env.container.clock)
    admin = logged_in(env, "root")

    first = admin.post("/api/v1/library/scan")
    assert first.status_code == 202
    assert started.wait(5)
    # The scan is running in the background and the API still answers.
    assert admin.get("/api/v1/auth/me").status_code == 200
    assert admin.get("/api/v1/library/scan/status").json()["state"] == "running"

    second = admin.post("/api/v1/library/scan")
    assert second.status_code == 409
    assert second.json() == {"detail": "A scan is already running"}
    assert second.headers["cache-control"] == "no-store"

    release.set()
    assert env.container.scan_runner.wait(10)
    assert admin.get("/api/v1/library/scan/status").json()["state"] == "finished"
    assert admin.post("/api/v1/library/scan").status_code == 202  # lock released
    env.container.scan_runner.wait(10)


def test_failed_scan_is_reported_without_details(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(db_url, tmp_path, scan=False)

    def boom(progress: ProgressCallback) -> ScanReport:
        raise RuntimeError("secret detail /etc/shadow")

    env.container.scan_runner = ScanRunner(boom, env.container.clock)
    admin = logged_in(env, "root")
    admin.post("/api/v1/library/scan")
    env.container.scan_runner.wait(10)
    response = admin.get("/api/v1/library/scan/status")
    assert response.json()["state"] == "failed"
    assert "secret" not in response.text and "shadow" not in response.text


def test_missing_library_folder_gives_generic_503_not_a_start_up_failure(
    db_url: str, tmp_path: Path
) -> None:
    gone = tmp_path / "no-such-library"
    env = Env(db_url, LIBRARY_PATH=gone)  # the app builds fine: the folder is only needed on use
    env.create_user("alice")
    env.create_user("root", role=Role.ADMIN)
    item = add_item(env, "Orphan")

    user = logged_in(env, "alice")
    assert user.get("/api/v1/items").status_code == 200  # the catalog is in the database
    page = user.get(f"/api/v1/items/{item.id}/pages/0")
    assert page.status_code == 503
    assert page.json() == {"detail": "Library unavailable"}
    assert "no-such-library" not in page.text

    admin = logged_in(env, "root")
    scan = admin.post("/api/v1/library/scan")
    assert scan.status_code == 503
    assert "no-such-library" not in scan.text


def test_container_reports_a_clear_error_without_the_path(db_url: str, tmp_path: Path) -> None:
    secret_dir = tmp_path / "private-mount-name"
    env = Env(db_url, LIBRARY_PATH=secret_dir)
    with pytest.raises(LibraryUnavailable) as info:
        _ = env.container.scan_runner
    assert "private-mount-name" not in str(info.value)
    # A file where a folder is expected is also "unavailable".
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x")
    env2 = Env(f"{db_url}2", LIBRARY_PATH=not_a_dir)
    with pytest.raises(LibraryUnavailable):
        _ = env2.container.storage


def test_extractor_limits_come_from_settings(db_url: str, tmp_path: Path) -> None:
    env, _ = library_env(
        db_url,
        tmp_path,
        scan=False,
        EXTRACTOR_MAX_ENTRIES=2,
        EXTRACTOR_MAX_PAGE_BYTES=1234,
        EXTRACTOR_MAX_TOTAL_UNCOMPRESSED_BYTES=5678,
        EXTRACTOR_MAX_COMPRESSION_RATIO=7,
    )
    limits = env.container.extractors[0]._limits  # type: ignore[attr-defined]  # noqa: SLF001
    assert (
        limits.max_entries,
        limits.max_page_bytes,
        limits.max_total_uncompressed_bytes,
        limits.max_compression_ratio,
    ) == (2, 1234, 5678, 7)


# ---------------------------------------------------------------- CLI


@pytest.fixture
def cli_library(db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from fakes import make_library

    lib = make_library(tmp_path)
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("LIBRARY_PATH", str(lib))
    get_settings.cache_clear()
    yield lib, db_url
    get_settings.cache_clear()


def test_cli_scan_populates_the_catalog_and_prints_counts_only(
    cli_library,
    capsys: pytest.CaptureFixture[str],  # type: ignore[no-untyped-def]
) -> None:
    lib, url = cli_library
    assert cli.main(["migrate"]) == 0
    capsys.readouterr()
    assert cli.main(["scan"]) == 0
    out = capsys.readouterr().out
    assert "added=2" in out and "errors=1" in out and "CorruptArchive: 1" in out
    assert "broken" not in out and str(lib) not in out
    with sqlite3.connect(url.removeprefix("sqlite:///")) as conn:
        rows = conn.execute("SELECT title, missing FROM items ORDER BY title").fetchall()
    assert rows == [("Folder Manga", 0), ("Vol 1", 0)]

    capsys.readouterr()
    assert cli.main(["scan"]) == 0  # idempotent
    again = capsys.readouterr().out
    assert "added=0" in again
    assert "unchanged=2" in again


def test_cli_scan_with_a_missing_library_is_a_clear_error(
    db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "vanished-folder"))
    get_settings.cache_clear()
    try:
        assert cli.main(["scan"]) == 1
    finally:
        get_settings.cache_clear()
    err = capsys.readouterr().err
    assert "LIBRARY_PATH" in err
    assert "vanished-folder" not in err


def test_cli_scan_command_exists_in_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "scan" in capsys.readouterr().out
