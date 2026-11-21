"""MangaDex and AniList adapters over canned answers (no network): parsing, language choice,
hostile shapes, and what is (and is not) sent."""

import pytest
from app.adapters.metadata.anilist import AniListProvider
from app.adapters.metadata.mangadex import MangaDexProvider
from app.domain.errors import ExternalFetchError

from metadata_fakes import (
    AL_COVER_URL,
    MD_COVER_FILE,
    MD_COVER_URL,
    MD_ID,
    FakeGateway,
    anilist_media,
    anilist_page,
    mangadex_entry,
    mangadex_list,
)

LANGS = ("pt-br", "pt", "en")


def _md(entry: dict[str, object]) -> tuple[MangaDexProvider, FakeGateway]:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org/manga", mangadex_list(entry))
    return MangaDexProvider(gateway), gateway


# ------------------------------------------------------------------ MangaDex


def test_mangadex_parses_the_real_shape() -> None:
    entry = mangadex_entry(
        title={"ja-ro": "Berserk"},
        alt_titles=[{"ja": "ベルセルク"}, {"pt-br": "Berserk BR"}, {"en": "Berserk EN"}],
        description={"en": "English text", "pt-br": "Texto em portugues", "ru": "ru text"},
    )
    provider, gateway = _md(entry)
    [candidate] = provider.search("Berserk", LANGS)
    assert candidate.provider == "mangadex" and candidate.external_id == MD_ID
    assert candidate.title == "Berserk" and candidate.year == 1989
    assert set(candidate.alt_titles) >= {"Berserk BR", "Berserk EN", "ベルセルク"}
    assert dict(candidate.descriptions) == {"en": "English text", "pt-br": "Texto em portugues"}
    assert candidate.cover_url == MD_COVER_URL  # built from the id and the validated file name
    assert candidate.source_url == f"https://mangadex.org/title/{MD_ID}"
    [(kind, url)] = gateway.calls
    assert kind == "GET" and url.startswith("https://api.mangadex.org/manga?title=Berserk&")
    assert "includes%5B%5D=cover_art" in url and "limit=10" in url


def test_mangadex_title_preference_en_then_ja_ro_then_any() -> None:
    both = mangadex_entry(title={"ja-ro": "Romaji", "en": "English"})
    assert _md(both)[0].search("x", LANGS)[0].title == "English"
    only_ko = mangadex_entry(title={"ko": "Hangul"})
    assert _md(only_ko)[0].search("x", LANGS)[0].title == "Hangul"


def test_mangadex_only_the_search_text_is_sent() -> None:
    provider, gateway = _md(mangadex_entry())
    provider.search("Omniscient Reader's Viewpoint", LANGS)
    [(_, url)] = gateway.calls
    assert "Omniscient+Reader%27s+Viewpoint" in url
    assert provider.search("x" * 500, LANGS) is not None
    assert len(gateway.calls[-1][1]) < 300  # the query is cut to 100 characters


@pytest.mark.parametrize(
    "bad_file",
    ["../../etc/passwd", "a/b.jpg", "x.exe", "a b.jpg", "x.jpg?x=1", "http://evil/x.jpg", "." * 70],
)
def test_mangadex_a_hostile_cover_file_name_yields_no_cover(bad_file: str) -> None:
    provider, _ = _md(mangadex_entry(cover_file=bad_file))
    [candidate] = provider.search("x", LANGS)
    assert candidate.cover_url is None


def test_mangadex_without_cover_relationship() -> None:
    provider, _ = _md(mangadex_entry(cover_file=None))
    assert provider.search("x", LANGS)[0].cover_url is None


@pytest.mark.parametrize(
    "entry",
    [
        mangadex_entry(ident="not-a-uuid"),
        mangadex_entry(ident="../../x"),
        mangadex_entry(ident=MD_ID.upper()),
        mangadex_entry(kind="author"),
        mangadex_entry(title={}),
        mangadex_entry(title={"en": "   "}),
        mangadex_entry(title={"en": 5}),  # type: ignore[dict-item]
        {"id": MD_ID, "type": "manga", "attributes": "nope"},
        "a string",
        None,
        [],
    ],
)
def test_mangadex_skips_malformed_entries(entry: object) -> None:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org", {"data": [entry]})
    assert MangaDexProvider(gateway).search("x", LANGS) == []


@pytest.mark.parametrize("body", [{}, [], "x", {"data": "x"}, {"data": {"a": 1}}, None, 7])
def test_mangadex_tolerates_any_top_level_shape(body: object) -> None:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org", body)
    assert MangaDexProvider(gateway).search("x", LANGS) == []


def test_mangadex_odd_field_types_are_ignored_not_fatal() -> None:
    entry = mangadex_entry(year=None)
    attrs = entry["attributes"]
    assert isinstance(attrs, dict)
    attrs["description"] = {"pt-br": ["list"], "en": 5, "pt": "ok"}
    attrs["altTitles"] = ["str", 5, {"en": 5}, {"en": "Real alt"}]
    attrs["year"] = "1999"
    provider, _ = _md(entry)
    [candidate] = provider.search("x", LANGS)
    assert dict(candidate.descriptions) == {"pt": "ok"}
    assert "Real alt" in candidate.alt_titles and candidate.year is None


