"""Fakes and canned source answers for the metadata tests. NO test opens a real socket: the real
providers and the real services run over `FakeGateway`, which applies the real URL allowlist
(`SafeGateway.check_url`) but answers from memory."""

import json
from collections.abc import Mapping
from urllib.parse import urlsplit

from app.adapters.http.safe_gateway import POST_HOSTS, SafeGateway
from app.domain.errors import ExternalFetchError
from app.domain.metadata import FetchedImage, sniff_image

MD_ID = "801513ba-a712-498c-8f57-cae55b38cc92"
MD_COVER_FILE = "81e1c82d-6672-400c-8c58-4ff9bfb89031.jpg"
MD_COVER_URL = f"https://uploads.mangadex.org/covers/{MD_ID}/{MD_COVER_FILE}.512.jpg"
AL_COVER_URL = "https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx1-test.jpg"


def good_png(seed: int = 0) -> bytes:
    body = bytes((seed + i) % 251 for i in range(32))
    head = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + body[:13] + b"\x00\x00\x00\x00"
    return head + body + b"\x00\x00\x00\x00IEND\xaeB`\x82"


def good_jpeg(seed: int = 0) -> bytes:
    return b"\xff\xd8\xff\xe0" + bytes((seed + i) % 251 for i in range(40)) + b"\xff\xd9"


def good_webp(seed: int = 0) -> bytes:
    payload = b"WEBPVP8 " + bytes((seed + i) % 251 for i in range(32))
    return b"RIFF" + len(payload).to_bytes(4, "little") + payload


def mangadex_entry(
    ident: str = MD_ID,
    *,
    title: Mapping[str, str] | None = None,
    alt_titles: list[dict[str, str]] | None = None,
    description: Mapping[str, str] | None = None,
    cover_file: str | None = MD_COVER_FILE,
    year: int | None = 1989,
    kind: str = "manga",
) -> dict[str, object]:
    relationships: list[dict[str, object]] = [{"id": "x", "type": "author"}]
    if cover_file is not None:
        relationships.append(
            {"id": "c", "type": "cover_art", "attributes": {"fileName": cover_file}}
        )
    return {
        "id": ident,
        "type": kind,
        "attributes": {
            "title": dict(title if title is not None else {"ja-ro": "Berserk"}),
            "altTitles": alt_titles or [],
            "description": dict(description or {}),
            "year": year,
        },
        "relationships": relationships,
    }


def mangadex_list(*entries: dict[str, object]) -> dict[str, object]:
    return {"result": "ok", "response": "collection", "data": list(entries), "total": len(entries)}


def anilist_media(
    ident: int = 30002,
    *,
    english: str | None = "Berserk",
    romaji: str | None = "Berserk",
    synonyms: list[str] | None = None,
    description: str | None = "A dark fantasy.",
    cover: str | None = AL_COVER_URL,
    year: int | None = 1989,
) -> dict[str, object]:
    return {
        "id": ident,
        "title": {"romaji": romaji, "english": english, "native": None},
        "synonyms": synonyms or [],
        "description": description,
        "startDate": {"year": year},
        "coverImage": {"extraLarge": cover},
    }


def anilist_page(*media: dict[str, object]) -> dict[str, object]:
    return {"data": {"Page": {"media": list(media)}}}


class FakeGateway:
    """Answers `HttpGateway` calls from routes registered by the test.

    A route is `(needle, payload)`: the first route whose needle is in the URL (or, for POST, in
    the JSON of the variables) answers; a payload that is an exception is raised instead.
    """

    def __init__(self) -> None:
        self.json_routes: list[tuple[str, object]] = []
        self.images: dict[str, bytes | Exception] = {}
        self.calls: list[tuple[str, str]] = []
        self.on_image: list[object] = []  # callables run before each image answer

    def route(self, needle: str, payload: object) -> None:
        self.json_routes.append((needle, payload))

    def _answer(self, key: str) -> object:
        for needle, payload in self.json_routes:
            if needle in key:
                if isinstance(payload, Exception):
                    raise payload
                if callable(payload):
                    return payload(key)  # an answer that depends on the request
                return payload
        raise ExternalFetchError("bad_status")

    def get_json(self, url: str) -> object:
        SafeGateway.check_url(url)
        self.calls.append(("GET", url))
        return self._answer(url)

    def post_json(self, url: str, payload: dict[str, object]) -> object:
        host, _ = SafeGateway.check_url(url)
        if host not in POST_HOSTS:
            raise ExternalFetchError("host_not_allowed")
        variables = json.dumps(payload.get("variables"))
        self.calls.append(("POST", f"{urlsplit(url).netloc} {variables}"))
        return self._answer(variables)

    def get_image(self, url: str) -> FetchedImage:
        SafeGateway.check_url(url)
        self.calls.append(("IMG", url))
        for hook in self.on_image:
            hook()  # type: ignore[operator]
        entry = self.images.get(url)
        if entry is None:
            raise ExternalFetchError("bad_status")
        if isinstance(entry, Exception):
            raise entry
        sniffed = sniff_image(entry)
        if sniffed is None:
            raise ExternalFetchError("invalid_image")
        return FetchedImage(data=entry, media_type=sniffed[0], ext=sniffed[1])

    def hosts_called(self) -> list[str]:
        return [urlsplit(u).netloc for kind, u in self.calls if kind != "POST"]


