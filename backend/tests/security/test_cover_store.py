"""LocalCoverStore: the file name comes only from the series UUID and a fixed extension; nothing
from the network, the database or a client is ever part of a path; writes are staged, then renamed.
"""

import os
import threading
from pathlib import Path

import pytest
from app.adapters.storage.cover_store import COVERS_DIRNAME, LocalCoverStore
from app.domain.errors import ExternalFetchError, UnsafePath
from app.domain.metadata import FetchedImage, StagedCover

from metadata_fakes import good_jpeg, good_png, good_webp

SID = "0f8fad5b-d9cb-469f-a165-70867728950e"


def image(data: bytes, ext: str, media: str) -> FetchedImage:
    return FetchedImage(data=data, media_type=media, ext=ext)


JPEG = image(good_jpeg(), "jpg", "image/jpeg")


def names(root: Path) -> list[str]:
    folder = root / COVERS_DIRNAME
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_stage_commit_read_roundtrip(tmp_path: Path) -> None:
    store = LocalCoverStore(tmp_path)
    for data, ext, media in (
        (good_jpeg(), "jpg", "image/jpeg"),
        (good_png(), "png", "image/png"),
        (good_webp(), "webp", "image/webp"),
    ):
        staged = store.stage(SID, image(data, ext, media))
        assert staged.rel_path == f"{SID}.{ext}"
        store.commit(staged)
        page = store.read(staged.rel_path)
        assert page is not None and page.data == data and page.media_type == media
        store.delete(staged.rel_path)
    assert names(tmp_path) == []


def test_nothing_is_visible_until_commit_and_discard_cleans_up(tmp_path: Path) -> None:
    store = LocalCoverStore(tmp_path)
    staged = store.stage(SID, JPEG)
    assert store.read(staged.rel_path) is None
    [temp] = names(tmp_path)
    assert temp.startswith(".") and temp.endswith(".tmp")
    store.discard(staged)
    store.discard(staged)  # idempotent
    assert names(tmp_path) == []


def test_commit_is_an_atomic_rename_and_a_failure_leaves_no_partial_cover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalCoverStore(tmp_path)
    store.commit(store.stage(SID, JPEG))  # an older cover exists
    newer = store.stage(SID, image(good_jpeg(99), "jpg", "image/jpeg"))

    def broken(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError, match="disk full"):
        store.commit(newer)
    monkeypatch.undo()
    page = store.read(f"{SID}.jpg")
    assert page is not None and page.data == good_jpeg()  # the old cover is intact
    store.discard(newer)
    assert names(tmp_path) == [f"{SID}.jpg"]


def test_a_failed_write_removes_its_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalCoverStore(tmp_path)

    def broken(_fd: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(os, "fsync", broken)
    with pytest.raises(OSError, match="fsync failed"):
        store.stage(SID, JPEG)
    monkeypatch.undo()
    assert names(tmp_path) == []


@pytest.mark.parametrize(
    "series_id",
    [
        "",
        "../evil",
        "..\\evil",
        SID.upper(),
        SID + ".png",
        SID + "/../x",
        "a" * 36,
        "/etc/passwd",
        "C:\\Windows\\x",
        SID[:-1],
        SID + "\x00",
    ],
)
def test_only_a_server_uuid_can_name_a_cover(tmp_path: Path, series_id: str) -> None:
    store = LocalCoverStore(tmp_path)
    with pytest.raises(UnsafePath):
        store.stage(series_id, JPEG)
    assert names(tmp_path) == []


@pytest.mark.parametrize("ext", ["php", "jpg/../x", "JPG", "gif", "", "jpg.php", "png\x00"])
def test_only_the_three_fixed_extensions_exist(tmp_path: Path, ext: str) -> None:
    with pytest.raises(UnsafePath):
        LocalCoverStore(tmp_path).stage(SID, image(good_jpeg(), ext, "image/jpeg"))
    assert names(tmp_path) == []


def test_size_is_capped_before_anything_is_written(tmp_path: Path) -> None:
    store = LocalCoverStore(tmp_path, max_bytes=100)
    with pytest.raises(ExternalFetchError) as info:
        store.stage(SID, image(good_jpeg() + b"x" * 100, "jpg", "image/jpeg"))
    assert info.value.reason == "too_large" and names(tmp_path) == []


def test_a_tampered_staged_value_cannot_escape_the_folder(tmp_path: Path) -> None:
    store = LocalCoverStore(tmp_path)
    store.stage(SID, JPEG)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"keep me")
    for staged in (
        StagedCover(SID, "../outside.jpg", "0123456789abcdef"),
        StagedCover(SID, f"{SID}.jpg", "../../outside"),
        StagedCover(SID, f"{SID}.jpg", "..\\..\\outside"),
        StagedCover(SID, f"{SID}.php", "0123456789abcdef"),
        StagedCover(SID, "x.jpg", "0123456789abcdef"),
    ):
        with pytest.raises(UnsafePath):
            store.commit(staged)
        with pytest.raises(UnsafePath):
            store.discard(StagedCover(SID, staged.rel_path, "../x"))
    assert outside.read_bytes() == b"keep me"


