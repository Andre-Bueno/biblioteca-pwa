"""Registry of format extractors. Add new formats here; services do not change."""

from app.adapters.extractors._common import default_read_gate
from app.adapters.extractors.cbz import CbzExtractor
from app.adapters.extractors.folder import FolderExtractor
from app.domain.library import ExtractorLimits
from app.ports.extractor import Extractor
from app.ports.storage import StorageBackend


def build_extractors(storage: StorageBackend, limits: ExtractorLimits) -> list[Extractor]:
    # One gate shared by every extractor: it bounds the memory held by concurrent page reads.
    gate = default_read_gate()
    return [
        CbzExtractor(storage, limits, gate=gate),
        FolderExtractor(storage, limits, gate=gate),
    ]
