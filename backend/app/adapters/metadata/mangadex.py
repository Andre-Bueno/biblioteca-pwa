"""MangaDex provider (public API, no key): cover, pt-br description and alternative titles.

Contract used (official API, verified against the live service): `GET /manga?title=..&includes[]=
cover_art` and `GET /manga/{id}?includes[]=cover_art` answer `{"result":"ok","data":[{"id",
"type":"manga","attributes":{"title":{lang:text},"altTitles":[{lang:text}],"description":{lang:
text},"year"},"relationships":[{"type":"cover_art","attributes":{"fileName"}}]}]}`. Covers are
served from `uploads.mangadex.org/covers/<manga id>/<file>.512.jpg`.

Only the cleaned series title is sent. The source URL and the cover URL are BUILT here from
validated ids, never copied from a response.
"""

import re
from collections.abc import Sequence
from urllib.parse import quote, urlencode

from app.adapters.metadata._json import as_dict, as_list, as_text, as_year
from app.domain.metadata import (
    MAX_ALT_TITLES,
    MAX_QUERY_LENGTH,
    MetadataCandidate,
    clean_title,
    normalize_language,
)
from app.ports.http_gateway import HttpGateway

API = "https://api.mangadex.org"
SITE = "https://mangadex.org/title"
COVERS = "https://uploads.mangadex.org/covers"
SEARCH_LIMIT = 10
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_COVER_FILE = re.compile(r"[0-9A-Za-z-]{1,64}\.(?:jpg|jpeg|png|webp|gif)")
_TITLE_PREFERENCE = ("en", "ja-ro")


class MangaDexProvider:
    name = "mangadex"
    description_only = False

    def __init__(self, gateway: HttpGateway) -> None:
        self._gateway = gateway

    def search(self, title: str, languages: Sequence[str]) -> list[MetadataCandidate]:
        query = urlencode(
            [
                ("title", title[:MAX_QUERY_LENGTH]),
                ("limit", str(SEARCH_LIMIT)),
                ("includes[]", "cover_art"),
                ("order[relevance]", "desc"),
            ]
        )
        body = as_dict(self._gateway.get_json(f"{API}/manga?{query}"))
        found = (self._parse(entry, languages) for entry in as_list(body.get("data")))
        return [c for c in found if c is not None][:SEARCH_LIMIT]

    def get(self, external_id: str, languages: Sequence[str]) -> MetadataCandidate | None:
        if _UUID.fullmatch(external_id) is None:
            return None
        url = f"{API}/manga/{quote(external_id)}?{urlencode([('includes[]', 'cover_art')])}"
        body = as_dict(self._gateway.get_json(url))
        return self._parse(body.get("data"), languages)

    @staticmethod
    def _parse(entry: object, languages: Sequence[str]) -> MetadataCandidate | None:
        data = as_dict(entry)
        ident = data.get("id")
        if not isinstance(ident, str) or _UUID.fullmatch(ident) is None:
            return None
        if data.get("type") != "manga":
            return None
        attrs = as_dict(data.get("attributes"))
        titles = {
            normalize_language(k): t
            for k, v in as_dict(attrs.get("title")).items()
            if (t := as_text(v, 500)) is not None
        }
        main_raw = next((titles[k] for k in _TITLE_PREFERENCE if k in titles), None)
        if main_raw is None and titles:
            main_raw = next(iter(titles.values()))
        if main_raw is None:
            return None
        alts: list[str] = [t for t in titles.values() if t != main_raw]
        for alt in as_list(attrs.get("altTitles")):
            alts.extend(t for v in as_dict(alt).values() if (t := as_text(v, 500)) is not None)
        wanted = {normalize_language(lang) for lang in languages}
        descriptions = {
            lang: text
            for k, v in as_dict(attrs.get("description")).items()
            if (lang := normalize_language(k)) in wanted and (text := as_text(v)) is not None
        }
        return MetadataCandidate(
            provider="mangadex",
            external_id=ident,
            title=clean_title(main_raw),
            alt_titles=tuple(clean_title(a) for a in alts[:MAX_ALT_TITLES]),
            descriptions=descriptions,
            cover_url=_cover_url(ident, data.get("relationships")),
            source_url=f"{SITE}/{ident}",
            year=as_year(attrs.get("year")),
        )


def _cover_url(manga_id: str, relationships: object) -> str | None:
    for rel in as_list(relationships):
        entry = as_dict(rel)
        if entry.get("type") != "cover_art":
            continue
        file_name = as_dict(entry.get("attributes")).get("fileName")
        if isinstance(file_name, str) and _COVER_FILE.fullmatch(file_name):
            return f"{COVERS}/{manga_id}/{file_name}.512.jpg"
    return None
