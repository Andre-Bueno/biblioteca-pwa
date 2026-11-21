"""HTTP schemas of the book routes. Output only; text is already sanitized by the adapter and the
paths of the file never appear."""

from pydantic import BaseModel, ConfigDict

from app.domain.book import BookInfo


class ChapterOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    title: str


class TocEntryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    index: int
    anchor: str | None


class BookOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    authors: list[str]
    language: str | None
    chapters: list[ChapterOut]
    toc: list[TocEntryOut]
    has_cover: bool

    @classmethod
    def from_domain(cls, book: BookInfo) -> "BookOut":
        return cls(
            title=book.title,
            authors=list(book.authors),
            language=book.language,
            chapters=[ChapterOut(index=c.index, title=c.title) for c in book.chapters],
            toc=[TocEntryOut(title=t.title, index=t.index, anchor=t.anchor) for t in book.toc],
            has_cover=book.has_cover,
        )
