"""Fusion of sources, Portuguese-first descriptions and automatic translation, end to end (real
providers, services and routes over a fake HTTP gateway: no network). The main scenario is the
real "Omniscient Reader's Viewpoint" case, whose MangaDex work has NO pt-br description."""

from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from app.domain.errors import ExternalFetchError

from library_env import logged_in, metadata_env, series_id_by_title
from metadata_fakes import (
    AL_ORV_COVER,
    MD_COVER_URL,
    ORV,
    ORV_COVER_URL,
    ORV_EN_TEXT,
    ORV_WORK_ID,
    FakeGateway,
    anilist_media,
    anilist_page,
    fake_translation,
    good_jpeg,
    good_png,
    googlebooks_list,
    googlebooks_volume,
    mangadex_entry,
    mangadex_list,
    mymemory_answer,
    orv_anilist_answer,
    orv_mangadex_answer,
    wikipedia_search_answer,
    wikipedia_summary_answer,
)

MD_PAGE = f"https://mangadex.org/title/{ORV_WORK_ID}"
WIKI_NO_ARTICLE = wikipedia_search_answer(
    ("Chae_Soo-bin", "Chae Soo-bin", "atriz sul-coreana"),
    ("Jisoo", "Jisoo", "cantora e atriz sul-coreana"),
)


def orv_gateway() -> FakeGateway:
    gateway = FakeGateway()
    gateway.route("title=Omniscient", orv_mangadex_answer())
    gateway.route("api.mangadex.org", mangadex_list())
    gateway.route("Omniscient", orv_anilist_answer())
    gateway.route('"search"', anilist_page())
    gateway.route("pt.wikipedia.org/w/rest.php", WIKI_NO_ARTICLE)
    gateway.route("www.googleapis.com", ExternalFetchError("rate_limited"))
    gateway.route("api.mymemory.translated.net", fake_translation)
    gateway.images[ORV_COVER_URL] = good_jpeg(11)
    gateway.images[AL_ORV_COVER] = good_png(2)
    return gateway


def detail(env, title: str = ORV) -> dict[str, object]:  # type: ignore[no-untyped-def]
    alice = logged_in(env)
    return alice.get(f"/api/v1/series/{series_id_by_title(alice, title)}").json()  # type: ignore[no-any-return]


def calls_to(gateway: FakeGateway, host: str) -> list[str]:
    return [u for k, u in gateway.calls if k != "POST" and urlsplit(u).netloc == host]


# ------------------------------------------------------------------ the real ORV case


def test_orv_without_pt_br_anywhere_gets_the_translated_english_synopsis(
    db_url: str, tmp_path: Path
) -> None:
    gateway = orv_gateway()
    env, _ = metadata_env(db_url, tmp_path, gateway)
    status = env.container.enrich_runner.run()
    assert status.matched == 1 and status.errors == 0

    body = detail(env)
    assert body["metadata_state"] == "matched"
    # cover + title source: the MangaDex WORK (4th answer), not the Book Version / doujinshi
    assert body["source"] == {"name": "MangaDex", "url": MD_PAGE}
    assert body["title"] == ORV  # the library's own title is never replaced
    # description: Portuguese by automatic translation, attributed to the ENGLISH original
    assert body["description"] == f"Traducao: {ORV_EN_TEXT}"
    assert body["description_lang"] == "pt-br"
    assert body["description_origin"] == "translated"
    assert body["description_source"] == {"name": "MangaDex", "url": MD_PAGE}

    alice = logged_in(env)
    sid = str(body["id"])
    assert alice.get(f"/api/v1/series/{sid}/cover").content == good_jpeg(11)
    assert [u for k, u in gateway.calls if k == "IMG"] == [ORV_COVER_URL]  # MangaDex .512 first


