import contextlib
import io
import stat
import struct
import zipfile
from pathlib import Path

import pytest
from app.adapters.extractors.cbz import CbzExtractor
from app.adapters.storage.local import LocalStorage
from app.domain.errors import (
    ArchiveLimitExceeded,
    CorruptArchive,
    PageOutOfRange,
    UnsafePath,
    UnsupportedFormat,
)
from app.domain.library import ExtractorLimits

from fakes import make_cbz, png


def _extractor(tmp_path: Path, data: bytes, limits: ExtractorLimits | None = None) -> CbzExtractor:
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    (lib / "t.cbz").write_bytes(data)
    return CbzExtractor(LocalStorage(lib), limits or ExtractorLimits())


def test_reads_pages_in_natural_order_with_media_types(tmp_path: Path) -> None:
    data = make_cbz(
        {"p10.png": png(10), "p2.png": png(2), "p1.png": png(1), "ComicInfo.xml": b"<x/>"}
    )
    ext = _extractor(tmp_path, data)
    assert ext.inspect("t.cbz").page_count == 3
    assert ext.read_page("t.cbz", 0).data == png(1)
    assert ext.read_page("t.cbz", 1).data == png(2)
    assert ext.read_page("t.cbz", 2).media_type == "image/png"
    assert ext.read_cover("t.cbz").data == png(1)


def test_page_out_of_range(tmp_path: Path) -> None:
    ext = _extractor(tmp_path, make_cbz({"a.png": png()}))
    for idx in (-1, 1):
        with pytest.raises(PageOutOfRange):
            ext.read_page("t.cbz", idx)


@pytest.mark.parametrize(
    "name", ["../evil.png", "a/../../evil.png", "/abs.png", "C:/evil.png", "..\\evil.png"]
)
def test_zip_slip_names_rejected(tmp_path: Path, name: str) -> None:
    ext = _extractor(tmp_path, make_cbz({"ok.png": png(), name: png()}))
    with pytest.raises(UnsafePath):
        ext.inspect("t.cbz")
    assert not (tmp_path / "evil.png").exists()


def test_symlink_entry_rejected(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("link.png")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    ext = _extractor(tmp_path, buf.getvalue())
    with pytest.raises(UnsafePath):
        ext.inspect("t.cbz")


def test_zip_bomb_by_ratio(tmp_path: Path) -> None:
    ext = _extractor(tmp_path, make_cbz({"a.png": png(), "bomb.bin": b"\0" * (4 * 1024 * 1024)}))
    with pytest.raises(ArchiveLimitExceeded):
        ext.inspect("t.cbz")


def test_zip_bomb_by_total_size(tmp_path: Path) -> None:
    limits = ExtractorLimits(max_total_uncompressed_bytes=1000)
    members = {f"{i}.png": png(i, 400) for i in range(4)}
    ext = _extractor(tmp_path, make_cbz(members), limits)
    with pytest.raises(ArchiveLimitExceeded):
        ext.inspect("t.cbz")


def test_too_many_entries(tmp_path: Path) -> None:
    limits = ExtractorLimits(max_entries=5)
    ext = _extractor(tmp_path, make_cbz({f"{i}.png": png(i) for i in range(6)}), limits)
    with pytest.raises(ArchiveLimitExceeded):
        ext.inspect("t.cbz")


def test_giant_page_rejected(tmp_path: Path) -> None:
    limits = ExtractorLimits(max_page_bytes=1000)
    ext = _extractor(tmp_path, make_cbz({"a.png": png(1, 5000)}), limits)
    with pytest.raises(ArchiveLimitExceeded):
        ext.inspect("t.cbz")


def test_lying_header_cannot_exceed_page_limit(tmp_path: Path) -> None:
    """Header claims a small size but data is bigger: the read is still bounded."""
    limits = ExtractorLimits(max_page_bytes=1000)
    data = bytearray(make_cbz({"a.png": png(1, 5000)}, compress=False))
    # patch uncompressed size (central directory + local header) to 100
    for sig, off in ((b"PK\x01\x02", 24), (b"PK\x03\x04", 22)):
        pos = data.index(sig)
        data[pos + off : pos + off + 4] = struct.pack("<I", 100)
    ext = _extractor(tmp_path, bytes(data), limits)
    try:
        ext.inspect("t.cbz")
        page = ext.read_page("t.cbz", 0)
        assert len(page.data) <= 1000
    except (CorruptArchive, ArchiveLimitExceeded, UnsupportedFormat):
        pass


def test_fake_extension_is_not_a_page(tmp_path: Path) -> None:
    ext = _extractor(tmp_path, make_cbz({"a.png": png(), "notes.jpg": b"just text, not an image"}))
    assert ext.inspect("t.cbz").page_count == 1


def test_only_fake_images_is_unsupported(tmp_path: Path) -> None:
    ext = _extractor(tmp_path, make_cbz({"notes.jpg": b"just text"}))
    with pytest.raises(UnsupportedFormat):
        ext.inspect("t.cbz")


def test_encrypted_entry_rejected(tmp_path: Path) -> None:
    data = bytearray(make_cbz({"a.png": png()}))
    for sig, off in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        pos = data.index(sig)
        data[pos + off] |= 0x1
    ext = _extractor(tmp_path, bytes(data))
    with pytest.raises(UnsupportedFormat):
        ext.inspect("t.cbz")


@pytest.mark.parametrize("junk", [b"not a zip at all", b"", b"PK\x03\x04" + b"\x00" * 10])
def test_corrupt_archive(tmp_path: Path, junk: bytes) -> None:
    ext = _extractor(tmp_path, junk)
    with pytest.raises(CorruptArchive):
        ext.inspect("t.cbz")


def test_truncated_archive(tmp_path: Path) -> None:
    data = make_cbz({"a.png": png(1, 3000)})
    ext = _extractor(tmp_path, data[: len(data) // 2])
    with pytest.raises(CorruptArchive):
        ext.inspect("t.cbz")


def test_corrupted_member_data(tmp_path: Path) -> None:
    data = bytearray(make_cbz({"a.png": png(1, 3000)}, compress=False))
    data[100] ^= 0xFF  # flip a byte inside the stored payload -> CRC mismatch
    ext = _extractor(tmp_path, bytes(data))
    with pytest.raises(CorruptArchive):
        ext.read_page("t.cbz", 0)


def test_huge_archive_file_is_not_read_whole(tmp_path: Path) -> None:
    """Large trailing garbage: inspect ends with a result or CorruptArchive, never hangs."""
    ext = _extractor(tmp_path, make_cbz({"a.png": png()}) + b"\0" * (5 * 1024 * 1024))
    with contextlib.suppress(CorruptArchive):
        ext.inspect("t.cbz")
