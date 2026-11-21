from pathlib import Path

import pytest
from app.adapters.extractors.folder import FolderExtractor
from app.adapters.storage.local import LocalStorage
from app.domain.errors import ArchiveLimitExceeded, PageOutOfRange, UnsupportedFormat
from app.domain.library import ExtractorLimits

from fakes import png


def _ext(tmp_path: Path, files: dict[str, bytes], limits: ExtractorLimits | None = None):
    lib = tmp_path / "lib"
    (lib / "m").mkdir(parents=True)
    for name, data in files.items():
        (lib / "m" / name).write_bytes(data)
    storage = LocalStorage(lib)
    return FolderExtractor(storage, limits or ExtractorLimits()), storage


def test_pages_natural_order(tmp_path: Path) -> None:
    ext, _ = _ext(tmp_path, {"10.png": png(10), "2.png": png(2), "1.png": png(1), "x.txt": b"t"})
    assert ext.inspect("m").page_count == 3
    assert ext.read_page("m", 1).data == png(2)
    assert ext.read_cover("m").data == png(1)
    with pytest.raises(PageOutOfRange):
        ext.read_page("m", 3)


def test_can_handle_only_dirs_with_images(tmp_path: Path) -> None:
    ext, storage = _ext(tmp_path, {"1.png": png()})
    assert ext.can_handle(storage.stat("m"))
    ext2, storage2 = _ext(tmp_path / "other", {"readme.txt": b"t"})
    assert not ext2.can_handle(storage2.stat("m"))


def test_fake_extension_rejected(tmp_path: Path) -> None:
    ext, _ = _ext(tmp_path, {"1.jpg": b"plain text"})
    with pytest.raises(UnsupportedFormat):
        ext.inspect("m")


def test_giant_page_rejected(tmp_path: Path) -> None:
    ext, _ = _ext(tmp_path, {"1.png": png(1, 5000)}, ExtractorLimits(max_page_bytes=1000))
    with pytest.raises(ArchiveLimitExceeded):
        ext.inspect("m")


def test_too_many_files(tmp_path: Path) -> None:
    files = {f"{i}.png": png(i) for i in range(6)}
    ext, _ = _ext(tmp_path, files, ExtractorLimits(max_entries=5))
    with pytest.raises(ArchiveLimitExceeded):
        ext.inspect("m")
