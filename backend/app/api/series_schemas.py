"""HTTP schemas for series. Never carries `folder_rel_path`, `cover_path`, a remote cover URL or
file names."""

from pydantic import BaseModel, ConfigDict, Field

from app.domain.metadata import MAX_DESCRIPTION_LENGTH, PROVIDER_LABELS
from app.domain.progress import Progress
from app.domain.series import Series, SeriesSummary, series_kind, short_description
from app.services.metadata_service import CandidateView
from app.services.series_service import ChapterView, SeriesDetail, SeriesPage

MAX_TITLE_INPUT = 200


class SeriesProgressOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read_chapters: int
    last_item_id: str | None


class SeriesItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    kind: str  # "manga" | "book" | "mixed"
    chapter_count: int
    has_cover: bool
    description: str | None
    description_lang: str | None
    metadata_state: str
    progress: SeriesProgressOut

    @classmethod
    def from_domain(cls, s: SeriesSummary) -> "SeriesItemOut":
        return cls(
            id=s.series.id,
            title=s.series.title,
            kind=s.kind,
            chapter_count=s.chapter_count,
            has_cover=s.has_cover,
            description=short_description(s.series.description),
            description_lang=s.series.description_lang,
            metadata_state=s.series.metadata_state,
            progress=SeriesProgressOut(read_chapters=s.read_chapters, last_item_id=s.last_item_id),
        )


class SeriesListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SeriesItemOut]
    limit: int
    offset: int
    has_more: bool

    @classmethod
    def from_page(cls, page: SeriesPage) -> "SeriesListOut":
        return cls(
            items=[SeriesItemOut.from_domain(s) for s in page.items],
            limit=page.limit,
            offset=page.offset,
            has_more=page.has_more,
        )


class ChapterProgressOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locator: int
    percent: float
    finished: bool

    @classmethod
    def from_domain(cls, p: Progress) -> "ChapterProgressOut":
        return cls(locator=p.locator, percent=p.percent, finished=p.finished)


class ChapterOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str  # "manga" | "book" | "pdf"
    title: str
    number: float | None
    page_count: int  # for a book: the number of chapters
    progress: ChapterProgressOut | None

    @classmethod
    def from_domain(cls, c: ChapterView) -> "ChapterOut":
        return cls(
            id=c.item.id,
            type=c.item.type.value,
            title=c.title,
            number=c.item.chapter_number,
            page_count=c.item.page_count,
            progress=None if c.progress is None else ChapterProgressOut.from_domain(c.progress),
        )


class SourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    url: str | None  # https page of the match at the source; never a local path


def source_out(series: Series) -> SourceOut | None:
    """The source of the metadata, or None. The URL is only passed on when it is https."""
    if series.metadata_source is None:
        return None
    url = series.source_url
    return SourceOut(
        name=PROVIDER_LABELS.get(series.metadata_source, series.metadata_source),
        url=url if url is not None and url.startswith("https://") else None,
    )


def description_source_out(series: Series) -> SourceOut | None:
    """Whose text the description is (for a translation: the source of the ORIGINAL English)."""
    if series.description_source_name is None:
        return None
    url = series.description_source_url
    return SourceOut(
        name=series.description_source_name,
        url=url if url is not None and url.startswith("https://") else None,
    )


class ContinueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    locator: int


class SeriesOut(BaseModel):
    # `continue` is a Python keyword: the attribute is `resume`, the JSON key stays `continue`.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    title: str
    kind: str  # "manga" | "book" | "mixed"
    description: str | None
    description_lang: str | None
    description_origin: str | None  # "source" | "translated" | "manual" | null
    description_source: SourceOut | None
    source: SourceOut | None  # cover / title source
    metadata_state: str
    chapter_count: int
    has_cover: bool
    chapters: list[ChapterOut]
    resume: ContinueOut | None = Field(alias="continue")

    @classmethod
    def from_domain(cls, d: SeriesDetail) -> "SeriesOut":
        s = d.series
        point = d.continue_point
        return cls(
            id=s.id,
            title=s.title,
            kind=series_kind(c.item.type.value for c in d.chapters),
            description=s.description,
            description_lang=s.description_lang,
            description_origin=s.description_origin,
            description_source=description_source_out(s),
            source=source_out(s),
            metadata_state=s.metadata_state,
            chapter_count=len(d.chapters),
            has_cover=any(c.item.has_cover for c in d.chapters),
            chapters=[ChapterOut.from_domain(c) for c in d.chapters],
            resume=None
            if point is None
            else ContinueOut(item_id=point.item_id, locator=point.locator),
        )


class SeriesMetadataOut(BaseModel):
    """Result of a metadata action (select / manual edit / clear)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str | None
    description_lang: str | None
    description_origin: str | None
    description_source: SourceOut | None
    source: SourceOut | None
    metadata_state: str
    cover_downloaded: bool  # a cover was fetched from a source (else the first chapter is used)

    @classmethod
    def from_domain(cls, s: Series) -> "SeriesMetadataOut":
        return cls(
            id=s.id,
            title=s.title,
            description=s.description,
            description_lang=s.description_lang,
            description_origin=s.description_origin,
            description_source=description_source_out(s),
            source=source_out(s),
            metadata_state=s.metadata_state,
            cover_downloaded=s.cover_path is not None,
        )


class CandidateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    external_id: str
    title: str
    year: int | None
    description: str | None
    cover_available: bool
    url: str | None

    @classmethod
    def from_view(cls, c: CandidateView) -> "CandidateOut":
        return cls(
            provider=c.provider,
            external_id=c.external_id,
            title=c.title,
            year=c.year,
            description=c.description,
            cover_available=c.cover_available,
            url=c.url,
        )


class CandidateListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CandidateOut]


class _StrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SelectCandidateRequest(_StrictIn):
    provider: str = Field(min_length=1, max_length=32, pattern=r"^[a-z]{1,32}$")
    # Ids are validated again by each provider; this only keeps path-like and markup characters out
    # (a Wikipedia key may hold letters with accents, "_" and parentheses).
    external_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[^\s/\\?#<>%\x00-\x1f\x7f]{1,128}$"
    )


class ManualMetadataRequest(_StrictIn):
    title: str | None = Field(default=None, max_length=MAX_TITLE_INPUT)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