@pytest.mark.parametrize(
    "rel",
    [
        "",
        "../secret.jpg",
        "..\\secret.jpg",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        f"{SID}.svg",
        f"{SID}.JPG",
        f"{SID}.jpg/",
        f"{SID}.jpg\x00.png",
        f"x/{SID}.jpg",
        f"{SID}.jpg.php",
        "plain.png",
    ],
)
def test_read_and_delete_ignore_any_name_that_is_not_uuid_dot_ext(tmp_path: Path, rel: str) -> None:
    store = LocalCoverStore(tmp_path)
    (tmp_path / "covers").mkdir()
    (tmp_path / "secret.jpg").write_bytes(good_jpeg())
    (tmp_path / "covers" / "plain.png").write_bytes(good_png())
    assert store.read(rel) is None
    store.delete(rel)
    assert (tmp_path / "secret.jpg").exists() and (tmp_path / "covers" / "plain.png").exists()


def test_read_refuses_a_file_that_is_not_an_image_or_is_too_big(tmp_path: Path) -> None:
    store = LocalCoverStore(tmp_path, max_bytes=500)
    folder = tmp_path / "covers"
    folder.mkdir()
    (folder / f"{SID}.jpg").write_bytes(b"<html><script>alert(1)</script></html>")
    assert store.read(f"{SID}.jpg") is None
    (folder / f"{SID}.png").write_bytes(good_png() + b"x" * 1000)
    assert store.read(f"{SID}.png") is None
    (folder / f"{SID}.webp").mkdir()  # a directory with that name
    assert store.read(f"{SID}.webp") is None


def test_the_type_served_comes_from_the_bytes_not_from_the_extension(tmp_path: Path) -> None:
    folder = tmp_path / "covers"
    folder.mkdir()
    (folder / f"{SID}.jpg").write_bytes(good_png())  # a PNG stored under a .jpg name
    page = LocalCoverStore(tmp_path).read(f"{SID}.jpg")
    assert page is not None and page.media_type == "image/png"


def test_a_symlink_is_never_followed(tmp_path: Path) -> None:
    folder = tmp_path / "covers"
    folder.mkdir()
    target = tmp_path / "secret.jpg"
    target.write_bytes(good_jpeg())
    try:
        (folder / f"{SID}.jpg").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    assert LocalCoverStore(tmp_path).read(f"{SID}.jpg") is None


def test_concurrent_commits_never_leave_a_corrupt_cover(tmp_path: Path) -> None:
    store = LocalCoverStore(tmp_path)
    datas = [good_jpeg(i) for i in range(8)]
    staged = [store.stage(SID, image(d, "jpg", "image/jpeg")) for d in datas]

    def commit(s: StagedCover) -> None:
        try:
            store.commit(s)
        except OSError:  # Windows may refuse a rename over a file being replaced at that instant
            store.discard(s)

    threads = [threading.Thread(target=commit, args=(s,)) for s in staged]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    page = store.read(f"{SID}.jpg")
    assert page is not None and page.data in datas  # one whole winner, never a mix
    assert names(tmp_path) == [f"{SID}.jpg"]