def test_only_the_public_synopsis_goes_to_the_translation_service(
    db_url: str, tmp_path: Path
) -> None:
    gateway = orv_gateway()
    env, lib = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    sent = calls_to(gateway, "api.mymemory.translated.net")
    assert sent
    for url in sent:
        query = parse_qs(urlsplit(url).query)
        assert set(query) == {"q", "langpair"}  # no `de` (e-mail), no key, nothing else
        assert query["langpair"] == ["en|pt-BR"]
        assert query["q"][0] in ORV_EN_TEXT
        assert len(query["q"][0].encode()) <= 400
        for private in (ORV, str(lib), str(tmp_path), "root", "alice", ".cbz", "@"):
            assert private not in unquote(url)


def test_pt_br_from_the_work_source_stops_everything_else(db_url: str, tmp_path: Path) -> None:
    gateway = orv_gateway()
    work = mangadex_entry(
        ORV_WORK_ID,
        title={"ko-ro": "Jeonjijeok Dokja Sijeom"},
        alt_titles=[{"en": ORV}],
        description={"pt-br": "Sinopse original em portugues.", "en": ORV_EN_TEXT},
        cover_file="5d3f7f0a-1111-4222-8333-444455556666.jpg",
        year=2020,
    )
    gateway.json_routes.insert(0, ("title=Omniscient", mangadex_list(work)))
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    body = detail(env)
    assert body["description"] == "Sinopse original em portugues."
    assert (body["description_lang"], body["description_origin"]) == ("pt-br", "source")
    assert body["description_source"] == {"name": "MangaDex", "url": MD_PAGE}
    hosts = {urlsplit(u).netloc for k, u in gateway.calls if k != "POST"}
    assert hosts == {"api.mangadex.org", "uploads.mangadex.org"}  # nothing else was asked
    assert not [c for c in gateway.calls if c[0] == "POST" and "Omniscient" in c[1]]


def test_the_cover_falls_through_the_sources_in_quality_order(db_url: str, tmp_path: Path) -> None:
    gateway = orv_gateway()
    gateway.images[ORV_COVER_URL] = ExternalFetchError("too_large")  # MangaDex image unusable
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    body = detail(env)
    # AniList's cover is used, so AniList becomes the cover/title source...
    assert body["source"] == {"name": "AniList", "url": "https://anilist.co/manga/119257"}
    assert logged_in(env).get(f"/api/v1/series/{body['id']}/cover").content == good_png(2)
    # ...but the description is still the best one (all sources considered): MangaDex's English
    assert body["description_origin"] == "translated"
    assert body["description_source"] == {"name": "MangaDex", "url": MD_PAGE}


def test_the_editions_alone_are_not_a_match(db_url: str, tmp_path: Path) -> None:
    gateway = orv_gateway()
    answer = orv_mangadex_answer()
    answer["data"] = answer["data"][:3]  # type: ignore[index]  # drop the work: editions only
    gateway.json_routes.insert(0, ("title=Omniscient", answer))
    gateway.json_routes.insert(1, ('"Omniscient', anilist_page()))
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    assert detail(env)["metadata_state"] == "not_found"


# ------------------------------------------------------------------ Portuguese Wikipedia

ARTICLE = "Jeonjijeok Dokja Sijeom é uma web novel sul-coreana adaptada em manhwa."


def wikipedia_gateway(
    *pages: tuple[str, str, str], summary: dict[str, object] | None = None
) -> FakeGateway:
    gateway = orv_gateway()
    gateway.json_routes.insert(0, ("pt.wikipedia.org/w/rest.php", wikipedia_search_answer(*pages)))
    if summary is not None:
        gateway.json_routes.insert(0, ("page/summary/", summary))
    return gateway


