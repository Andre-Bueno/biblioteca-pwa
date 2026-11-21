"""AniList provider (public GraphQL API, no key): cover and English description (fallback source).

Contract used (verified against the live service): `POST https://graphql.anilist.co` with
`{"query", "variables"}` answers `{"data":{"Page":{"media":[{"id","title":{"romaji","english",
"native"},"synonyms":[..],"description","startDate":{"year"},"coverImage":{"extraLarge"}}]}}}`.
GET is not supported by the service. The description is in English only (no translation is done).
Cover images are served from `s4.anilist.co` (the only image host on the gateway allowlist).

Only the cleaned series title is sent. The source URL is BUILT from the numeric id; the cover URL
comes from the response but only the gateway allowlist decides whether it is ever fetched.
"""

from collections.abc import Sequence

from app.adapters.metadata._json import as_dict, as_list, as_text, as_year
from app.domain.metadata import MAX_ALT_TITLES, MAX_QUERY_LENGTH, MetadataCandidate, clean_title
from app.ports.http_gateway import HttpGateway

ENDPOINT = "https://graphql.anilist.co"
SITE = "https://anilist.co/manga"
SEARCH_LIMIT = 10
MAX_ID_DIGITS = 10
_FIELDS = (
    "id title{romaji english native} synonyms description(asHtml:false) "
    "startDate{year} coverImage{extraLarge}"
)
_SEARCH = (
    f"query($search:String){{Page(perPage:{SEARCH_LIMIT}){{"
    f"media(search:$search,type:MANGA){{{_FIELDS}}}}}}}"
)
_BY_ID = f"query($id:Int){{Media(id:$id,type:MANGA){{{_FIELDS}}}}}"


class AniListProvider:
    name = "anilist"
    description_only = False

    def __init__(self, gateway: HttpGateway) -> None:
        self._gateway = gateway

    def search(self, title: str, languages: Sequence[str]) -> list[MetadataCandidate]:
        payload: dict[str, object] = {
            "query": _SEARCH,
            "variables": {"search": title[:MAX_QUERY_LENGTH]},
        }
        body = as_dict(self._gateway.post_json(ENDPOINT, payload))
        media = as_list(as_dict(as_dict(body.get("data")).get("Page")).get("media"))
        found = (self._parse(entry, languages) for entry in media)
        return [c for c in found if c is not None][:SEARCH_LIMIT]

    def get(self, external_id: str, languages: Sequence[str]) -> MetadataCandidate | None:
        if (
            not (external_id.isascii() and external_id.isdigit())
            or len(external_id) > MAX_ID_DIGITS
        ):
            return None
        payload: dict[str, object] = {"query": _BY_ID, "variables": {"id": int(external_id)}}
        body = as_dict(self._gateway.post_json(ENDPOINT, payload))
        return self._parse(as_dict(body.get("data")).get("Media"), languages)

    @staticmethod
    def _parse(entry: object, languages: Sequence[str]) -> MetadataCandidate | None:
        data = as_dict(entry)
        ident = data.get("id")
        if (
            not isinstance(ident, int)
            or isinstance(ident, bool)
            or not 0 < ident < 10**MAX_ID_DIGITS
        ):
            return None
        titles = as_dict(data.get("title"))
        main = next(
            (t for key in ("english", "romaji", "native") if (t := as_text(titles.get(key), 500))),
            None,
        )
        if main is None:
            return None
        alts = [
            t for key in ("english", "romaji", "native") if (t := as_text(titles.get(key), 500))
        ]
        alts.extend(t for s in as_list(data.get("synonyms")) if (t := as_text(s, 500)) is not None)
        description = as_text(data.get("description"))
        cover = as_text(as_dict(data.get("coverImage")).get("extraLarge"), 512)
        return MetadataCandidate(
            provider="anilist",
            external_id=str(ident),
            title=clean_title(main),
            alt_titles=tuple(clean_title(a) for a in alts[:MAX_ALT_TITLES] if a != main),
            descriptions={"en": description} if description and "en" in _wanted(languages) else {},
            cover_url=cover,
            source_url=f"{SITE}/{ident}",
            year=as_year(as_dict(data.get("startDate")).get("year")),
        )


def _wanted(languages: Sequence[str]) -> set[str]:
    return {lang.strip().lower() for lang in languages}
