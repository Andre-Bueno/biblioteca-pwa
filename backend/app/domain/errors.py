"""Domain errors. Messages must never contain client-supplied paths or secrets."""


class DomainError(Exception):
    """Base class for all domain errors."""


class UnsafePath(DomainError):  # noqa: N818 - name fixed by the domain contract
    """A path (or archive member name) is not allowed: traversal, absolute, link, reserved."""


class UnsupportedFormat(DomainError):  # noqa: N818
    """The file is not a supported format (or is encrypted / has no readable pages)."""


class ArchiveLimitExceeded(DomainError):  # noqa: N818
    """An archive exceeded a configured safety limit (entries, size, ratio, page size)."""


class CorruptArchive(DomainError):  # noqa: N818
    """The archive is malformed or unreadable."""


class PageOutOfRange(DomainError):  # noqa: N818
    """The requested page index does not exist."""


class ItemNotFound(DomainError):  # noqa: N818
    """No item with the requested id."""


class LibraryUnavailable(DomainError):  # noqa: N818
    """The library directory is missing or unreadable (message never carries the path)."""


class ScanAlreadyRunning(DomainError):  # noqa: N818
    """A library scan is already in progress."""


class DataAccessError(DomainError):
    """Persistence failed. Deliberately generic: DB driver details may carry sensitive data."""


class ResourceBusy(DomainError):  # noqa: N818
    """A bounded, expensive resource (password hashing, page reads) has no free slot right now.

    Raised instead of queueing without limit, so a flood cannot hold every worker thread. The
    caller answers a generic 503 and the client retries later.
    """


class ExternalFetchError(DomainError):
    """A fetch from an external public source failed or was refused.

    `reason` is one of a small fixed set of codes (never a URL, host, header or body), so it is
    safe to log and count. Callers treat it as "source unavailable" and move on.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MetadataDisabled(DomainError):  # noqa: N818
    """External metadata lookups are switched off (`METADATA_ENABLED=false`)."""


class InvalidMetadata(DomainError):  # noqa: N818
    """A manual metadata edit has no usable content (empty title, nothing to change)."""


class EnrichAlreadyRunning(DomainError):  # noqa: N818
    """A metadata enrichment run is already in progress."""


class UpdateNotConfigured(DomainError):  # noqa: N818
    """No update webhook is configured (or the version check is off)."""


class UpdateNotAvailable(DomainError):  # noqa: N818
    """The tag asked for is not the known latest release, or there is nothing to update to."""


class UpdateAlreadyRequested(DomainError):  # noqa: N818
    """An update was requested a moment ago."""


class UpdateNotifyFailed(DomainError):  # noqa: N818
    """The webhook did not accept the request. Deliberately carries no URL, host or body."""