def test_a_strong_wikipedia_match_gives_the_pt_description_with_attribution(
    db_url: str, tmp_path: Path
) -> None:
    key = "Omniscient_Reader's_Viewpoint"
    gateway = wikipedia_gateway(
        (key, "Omniscient Reader's Viewpoint", "série de manhwa sul-coreana"),
        summary=wikipedia_summary_answer(
            "Omniscient Reader's Viewpoint", ARTICLE, description="série de manhwa sul-coreana"
        ),
    )
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    body = detail(env)
    assert body["description"] == ARTICLE
    assert (body["description_lang"], body["description_origin"]) == ("pt-br", "source")
    # attribution (CC BY-SA 4.0): the article, with a URL BUILT from the key (never the response's)
    assert body["description_source"] == {
        "name": "Wikipédia",
        "url": "https://pt.wikipedia.org/wiki/Omniscient_Reader%27s_Viewpoint",
    }
    assert body["source"]["name"] == "MangaDex"  # type: ignore[index]  # cover/title unaffected
    assert calls_to(gateway, "api.mymemory.translated.net") == []  # no translation needed
    assert "evil.example" not in str(body)


@pytest.mark.parametrize(
    ("pages", "summary"),
    [
        # a disambiguation page
        (
            [("Omniscient_Reader", "Omniscient Reader", "página de desambiguação")],
            wikipedia_summary_answer("Omniscient Reader", ARTICLE, kind="disambiguation"),
        ),
        # right title, but the article is about something else (no manga/manhwa evidence)
        (
            [("Omniscient_Reader", "Omniscient Reader", "série de televisão americana")],
            wikipedia_summary_answer(
                "Omniscient Reader", "Uma série de televisão americana.", description="série de TV"
            ),
        ),
        # an unrelated title (an actress who starred in the film adaptation)
        (
            [("Jisoo", "Jisoo", "cantora e atriz")],
            wikipedia_summary_answer("Jisoo", "Jisoo é cantora e estrelou o filme do mangá."),
        ),
        # similar but not the same work
        (
            [("Omniscient_Reader_2", "Omniscient Reader Returns", "série de manhwa")],
            wikipedia_summary_answer("Omniscient Reader Returns", ARTICLE),
        ),
    ],
)
def test_a_weak_wikipedia_match_is_never_used(
    db_url: str, tmp_path: Path, pages: list[tuple[str, str, str]], summary: dict[str, object]
) -> None:
    gateway = wikipedia_gateway(*pages, summary=summary)
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    body = detail(env)
    assert body["description_origin"] == "translated"  # fell through to the translation
    assert ARTICLE not in str(body["description"])


# ------------------------------------------------------------------ Google Books

BOOK_TEXT = "<p>A <b>web novel</b> virou <i>realidade</i>.</p>"


def books_gateway(*volumes: dict[str, object]) -> FakeGateway:
    gateway = orv_gateway()
    gateway.json_routes.insert(0, ("www.googleapis.com", googlebooks_list(*volumes)))
    return gateway


def test_a_strong_google_books_match_gives_the_pt_description_with_attribution(
    db_url: str, tmp_path: Path
) -> None:
    gateway = books_gateway(
        googlebooks_volume(
            "abc123", f"{ORV} Vol. 1", BOOK_TEXT, categories=["Comics & Graphic Novels"]
        ),
        googlebooks_volume(
            "abc124", f"{ORV} Vol. 2", "Outro volume.", categories=["Comics & Graphic Novels"]
        ),
    )
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    body = detail(env)
    assert body["description"] == "A web novel virou realidade."  # HTML gone
    assert (body["description_lang"], body["description_origin"]) == ("pt-br", "source")
    assert body["description_source"] == {
        "name": "Google Livros",
        "url": "https://books.google.com/books?id=abc123",  # the first volume of the series
    }