def test_mangadex_markup_in_titles_is_made_safe() -> None:
    provider, _ = _md(mangadex_entry(title={"en": "<script>alert(1)</script>Bad\x00‮Name"}))
    [candidate] = provider.search("x", LANGS)
    for bad in ("<", ">", "\x00", "‮"):
        assert bad not in candidate.title


def test_mangadex_get_validates_the_id_before_any_request() -> None:
    provider, gateway = _md(mangadex_entry())
    for bad in ("", "x", "../manga", MD_ID.upper(), MD_ID + "/../x", MD_ID + "?a=1", "g" * 36):
        assert provider.get(bad, LANGS) is None
    assert gateway.calls == []


def test_mangadex_get_fetches_one_entry() -> None:
    gateway = FakeGateway()
    gateway.route(f"/manga/{MD_ID}", {"result": "ok", "data": mangadex_entry()})
    candidate = MangaDexProvider(gateway).get(MD_ID, LANGS)
    assert candidate is not None and candidate.cover_url == MD_COVER_URL
    assert gateway.calls[0][1] == f"https://api.mangadex.org/manga/{MD_ID}?includes%5B%5D=cover_art"


def test_mangadex_a_gateway_failure_propagates_as_a_generic_error() -> None:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org", ExternalFetchError("timeout"))
    with pytest.raises(ExternalFetchError):
        MangaDexProvider(gateway).search("x", LANGS)


def test_mangadex_cover_file_name_is_part_of_the_built_url_only() -> None:
    assert MD_COVER_FILE in MD_COVER_URL and MD_COVER_URL.startswith(
        "https://uploads.mangadex.org/covers/"
    )


# ------------------------------------------------------------------ AniList


def _al(*media: dict[str, object]) -> tuple[AniListProvider, FakeGateway]:
    gateway = FakeGateway()
    gateway.route("", anilist_page(*media))
    return AniListProvider(gateway), gateway


def test_anilist_parses_the_real_shape() -> None:
    media = anilist_media(
        30002,
        english="Berserk",
        romaji="Berserk (romaji)",
        synonyms=["Berserk: Deluxe"],
        description="A <i>dark</i> tale.<br>Second line.",
    )
    provider, gateway = _al(media)
    [candidate] = provider.search("Berserk", LANGS)
    assert candidate.provider == "anilist" and candidate.external_id == "30002"
    assert candidate.title == "Berserk" and candidate.year == 1989
    assert "Berserk: Deluxe" in candidate.alt_titles and "Berserk (romaji)" in candidate.alt_titles
    assert candidate.source_url == "https://anilist.co/manga/30002"  # built from the id
    assert candidate.cover_url == AL_COVER_URL
    assert set(candidate.descriptions) == {"en"}  # English only: no automatic translation
    assert gateway.calls == [("POST", 'graphql.anilist.co {"search": "Berserk"}')]


def test_anilist_description_only_when_english_is_wanted() -> None:
    provider, _ = _al(anilist_media())
    assert provider.search("x", ("pt-br", "pt"))[0].descriptions == {}


def test_anilist_site_url_from_the_response_is_never_used() -> None:
    media = anilist_media()
    media["siteUrl"] = "https://evil.example/phish"
    provider, _ = _al(media)
    assert provider.search("x", LANGS)[0].source_url == "https://anilist.co/manga/30002"


@pytest.mark.parametrize(
    "media",
    [
        anilist_media(ident=0),
        anilist_media(ident=-5),
        anilist_media(ident=10**12),
        {"id": "30002", "title": {"english": "x"}},
        {"id": True, "title": {"english": "x"}},
        anilist_media(english=None, romaji=None),
        "str",
        None,
    ],
)
def test_anilist_skips_malformed_entries(media: object) -> None:
    gateway = FakeGateway()
    gateway.route("", {"data": {"Page": {"media": [media]}}})
    assert AniListProvider(gateway).search("x", LANGS) == []


@pytest.mark.parametrize(
    "body",
    [{}, [], "x", {"errors": [{"message": "boom"}], "data": None}, {"data": {"Page": None}}, None],
)
def test_anilist_tolerates_error_bodies(body: object) -> None:
    gateway = FakeGateway()
    gateway.route("", body)
    assert AniListProvider(gateway).search("x", LANGS) == []


def test_anilist_get_validates_the_id_before_any_request() -> None:
    provider, gateway = _al(anilist_media())
    for bad in ("", "abc", "12a", "-1", "1.5", "٣٠", "1" * 11, "1; DROP", " 5"):
        assert provider.get(bad, LANGS) is None
    assert gateway.calls == []


def test_anilist_get_sends_the_id_as_an_integer() -> None:
    gateway = FakeGateway()
    gateway.route("", {"data": {"Media": anilist_media(30002)}})
    candidate = AniListProvider(gateway).get("30002", LANGS)
    assert candidate is not None and candidate.external_id == "30002"
    assert gateway.calls == [("POST", 'graphql.anilist.co {"id": 30002}')]


def test_anilist_a_cover_outside_the_allowlist_is_kept_but_never_fetchable() -> None:
    """The provider passes the URL on; the gateway allowlist is what refuses it (see
    test_safe_gateway and the service tests)."""
    provider, gateway = _al(anilist_media(cover="http://169.254.169.254/x.jpg"))
    [candidate] = provider.search("x", LANGS)
    assert candidate.cover_url == "http://169.254.169.254/x.jpg"
    with pytest.raises(ExternalFetchError) as info:
        gateway.get_image(candidate.cover_url or "")
    assert info.value.reason == "invalid_url"
