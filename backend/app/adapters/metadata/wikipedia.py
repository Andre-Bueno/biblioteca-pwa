"""Portuguese Wikipedia provider (description only; public REST API, no key).

Contract used (verified against the live service):
- `GET https://pt.wikipedia.org/w/rest.php/v1/search/page?q=..&limit=N` answers `{"pages":[{"id",
  "key","title","excerpt","description","thumbnail"}]}`;
- `GET https://pt.wikipedia.org/api/rest_v1/page/summary/<key>` answers `{"type":"standard"|
  "disambiguation","title","description","extract","content_urls":{"desktop":{"page"}},"lang"}`.

The text is CC BY-SA 4.0: the article title and URL are kept so the reader sees the attribution.
A page is used only when it is a normal article (not a disambiguation page), its title is close to
the searched title AND its own short description / opening says it is a manga, manhwa, webtoon,
comic or web novel. The article URL is BUILT from the key, never copied from the response.
"""

import re
from collections.abc import Sequence
from urllib.parse import quote, urlencode

from app.adapters.metadata._json import as_dict, as_list, as_text
from app.domain.metadata import (
    MAX_QUERY_LENGTH,
    MetadataCandidate,
    clean_title,
    has_comic_evidence,
    normalize_language,
    title_similarity,
)
from app.ports.http_gateway import HttpGateway

SEARCH = "https://pt.wikipedia.org/w/rest.php/v1/search/page"
SUMMARY = "https://pt.wikipedia.org/api/rest_v1/page/summary/"
ARTICLE = "https://pt.wikipedia.org/wiki/"
SEARCH_LIMIT = 5
MAX_SUMMARIES = 2  # pages whose summary is fetched per search (bounds the requests)
MIN_TITLE_SIMILARITY = 0.6
_KEY = re.compile(r"[^\s/\\?#<>%\x00-\x1f\x7f]{1,200}")
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)\s*$")


def portuguese_key(languages: Sequence[str]) -> str | None:
    """The configured Portuguese language code the text is filed under (first one wanted)."""
    return next((n for n in map(normalize_language, languages) if n.startswith("pt")), None)


class WikipediaProvider:
    name = "wikipedia"
    description_only = True

    def __init__(self, gateway: HttpGateway) -> None:
        self._gateway = gateway

    def search(self, title: str, languages: Sequence[str]) -> list[MetadataCandidate]:
        lang = portuguese_key(languages)
        if lang is None:
            return []
        query = urlencode([("q", title[:MAX_QUERY_LENGTH]), ("limit", str(SEARCH_LIMIT))])
        body = as_dict(self._gateway.get_json(f"{SEARCH}?{query}"))
        keys: list[str] = []
        for page in as_list(body.get("pages")):
            entry = as_dict(page)
            key, page_title = entry.get("key"), as_text(entry.get("title"), 300)
            if not isinstance(key, str) or _KEY.fullmatch(key) is None or page_title is None:
                continue
            similar = max(
                title_similarity(page_title, title),
                title_similarity(_PARENTHETICAL.sub("", page_title), title),
            )
            if similar >= MIN_TITLE_SIMILARITY:
                keys.append(key)
            if len(keys) == MAX_SUMMARIES:
                break
        found = (self._summary(key, lang, need_evidence=True) for key in keys)
        return [c for c in found if c is not None]

    def get(self, external_id: str, languages: Sequence[str]) -> MetadataCandidate | None:
        lang = portuguese_key(languages)
        if lang is None or _KEY.fullmatch(external_id) is None:
            return None
        return self._summary(external_id, lang, need_evidence=False)

    def _summary(self, key: str, lang: str, *, need_evidence: bool) -> MetadataCandidate | None:
        body = as_dict(self._gateway.get_json(f"{SUMMARY}{quote(key, safe='')}"))
        if body.get("type") != "standard":
            return None  # disambiguation, redirect or error page
        raw_title = as_text(body.get("title"), 300)
        extract = as_text(body.get("extract"))
        if raw_title is None or extract is None:
            return None
        short = as_text(body.get("description"), 300) or ""
        if need_evidence and not has_comic_evidence(f"{short} {extract[:600]}"):
            return None  # an article about something else with a similar name
        main = clean_title(_PARENTHETICAL.sub("", raw_title) or raw_title)
        full = clean_title(raw_title)
        return MetadataCandidate(
            provider="wikipedia",
            external_id=key,
            title=main,
            alt_titles=() if full == main else (full,),
            descriptions={lang: extract},
            cover_url=None,
            source_url=f"{ARTICLE}{quote(key, safe='()_,')}",
        )
