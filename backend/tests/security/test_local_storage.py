import os
import subprocess  # noqa: S404 - test helper creating a junction with a fixed command
import sys
from pathlib import Path

import pytest
from app.adapters.storage.local import LocalStorage
from app.domain.errors import UnsafePath


@pytest.fixture
def root(tmp_path: Path) -> Path:
    lib = tmp_path / "library"
    (lib / "Series One").mkdir(parents=True)
    (lib / "Series One" / "001.png").write_bytes(b"x")
    (lib / "book.cbz").write_bytes(b"zip")
    return lib


@pytest.fixture
def storage(root: Path) -> LocalStorage:
    return LocalStorage(root)


@pytest.mark.parametrize(
    "bad",
    [
        "..",
        "../secret.txt",
        "Series One/../../secret.txt",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "C:\\Windows\\win.ini",
        "..\\secret",
        "a\x00b.cbz",
        "",
        ".",
        "Series One/./001.png",
        "CON",
        "nul.txt",
        "Series One/COM1.png",
        "lpt9",
        "trailing.",
        "space ",
        "file.cbz:stream",
        "a" * 2000,
        "/".join(["d"] * 40),
    ],
)
def test_rejects_hostile_paths(storage: LocalStorage, bad: str) -> None:
    with pytest.raises(UnsafePath):
        storage.open(bad)
    with pytest.raises(UnsafePath):
        storage.stat(bad)


def test_non_string_path_rejected(storage: LocalStorage) -> None:
    with pytest.raises(UnsafePath):
        storage.stat(None)  # type: ignore[arg-type]


def test_normal_paths_work(storage: LocalStorage) -> None:
    assert storage.open("book.cbz").read() == b"zip"
    entry = storage.stat("Series One")
    assert entry.is_dir
    assert entry.size == 1
    assert [c.rel_path for c in storage.list_children("Series One")] == ["Series One/001.png"]


def test_missing_file_is_not_found(storage: LocalStorage) -> None:
    with pytest.raises(FileNotFoundError):
        storage.open("nope.cbz")


def test_open_directory_is_rejected(storage: LocalStorage) -> None:
    with pytest.raises(UnsafePath):
        storage.open("Series One")


def test_list_entries_returns_relative_posix_paths(storage: LocalStorage) -> None:
    rels = {e.rel_path for e in storage.list_entries()}
    assert rels == {"Series One", "Series One/001.png", "book.cbz"}


def test_normal_folder_is_not_mistaken_for_a_link(storage: LocalStorage, root: Path) -> None:
    """Regression guard for OneDrive: ordinary folders may carry the ReparsePoint attribute.

    Detection must rely on real symlink/junction checks, never on the raw attribute.
    """
    sub = root / "OneDrive Folder"
    sub.mkdir()
    (sub / "p.png").write_bytes(b"x")
    assert storage.stat("OneDrive Folder").is_dir
    assert storage.open("OneDrive Folder/p.png").read() == b"x"
    assert "OneDrive Folder/p.png" in {e.rel_path for e in storage.list_entries()}


def _make_dir_link(link: Path, target: Path) -> bool:
    """Create a symlink, or a junction on Windows. Returns False if the OS refuses."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if sys.platform == "win32":
        result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],  # noqa: S607
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    return False


def test_directory_link_to_outside_is_rejected(
    storage: LocalStorage, root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"secret")
    if not _make_dir_link(root / "escape", outside):
        pytest.skip("OS does not allow creating symlinks/junctions here")
    with pytest.raises(UnsafePath):
        storage.open("escape/secret.txt")
    with pytest.raises(UnsafePath):
        storage.stat("escape")
    assert not any(e.rel_path.startswith("escape") for e in storage.list_entries())


def test_file_symlink_is_rejected(storage: LocalStorage, root: Path, tmp_path: Path) -> None:
    target = tmp_path / "secret.txt"
    target.write_bytes(b"secret")
    try:
        os.symlink(target, root / "link.cbz")
    except (OSError, NotImplementedError):
        pytest.skip("OS does not allow creating symlinks here")
    with pytest.raises(UnsafePath):
        storage.open("link.cbz")
    assert "link.cbz" not in {e.rel_path for e in storage.list_entries()}


def test_root_must_exist(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LocalStorage(tmp_path / "missing")
