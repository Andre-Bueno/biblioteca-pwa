"""Google Books provider (description only; public API, no key, small anonymous quota).

Contract used (official Books API v1; the live service answered 429 on every probe from the
development machine, so the structure below follows the documentation and could not be confirmed
against a real answer): `GET /books/v1/volumes?q=intitle:"..."&langRestrict=pt` answers
`{"totalItems","items":[{"id","volumeInfo":{"title","subtitle","description","categories":[..],
"language","publishedDate","infoLink"}}]}` and `GET /books/v1/volumes/<id>` answers one volume.

A volume is used only if it is in Portuguese, has a description and says (category, title or
description) that it is a comic/manga/manhwa/webtoon. Volumes of the same series are collapsed to
the first one. The cover is NOT taken (another host); the page URL is built from the id. A 429 is
handled by the gateway (Retry-After, backoff): the quota is never hammered.
"""

import re
from collections.abc import Sequence
from urllib.parse import quote, urlencode

from app.adapters.metadata._json import as_dict, as_list, as_text, as_year
from app.adapters.metadata.wikipedia import portuguese_key
from app.domain.metadata import (
    MAX_QUERY_LENGTH,
    MetadataCandidate,
    clean_title,
    has_comic_evidence,
    normalize_title,
)
from app.ports.http_gateway import HttpGateway

API = "https://www.googleapis.com/books/v1/volumes"
PAGE = "https://books.google.com/books"
SEARCH_LIMIT = 10
_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")


class GoogleBooksProvider:
    name = "googlebooks"
    description_only = True

    def __init__(self, gateway: HttpGateway) -> None:
        self._gateway = gateway

    def search(self, title: str, languages: Sequence[str]) -> list[MetadataCandidate]:
        lang = portuguese_key(languages)
        if lang is None:
            return []
        phrase = title[:MAX_QUERY_LENGTH].replace('"', " ")
        query = urlencode(
            [
                ("q", f'intitle:"{phrase}"'),
                ("langRestrict", "pt"),
                ("maxResults", str(SEARCH_LIMIT)),
                ("printType", "books"),
            ]
        )
        body = as_dict(self._gateway.get_json(f"{API}?{query}"))
        seen: set[str] = set()
        found: list[MetadataCandidate] = []
        for item in as_list(body.get("items")):
            candidate = self._parse(item, lang, need_evidence=True)
            if candidate is None:
                continue
            series_key = normalize_title(candidate.title)
            if series_key in seen:
                continue  # another volume of the same series
            seen.add(series_key)
            found.append(candidate)
        return found

    def get(self, external_id: str, languages: Sequence[str]) -> MetadataCandidate | None:
        lang = portuguese_key(languages)
        if lang is None or _ID.fullmatch(external_id) is None:
            return None
        body = self._gateway.get_json(f"{API}/{quote(external_id, safe='')}")
        return self._parse(body, lang, need_evidence=False)

    @staticmethod
    def _parse(entry: object, lang: str, *, need_evidence: bool) -> MetadataCandidate | None:
        data = as_dict(entry)
        ident = data.get("id")
        if not isinstance(ident, str) or _ID.fullmatch(ident) is None:
            return None
        info = as_dict(data.get("volumeInfo"))
        title = as_text(info.get("title"), 300)
        description = as_text(info.get("description"))
        language = as_text(info.get("language"), 16) or ""
        if title is None or description is None or not language.lower().startswith("pt"):
            return None
        categories = " ".join(c for c in as_list(info.get("categories")) if isinstance(c, str))
        if need_evidence and not has_comic_evidence(f"{categories} {title} {description[:600]}"):
            return None
        published = as_text(info.get("publishedDate"), 32) or ""
        return MetadataCandidate(
            provider="googlebooks",
            external_id=ident,
            title=clean_title(title),
            alt_titles=(),
            descriptions={lang: description},
            cover_url=None,
            source_url=f"{PAGE}?{urlencode([('id', ident)])}",
            year=as_year(int(published[:4])) if published[:4].isdigit() else None,
        )