@pytest.mark.parametrize(
    "volume",
    [
        googlebooks_volume("v1", ORV, "Texto.", categories=["Fiction"]),  # not a comic
        googlebooks_volume("v2", ORV, "Texto.", categories=["Comics"], language="en"),
        googlebooks_volume("v3", ORV, None, categories=["Comics"]),  # no description
        googlebooks_volume(
            "v4", ORV, "Texto.", categories=["Comics"], published="1850"
        ),  # predates
        googlebooks_volume("v5", "Outro Titulo Qualquer", "Texto.", categories=["Comics"]),
        googlebooks_volume("v6", f"{ORV} Fanbook", "Texto.", categories=["Comics"]),
        googlebooks_volume("../x", ORV, "Texto.", categories=["Comics"]),  # hostile id
    ],
)
def test_a_weak_google_books_match_is_never_used(
    db_url: str, tmp_path: Path, volume: dict[str, object]
) -> None:
    env, _ = metadata_env(db_url, tmp_path, books_gateway(volume))
    env.container.enrich_runner.run()
    body = detail(env)
    assert body["description_origin"] == "translated"
    assert "Texto." not in str(body["description"])


def test_wikipedia_comes_before_google_books(db_url: str, tmp_path: Path) -> None:
    gateway = wikipedia_gateway(
        ("ORV", ORV, "série de manhwa"),
        summary=wikipedia_summary_answer(ORV, ARTICLE),
    )
    gateway.json_routes.insert(
        0,
        (
            "www.googleapis.com",
            googlebooks_list(googlebooks_volume("abc", ORV, "Livro.", categories=["Comics"])),
        ),
    )
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    assert detail(env)["description_source"]["name"] == "Wikipédia"  # type: ignore[index]
    assert calls_to(gateway, "www.googleapis.com") == []  # not even asked


# ------------------------------------------------------------------ translation limits


def two_series_gateway(translation: object) -> FakeGateway:
    gateway = FakeGateway()
    for name in ("Berserk", "Solo"):
        gateway.route(
            f"title={name}",
            mangadex_list(
                mangadex_entry(
                    title={"en": name}, description={"en": f"{name} synopsis. Second sentence."}
                )
            ),
        )
    gateway.route("api.mangadex.org", mangadex_list())
    gateway.route('"search"', anilist_page())
    gateway.route("api.mymemory.translated.net", translation)
    gateway.images[MD_COVER_URL] = good_jpeg(1)
    return gateway


@pytest.mark.parametrize(
    "answer",
    [
        mymemory_answer("", status=200),  # empty
        mymemory_answer("solo synopsis. second sentence.", match=0.9),  # identical (not translated)
        mymemory_answer("Traduzido", match=0.2),  # weak match: a translation-memory leftover
        mymemory_answer("Traduzido", status=403),
        mymemory_answer("Traduzido", status=429),
        mymemory_answer("x", status=200),  # absurdly short
        mymemory_answer("Traduzido " * 200),  # runaway
        mymemory_answer("<script>alert(1)</script>"),  # markup only: empty once sanitized
        {"unexpected": "shape"},
        {"responseData": "nope", "responseStatus": 200},
        "not even a dict",
        ExternalFetchError("timeout"),
        ExternalFetchError("rate_limited"),
    ],
)
def test_an_untrustworthy_translation_keeps_the_english_original(
    db_url: str, tmp_path: Path, answer: object
) -> None:
    env, _ = metadata_env(db_url, tmp_path, two_series_gateway(answer))
    env.container.enrich_runner.run()
    body = detail(env, "Solo")
    assert body["description"] == "Solo synopsis. Second sentence."
    assert (body["description_lang"], body["description_origin"]) == ("en", "source")
    assert body["description_source"]["name"] == "MangaDex"  # type: ignore[index]


@pytest.mark.parametrize(
    "answer",
    [
        mymemory_answer("Traduzido", quota=True),
        mymemory_answer("MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY."),
        mymemory_answer("Traduzido", status=429),
        ExternalFetchError("rate_limited"),
    ],
)
def test_a_quota_answer_stops_the_translations_for_a_while(
    db_url: str, tmp_path: Path, answer: object
) -> None:
    gateway = two_series_gateway(answer)
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    assert len(calls_to(gateway, "api.mymemory.translated.net")) == 1  # the 2nd series: not asked
    for title in ("Berserk", "Solo"):
        assert detail(env, title)["description_origin"] == "source"  # English kept, flagged so


