"""Registry of format extractors. Add new formats here; services do not change."""

from app.adapters.extractors._common import default_read_gate
from app.adapters.extractors.cbz import CbzExtractor
from app.adapters.extractors.epub import EpubExtractor
from app.adapters.extractors.folder import FolderExtractor
from app.domain.library import ExtractorLimits
from app.ports.book_reader import BookReader
from app.ports.extractor import Extractor
from app.ports.storage import StorageBackend


def build_extractors(storage: StorageBackend, limits: ExtractorLimits) -> list[Extractor]:
    # One gate shared by every extractor: it bounds the memory held by concurrent page reads.
    gate = default_read_gate()
    return [
        CbzExtractor(storage, limits, gate=gate),
        EpubExtractor(storage, limits, gate=gate),
        FolderExtractor(storage, limits, gate=gate),
    ]


def book_readers(extractors: list[Extractor]) -> list[BookReader]:
    """The extractors that can also read a book chapter by chapter (the same instances, so the
    structure cache and the read gate are shared with the scan)."""
    return [e for e in extractors if isinstance(e, BookReader)]
