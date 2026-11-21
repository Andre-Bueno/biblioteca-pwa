"""Builders for API tests that need a real (temporary) library and scanned items."""

import uuid
from pathlib import Path

from app.domain.item import Item, ItemType
from app.domain.user import Role
from app.ports.http_gateway import HttpGateway

from auth_fakes import PASSWORD, START, ApiClient, Env
from fakes import make_cbz, make_library, png

ADMIN = "root"


def library_env(
    db_url: str, tmp_path: Path, *, scan: bool = True, **overrides: object
) -> tuple[Env, Path]:
    """App on a temp DB + temp library, with users alice (user) and root (admin)."""
    lib = make_library(tmp_path)
    env = Env(db_url, LIBRARY_PATH=lib, **overrides)
    env.create_user("alice", PASSWORD)
    env.create_user(ADMIN, PASSWORD, role=Role.ADMIN)
    if scan:
        env.container.scan_runner.run()
    return env, lib


def logged_in(env: Env, username: str = "alice") -> ApiClient:
    client = env.client()
    assert client.login(username, PASSWORD).status_code == 200
    return client


def add_item(
    env: Env,
    title: str,
    *,
    item_type: ItemType = ItemType.MANGA,
    fmt: str = "cbz",
    pages: int = 2,
    rel_path: str | None = None,
) -> Item:
    item = Item(
        id=str(uuid.uuid4()),
        type=item_type,
        title=title,
        rel_path=rel_path or f"{uuid.uuid4()}.cbz",
        format=fmt,
        page_count=pages,
        size=1,
        mtime_ns=1,
        added_at=START,
    )
    env.container.item_repository.add(item)
    return item


def item_id_by_title(client: ApiClient, title: str) -> str:
    items = client.get("/api/v1/items?limit=100").json()["items"]
    return next(i["id"] for i in items if i["title"] == title)


ORV = "Omniscient Reader's Viewpoint"


def make_series_library(root: Path) -> Path:
    """A library shaped like a real one: a folder of numbered CBZ chapters (one corrupt, one with
    no number), loose volumes in the root, an image folder in the root and a series with a chapter
    that is itself an image folder."""
    lib = root / "series_lib"
    (lib / ORV).mkdir(parents=True)
    for number in (0, 1, 2, 10, 11, 100):
        pages = {"1.png": png(number), "2.png": png(number + 1), "3.png": png(number + 2)}
        (lib / ORV / f"Capitulo - {number}.cbz").write_bytes(make_cbz(pages))
    (lib / ORV / "Capitulo - 5.cbz").write_bytes(b"corrupt at the source")
    (lib / ORV / "Extras.cbz").write_bytes(make_cbz({"1.png": png(9), "2.png": png(10)}))
    (lib / "Berserk v03.cbz").write_bytes(make_cbz({"1.png": png(1), "2.png": png(2)}))
    (lib / "Solo.cbz").write_bytes(make_cbz({"1.png": png(3), "2.png": png(4)}))
    (lib / "Folder Manga").mkdir()
    (lib / "Folder Manga" / "1.png").write_bytes(png(1))
    (lib / "Folder Manga" / "2.png").write_bytes(png(2))
    (lib / "Mixed Series" / "Chapter 7.5").mkdir(parents=True)
    (lib / "Mixed Series" / "Chapter 7.5" / "1.png").write_bytes(png(7))
    (lib / "Mixed Series" / "Chapter 7.5" / "2.png").write_bytes(png(8))
    (lib / "Mixed Series" / "Chapter 8.cbz").write_bytes(
        make_cbz({"1.png": png(5), "2.png": png(6)})
    )
    return lib


def series_env(db_url: str, tmp_path: Path, *, scan: bool = True) -> tuple[Env, Path]:
    """Like `library_env` but over `make_series_library`."""
    lib = make_series_library(tmp_path)
    env = Env(db_url, LIBRARY_PATH=lib)
    env.create_user("alice", PASSWORD)
    env.create_user("bob", PASSWORD)
    env.create_user(ADMIN, PASSWORD, role=Role.ADMIN)
    if scan:
        env.container.scan_runner.run()
    return env, lib


def series_id_by_title(client: ApiClient, title: str) -> str:
    series = client.get("/api/v1/series?limit=100").json()["items"]
    return next(s["id"] for s in series if s["title"] == title)


def metadata_env(
    db_url: str,
    tmp_path: Path,
    gateway: HttpGateway | None,
    *,
    scan: bool = True,
    **overrides: object,
) -> tuple[Env, Path]:
    """Like `series_env`, with a fake HTTP gateway (never the network) and a temp DATA_DIR. Users:
    alice and bob (users), root and root2 (admins)."""
    lib = make_series_library(tmp_path)
    env = Env(db_url, gateway=gateway, LIBRARY_PATH=lib, DATA_DIR=tmp_path / "data", **overrides)
    env.create_user("alice", PASSWORD)
    env.create_user("bob", PASSWORD)
    env.create_user(ADMIN, PASSWORD, role=Role.ADMIN)
    env.create_user("root2", PASSWORD, role=Role.ADMIN)
    if scan:
        env.container.scan_runner.run()
    return env, lib