def test_a_good_translation_is_sanitized_again_and_marked(db_url: str, tmp_path: Path) -> None:
    def hostile(url: str) -> dict[str, object]:
        return mymemory_answer("<b>Sinopse</b> [x](javascript:alert(1)) &lt;script&gt;‮ traduzida.")

    env, _ = metadata_env(db_url, tmp_path, two_series_gateway(hostile))
    env.container.enrich_runner.run()
    body = detail(env, "Solo")
    assert body["description_origin"] == "translated" and body["description_lang"] == "pt-br"
    text = str(body["description"])
    for bad in ("<", ">", "javascript", "](", "‮"):
        assert bad not in text


def test_a_long_synopsis_is_sent_in_small_pieces_and_cut_at_a_sentence(
    db_url: str, tmp_path: Path
) -> None:
    sentence = "This is one sentence of the synopsis that is fairly long. "
    long_text = sentence * 60  # 3500 characters: far above what is worth the daily quota
    gateway = two_series_gateway(fake_translation)
    gateway.json_routes.insert(
        0,
        (
            "title=Solo",
            mangadex_list(mangadex_entry(title={"en": "Solo"}, description={"en": long_text})),
        ),
    )
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    sent = [
        parse_qs(urlsplit(u).query)["q"][0]
        for u in calls_to(gateway, "api.mymemory.translated.net")
    ]
    solo_pieces = [q for q in sent if q.startswith("This is one")]
    assert len(solo_pieces) > 1 and all(len(q.encode()) <= 400 for q in solo_pieces)
    assert sum(len(q) for q in solo_pieces) <= 1500  # at most ~1500 characters leave the server
    body = detail(env, "Solo")
    assert body["description_origin"] == "translated"
    assert str(body["description"]).rstrip().endswith("synopsis that is fairly long.")


def test_translation_can_be_switched_off(db_url: str, tmp_path: Path) -> None:
    gateway = orv_gateway()
    env, _ = metadata_env(db_url, tmp_path, gateway, METADATA_TRANSLATE_ENABLED=False)
    env.container.enrich_runner.run()
    assert calls_to(gateway, "api.mymemory.translated.net") == []
    body = detail(env)
    assert body["description"] == ORV_EN_TEXT
    assert (body["description_lang"], body["description_origin"]) == ("en", "source")


def test_providers_can_be_chosen_and_ordered(db_url: str, tmp_path: Path) -> None:
    gateway = orv_gateway()
    env, _ = metadata_env(
        db_url, tmp_path, gateway, METADATA_PROVIDERS="anilist", METADATA_TRANSLATE_ENABLED=False
    )
    env.container.enrich_runner.run()
    assert {urlsplit(u).netloc for k, u in gateway.calls if k != "POST"} == {"s4.anilist.co"}
    assert detail(env)["source"] == {"name": "AniList", "url": "https://anilist.co/manga/119257"}


# ------------------------------------------------------------------ attribution and manual flows