# ---------------------------------------------------------------- the real "Omniscient Reader" case
# Shapes probed on the live services (2026-11-20); texts are synthetic placeholders.

ORV = "Omniscient Reader's Viewpoint"
ORV_WORK_ID = "9a414441-bbad-43f1-a3a7-dc262ca790a3"
ORV_COVER_FILE = "5d3f7f0a-1111-4222-8333-444455556666.jpg"
ORV_COVER_URL = f"https://uploads.mangadex.org/covers/{ORV_WORK_ID}/{ORV_COVER_FILE}.512.jpg"
ORV_EN_TEXT = (
    "A reader discovers that the web novel he follows has become real. He knows how it ends."
)
AL_ORV_COVER = "https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx119257-test.jpg"


def orv_mangadex_answer() -> dict[str, object]:
    """MangaDex answer for the library title: three editions first, the work only 4th, with the
    library title as an alternative title and NO pt-br description (de, en, es, ... only)."""
    cover = "0aaaaaaa-1111-4222-8333-444455556666.jpg"
    book = mangadex_entry(
        "46392cb3-a0f8-42e4-b2ac-b89637df56d9",
        title={"en": f"{ORV} (Book Version)"},
        alt_titles=[
            {"ko": "전지적 독자 시점"},
            {"en": ORV},
            {"pt-br": "Ponto de vista do leitor onisciente"},
        ],
        description={"en": "Book edition text."},
        cover_file=cover,
        year=None,
    )
    blind = mangadex_entry(
        "7cf4bacd-839f-41e7-b1c8-5852a9079c7f",
        title={"en": f"{ORV} - Blind (Doujinshi)"},
        alt_titles=[{"ko": "블라인드"}],
        description={"en": "Doujinshi text."},
        cover_file=cover,
        year=2020,
    )
    maid = mangadex_entry(
        "e8067480-6c51-4c61-a365-50f36461644e",
        title={"en": f"{ORV}  - Maid, Make, Mine (Doujinshi)"},
        alt_titles=[{"ko": "메이드, 메이크, 마인"}],
        description={"en": "Doujinshi text."},
        cover_file=cover,
        year=2019,
    )
    work = mangadex_entry(
        ORV_WORK_ID,
        title={"ko-ro": "Jeonjijeok Dokja Sijeom"},
        alt_titles=[
            {"en": ORV},
            {"fr": "Lecteur omniscient"},
            {"ja": "全知的な読者の視点から"},
            {"en": "ORV"},
        ],
        description={"de": "Text.", "en": ORV_EN_TEXT, "es": "Texto.", "fr": "Texte.", "ko": "글."},
        cover_file=ORV_COVER_FILE,
        year=2020,
    )
    return mangadex_list(book, blind, maid, work)


def orv_anilist_answer() -> dict[str, object]:
    return anilist_page(
        anilist_media(
            119257,
            english="Omniscient Reader",
            romaji="Jeonjijeok Dokja Sijeom",
            synonyms=[ORV, "ORV"],
            description="AniList English text <br>of the series.",
            cover=AL_ORV_COVER,
            year=2020,
        )
    )


def wikipedia_search_answer(*pages: tuple[str, str, str]) -> dict[str, object]:
    """(key, title, short description) per page, in the shape of the REST search."""
    return {
        "pages": [
            {"id": i, "key": k, "title": t, "excerpt": "x", "description": d, "thumbnail": None}
            for i, (k, t, d) in enumerate(pages, start=1)
        ]
    }


def wikipedia_summary_answer(
    title: str, extract: str, *, description: str = "série de mangá", kind: str = "standard"
) -> dict[str, object]:
    return {
        "type": kind,
        "title": title,
        "description": description,
        "extract": extract,
        "lang": "pt",
        "content_urls": {"desktop": {"page": "https://evil.example/not-used"}},
    }


def googlebooks_volume(
    ident: str,
    title: str,
    description: str | None,
    *,
    categories: list[str] | None = None,
    language: str = "pt",
    published: str | None = "2020-05-01",
) -> dict[str, object]:
    info: dict[str, object] = {"title": title, "language": language, "categories": categories or []}
    if description is not None:
        info["description"] = description
    if published is not None:
        info["publishedDate"] = published
    return {"kind": "books#volume", "id": ident, "volumeInfo": info}


def googlebooks_list(*items: dict[str, object]) -> dict[str, object]:
    return {"kind": "books#volumes", "totalItems": len(items), "items": list(items)}


def mymemory_answer(
    text: str, *, match: float = 0.85, status: int = 200, quota: bool = False
) -> dict[str, object]:
    return {
        "responseData": {"translatedText": text, "match": match},
        "quotaFinished": quota,
        "responseDetails": "",
        "responseStatus": status,
        "matches": [],
    }


def fake_translation(url: str) -> dict[str, object]:
    """A MyMemory stand-in: translates by prefixing, so tests can see what was sent."""
    from urllib.parse import parse_qs, urlsplit

    q = parse_qs(urlsplit(url).query)["q"][0]
    return mymemory_answer(f"Traducao: {q}")
