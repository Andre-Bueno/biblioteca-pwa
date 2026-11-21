"""REG-016 (FIND-2026-011): a folder counted files with an image extension but fake content.

Bug: `FolderExtractor.inspect` validated only the cover, so `page_count` included a `3.jpg` that
holds text; asking for that page answered 422. The CBZ extractor already ignored such entries.
Fix: the page list is built from files whose magic bytes are an image (same as CBZ), so page_count
and the readable pages agree.
"""

from pathlib import Path

import pytest
from app.adapters.extractors.folder import FolderExtractor
from app.adapters.storage.local import LocalStorage
from app.domain.errors import PageOutOfRange
from app.domain.library import ExtractorLimits

from fakes import png


def _folder(tmp_path: Path, files: dict[str, bytes]) -> FolderExtractor:
    lib = tmp_path / "lib"
    (lib / "m").mkdir(parents=True)
    for name, data in files.items():
        (lib / "m" / name).write_bytes(data)
    return FolderExtractor(LocalStorage(lib), ExtractorLimits())


def test_page_count_ignores_files_with_image_extension_but_fake_content(tmp_path: Path) -> None:
    ext = _folder(tmp_path, {"1.png": png(1), "2.png": png(2), "3.jpg": b"just some text"})
    assert ext.inspect("m").page_count == 2
    assert ext.read_page("m", 1).data == png(2)
    with pytest.raises(PageOutOfRange):
        ext.read_page("m", 2)


def test_fake_file_in_the_middle_does_not_shift_the_pages(tmp_path: Path) -> None:
    ext = _folder(tmp_path, {"1.png": png(1), "2.jpg": b"text", "3.png": png(3)})
    assert ext.inspect("m").page_count == 2
    assert ext.read_page("m", 1).data == png(3)


def test_page_read_does_not_sniff_every_file_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ext = _folder(tmp_path, {f"{i}.png": png(i) for i in range(30)})
    ext.inspect("m")
    opened: list[str] = []
    storage = ext._storage
    original = storage.open

    def counting(rel_path: str):  # type: ignore[no-untyped-def]
        opened.append(rel_path)
        return original(rel_path)

    monkeypatch.setattr(storage, "open", counting)
    ext.read_page("m", 7)
    assert len(opened) <= 1