def test_select_a_description_only_source_keeps_the_cover_and_source(
    db_url: str, tmp_path: Path
) -> None:
    gateway = wikipedia_gateway(
        ("ORV", ORV, "série de manhwa"), summary=wikipedia_summary_answer(ORV, ARTICLE)
    )
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()  # translated description + MangaDex cover
    admin = logged_in(env, "root")
    sid = series_id_by_title(admin, ORV)
    cover_before = admin.get(f"/api/v1/series/{sid}/cover").content
    # the candidates list offers it (a description-only candidate has no cover)
    items = admin.get(f"/api/v1/series/{sid}/metadata/candidates").json()["items"]
    wiki = next(c for c in items if c["provider"] == "wikipedia")
    assert wiki["cover_available"] is False and wiki["url"].startswith("https://pt.wikipedia.org/")
    assert {c["provider"] for c in items} >= {"mangadex", "wikipedia"}

    response = admin.post(
        f"/api/v1/series/{sid}/metadata/select", {"provider": "wikipedia", "external_id": "ORV"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metadata_state"] == "manual" and body["description"] == ARTICLE
    assert body["description_origin"] == "source"
    assert body["description_source"] == {
        "name": "Wikipédia",
        "url": "https://pt.wikipedia.org/wiki/ORV",
    }
    assert body["source"] == {"name": "MangaDex", "url": MD_PAGE}  # cover source untouched
    assert body["cover_downloaded"] is True
    assert admin.get(f"/api/v1/series/{sid}/cover").content == cover_before


def test_manual_edit_marks_the_origin_manual_and_delete_clears_the_attribution(
    db_url: str, tmp_path: Path
) -> None:
    env, _ = metadata_env(db_url, tmp_path, orv_gateway())
    env.container.enrich_runner.run()
    admin = logged_in(env, "root")
    sid = series_id_by_title(admin, ORV)
    only_title = admin.put(f"/api/v1/series/{sid}/metadata", {"title": "ORV"}).json()
    assert (
        only_title["description_origin"] == "translated"
    )  # description untouched: attribution too
    edited = admin.put(f"/api/v1/series/{sid}/metadata", {"description": "Texto do dono."}).json()
    assert edited["description_origin"] == "manual" and edited["description_source"] is None
    assert edited["description_lang"] is None
    emptied = admin.put(f"/api/v1/series/{sid}/metadata", {"description": ""}).json()
    assert emptied["description"] is None and emptied["description_origin"] is None
    cleared = admin.delete(f"/api/v1/series/{sid}/metadata").json()
    assert cleared["description_origin"] is None and cleared["description_source"] is None
    assert cleared["metadata_state"] == "none"


def test_select_a_work_source_resolves_the_description_with_the_same_rules(
    db_url: str, tmp_path: Path
) -> None:
    gateway = orv_gateway()
    work = orv_mangadex_answer()["data"][3]  # type: ignore[index]
    gateway.json_routes.insert(0, (f"/manga/{ORV_WORK_ID}", {"result": "ok", "data": work}))
    env, _ = metadata_env(db_url, tmp_path, gateway)
    admin = logged_in(env, "root")
    sid = series_id_by_title(admin, ORV)
    response = admin.post(
        f"/api/v1/series/{sid}/metadata/select",
        {"provider": "mangadex", "external_id": ORV_WORK_ID},
    )
    body = response.json()
    assert response.status_code == 200 and body["metadata_state"] == "manual"
    assert body["description_origin"] == "translated" and body["description_lang"] == "pt-br"
    assert body["description_source"] == {"name": "MangaDex", "url": MD_PAGE}
    assert env.container.enrich_runner.run(force=True).matched == 0  # manual is never touched


def test_metadata_disabled_builds_no_translator_and_no_describers(
    db_url: str, tmp_path: Path
) -> None:
    gateway = orv_gateway()
    env, _ = metadata_env(db_url, tmp_path, gateway, METADATA_ENABLED=False)
    service = env.container.metadata_service
    assert service._providers == () and service._translator is None  # type: ignore[attr-defined]
    assert gateway.calls == []


def test_the_attribution_names_are_the_known_labels_only(db_url: str, tmp_path: Path) -> None:
    env, _ = metadata_env(db_url, tmp_path, orv_gateway())
    env.container.enrich_runner.run()
    body = detail(env)
    assert {body["source"]["name"], body["description_source"]["name"]} <= {  # type: ignore[index]
        "MangaDex",
        "AniList",
        "Wikipédia",
        "Google Livros",
    }
    for url in (body["source"]["url"], body["description_source"]["url"]):  # type: ignore[index]
        assert url.startswith("https://")


def test_anilist_media_helper_is_the_documented_shape() -> None:
    media = anilist_media()
    assert set(media) == {"id", "title", "synonyms", "description", "startDate", "coverImage"}
