"""HTTP schemas for the catalog and scan routes. Never carries `rel_path` or any file name."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.item import Item, ItemType
from app.services.catalog import ItemPage
from app.services.enrich_runner import EnrichState, EnrichStatus
from app.services.scan_runner import ScanState, ScanStatus


class ItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: ItemType
    title: str
    format: str
    page_count: int
    added_at: datetime
    has_cover: bool

    @classmethod
    def from_domain(cls, item: Item) -> "ItemOut":
        return cls(
            id=item.id,
            type=item.type,
            title=item.title,
            format=item.format,
            page_count=item.page_count,
            added_at=item.added_at,
            has_cover=item.has_cover,
        )


class ItemListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ItemOut]
    limit: int
    offset: int
    has_more: bool

    @classmethod
    def from_page(cls, page: ItemPage) -> "ItemListOut":
        return cls(
            items=[ItemOut.from_domain(i) for i in page.items],
            limit=page.limit,
            offset=page.offset,
            has_more=page.has_more,
        )


class ScanStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ScanState
    processed: int
    total: int
    started_at: datetime | None
    finished_at: datetime | None
    added: int
    updated: int
    unchanged: int
    removed: int
    skipped: int
    error_count: int
    errors_by_reason: dict[str, int]

    @classmethod
    def from_domain(cls, status: ScanStatus) -> "ScanStatusOut":
        return cls(
            state=status.state,
            processed=status.processed,
            total=status.total,
            started_at=status.started_at,
            finished_at=status.finished_at,
            added=status.added,
            updated=status.updated,
            unchanged=status.unchanged,
            removed=status.removed,
            skipped=status.skipped,
            error_count=status.error_count,
            errors_by_reason=status.errors_by_reason,
        )


class EnrichStatusOut(BaseModel):
    """Counts only: no URL, host or error detail of the sources ever appears here."""

    model_config = ConfigDict(extra="forbid")

    state: EnrichState
    started_at: datetime | None
    finished_at: datetime | None
    matched: int
    not_found: int
    skipped: int
    errors: int

    @classmethod
    def from_domain(cls, status: EnrichStatus) -> "EnrichStatusOut":
        return cls(
            state=status.state,
            started_at=status.started_at,
            finished_at=status.finished_at,
            matched=status.matched,
            not_found=status.not_found,
            skipped=status.skipped,
            errors=status.errors,
        )
