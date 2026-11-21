"""REG-008 (FIND-2026-003): every CBZ page/cover request opened every entry of the archive.

Bug: `read_page`/`read_cover` rebuilt the page list (opening and sniffing ALL images) on each
request, so a 9 500-entry CBZ cost ~175 ms of CPU per page and one user could saturate the
process; the page body (up to 64 MiB) was also read with no bound on concurrent readers.
Fix: the validated page index is cached per (rel_path, size, mtime_ns) in a bounded LRU, a page
read opens only the requested entry, and page bodies are read through a bounded gate.
"""

import threading
import time
import zipfile

import pytest
from app.adapters.extractors.cbz import CbzExtractor
from app.adapters.gate import BoundedGate
from app.domain.errors import ResourceBusy
from app.domain.library import ExtractorLimits

from fakes import FakeStorage, make_cbz, png


def _ext(files: dict[str, bytes], **kwargs: object) -> tuple[CbzExtractor, FakeStorage]:
    storage = FakeStorage(files)
    return CbzExtractor(storage, ExtractorLimits(), **kwargs), storage  # type: ignore[arg-type]


def _count_opens(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    original = zipfile.ZipFile.open

    def counting(self: zipfile.ZipFile, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        calls.append(1)
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(zipfile.ZipFile, "open", counting)
    return calls


def test_page_read_opens_at_most_the_requested_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    members = {f"{i:04d}.png": png(i) for i in range(300)}
    ext, _ = _ext({"big.cbz": make_cbz(members)})
    assert ext.inspect("big.cbz").page_count == 300  # builds (and caches) the index once
    calls = _count_opens(monkeypatch)
    assert ext.read_page("big.cbz", 150).data == png(150)
    assert len(calls) <= 1
    ext.read_cover("big.cbz")
    assert len(calls) <= 2


def test_changed_archive_invalidates_the_cached_index() -> None:
    first = make_cbz({"1.png": png(1), "2.png": png(2)})
    ext, storage = _ext(
        {"a.cbz": first},
    )
    assert ext.inspect("a.cbz").page_count == 2
    storage.files["a.cbz"] = make_cbz({"1.png": png(9), "2.png": png(2), "3.png": png(3)})
    storage.mtimes["a.cbz"] = 2
    assert ext.read_page("a.cbz", 2).data == png(3)
    assert ext.read_page("a.cbz", 0).data == png(9)


def test_index_cache_is_bounded() -> None:
    files = {f"{i}.cbz": make_cbz({"1.png": png(i)}) for i in range(5)}
    ext, _ = _ext(files, index_cache_size=2)
    for name in files:
        ext.read_page(name, 0)
    assert ext.cached_archives <= 2


def test_page_reads_are_bounded_by_the_gate() -> None:
    gate = BoundedGate(slots=1, max_waiting=0, timeout=0.1)
    ext, _ = _ext({"a.cbz": make_cbz({"1.png": png(1)})}, gate=gate)
    release = threading.Event()
    entered = threading.Event()

    def hold() -> None:
        with gate.slot():
            entered.set()
            release.wait(5)

    holder = threading.Thread(target=hold)
    holder.start()
    assert entered.wait(5)
    start = time.perf_counter()
    with pytest.raises(ResourceBusy):
        ext.read_page("a.cbz", 0)
    assert time.perf_counter() - start < 0.5
    release.set()
    holder.join(5)
    assert ext.read_page("a.cbz", 0).data == png(1)
