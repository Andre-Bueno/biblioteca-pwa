"""Wikipedia (pt), Google Books and MyMemory adapters over canned answers (no network)."""

from urllib.parse import parse_qs, urlsplit

import pytest
from app.adapters.metadata.googlebooks import GoogleBooksProvider
from app.adapters.metadata.mymemory import QUIET_SECONDS, MyMemoryTranslator
from app.adapters.metadata.wikipedia import WikipediaProvider
from app.domain.errors import ExternalFetchError

from metadata_fakes import (
    FakeGateway,
    googlebooks_list,
    googlebooks_volume,
    mymemory_answer,
    wikipedia_search_answer,
    wikipedia_summary_answer,
)

LANGS = ("pt-br", "pt", "en")
ARTICLE = "Solo Leveling é uma web novel sul-coreana, adaptada como manhwa."


def wiki(
    pages: list[tuple[str, str, str]], summary: object
) -> tuple[WikipediaProvider, FakeGateway]:
    gateway = FakeGateway()
    gateway.route("page/summary/", summary)
    gateway.route("rest.php", wikipedia_search_answer(*pages))
    return WikipediaProvider(gateway), gateway


# ------------------------------------------------------------------ Wikipedia


def test_wikipedia_builds_a_candidate_from_search_and_summary() -> None:
    provider, gateway = wiki(
        [("Solo_Leveling", "Solo Leveling", "série de manhwa sul-coreana")],
        wikipedia_summary_answer(
            "Solo Leveling", ARTICLE, description="série de manhwa sul-coreana"
        ),
    )
    [candidate] = provider.search("Solo Leveling", LANGS)
    assert candidate.provider == "wikipedia" and candidate.external_id == "Solo_Leveling"
    assert candidate.title == "Solo Leveling" and dict(candidate.descriptions) == {"pt-br": ARTICLE}
    assert candidate.cover_url is None
    # URL built from the key: the (hostile) content_urls of the response are ignored
    assert candidate.source_url == "https://pt.wikipedia.org/wiki/Solo_Leveling"
    search_url, summary_url = (u for _, u in gateway.calls)
    assert search_url.startswith(
        "https://pt.wikipedia.org/w/rest.php/v1/search/page?q=Solo+Leveling"
    )
    assert summary_url == "https://pt.wikipedia.org/api/rest_v1/page/summary/Solo_Leveling"


def test_wikipedia_parenthetical_is_kept_as_an_alternative_title() -> None:
    provider, _ = wiki(
        [("Berserk_(mangá)", "Berserk (mangá)", "série de mangá")],
        wikipedia_summary_answer("Berserk (mangá)", "Berserk é um mangá de Kentaro Miura."),
    )
    [candidate] = provider.search("Berserk", LANGS)
    assert candidate.title == "Berserk" and candidate.alt_titles == ("Berserk (mangá)",)
    assert candidate.source_url == "https://pt.wikipedia.org/wiki/Berserk_(mang%C3%A1)"


def test_wikipedia_needs_a_portuguese_language_in_the_configuration() -> None:
    provider, gateway = wiki([("X", "X", "mangá")], wikipedia_summary_answer("X", "mangá"))
    assert provider.search("X", ("en", "es")) == [] and gateway.calls == []
    [candidate] = provider.search("X", ("en", "pt"))
    assert set(candidate.descriptions) == {"pt"}  # filed under the configured Portuguese code


def test_wikipedia_at_most_two_summaries_are_fetched() -> None:
    pages = [(f"Solo_{i}", f"Solo Leveling {i}", "mangá") for i in range(5)]
    provider, gateway = wiki(pages, wikipedia_summary_answer("Solo Leveling", ARTICLE))
    provider.search("Solo Leveling", LANGS)
    assert len(gateway.calls) == 1 + 2


@pytest.mark.parametrize(
    "summary",
    [
        wikipedia_summary_answer("X", ARTICLE, kind="disambiguation"),
        wikipedia_summary_answer("X", ARTICLE, kind="no-extract"),
        wikipedia_summary_answer("X", "", description="mangá"),
        wikipedia_summary_answer("X", "Uma cidade da Suíça.", description="cidade"),  # no evidence
        {"type": "standard"},
        {"type": "standard", "title": 5, "extract": 5},
        "string",
        None,
    ],
)
def test_wikipedia_refuses_pages_that_are_not_clearly_the_work(summary: object) -> None:
    provider, _ = wiki([("X", "X", "mangá")], summary)
    assert provider.search("X", LANGS) == []


@pytest.mark.parametrize(
    "key", ["", "a/b", "a\\b", "a?b", "a#b", "a b", "a%2fb", "<x>", "x" * 201, "a\nb"]
)
def test_wikipedia_rejects_hostile_keys_before_any_request(key: str) -> None:
    provider, gateway = wiki([], wikipedia_summary_answer("X", ARTICLE))
    assert provider.get(key, LANGS) is None
    assert gateway.calls == []
    hostile, gateway2 = wiki([(key, "X", "mangá")], wikipedia_summary_answer("X", ARTICLE))
    assert hostile.search("X", LANGS) == []
    assert len(gateway2.calls) == 1  # only the search; the key never reached a URL


def test_wikipedia_get_does_not_need_the_evidence_but_needs_a_normal_article() -> None:
    provider, _ = wiki(
        [], wikipedia_summary_answer("Qualquer", "Texto sem pistas.", description="x")
    )
    assert provider.get("Qualquer", LANGS) is not None  # the admin chose it
    other, _ = wiki([], wikipedia_summary_answer("Qualquer", "Texto.", kind="disambiguation"))
    assert other.get("Qualquer", LANGS) is None


def test_wikipedia_errors_are_generic() -> None:
    provider, _ = wiki([], ExternalFetchError("timeout"))
    gateway = FakeGateway()
    gateway.route("rest.php", ExternalFetchError("rate_limited"))
    with pytest.raises(ExternalFetchError):
        WikipediaProvider(gateway).search("X", LANGS)
    assert provider.search("X", LANGS) == []


# ------------------------------------------------------------------ Google Books


def books(*volumes: dict[str, object]) -> tuple[GoogleBooksProvider, FakeGateway]:
    gateway = FakeGateway()
    gateway.route("www.googleapis.com/books/v1/volumes", googlebooks_list(*volumes))
    return GoogleBooksProvider(gateway), gateway


def test_googlebooks_query_and_candidate_shape() -> None:
    volume = googlebooks_volume(
        "abc_123-X", "Solo Leveling 1", "<p>Texto</p>", categories=["Comics & Graphic Novels"]
    )
    provider, gateway = books(volume)
    [candidate] = provider.search('Solo "Leveling"', LANGS)
    [(_, url)] = gateway.calls
    query = parse_qs(urlsplit(url).query)
    assert query["q"] == ['intitle:"Solo  Leveling "'] or query["q"][0].startswith('intitle:"Solo')
    assert query["langRestrict"] == ["pt"] and "key" not in query
    assert candidate.provider == "googlebooks" and candidate.external_id == "abc_123-X"
    assert candidate.year == 2020 and candidate.cover_url is None
    assert candidate.source_url == "https://books.google.com/books?id=abc_123-X"
    assert dict(candidate.descriptions) == {"pt-br": "<p>Texto</p>"}  # sanitized later, on use


def test_googlebooks_collapses_volumes_of_one_series() -> None:
    comics = ["Quadrinhos e romances gráficos"]
    provider, _ = books(
        googlebooks_volume("a", "Solo Leveling Vol. 1", "Um.", categories=comics),
        googlebooks_volume("b", "Solo Leveling Vol. 2", "Dois.", categories=comics),
        googlebooks_volume("c", "Outra Obra", "Tres.", categories=comics),
    )
    assert [c.external_id for c in provider.search("Solo Leveling", LANGS)] == ["a", "c"]


@pytest.mark.parametrize(
    "volume",
    [
        googlebooks_volume("a", "T", "Texto.", categories=["Fiction"]),
        googlebooks_volume("a", "T", "Texto.", categories=["Comics"], language="en"),
        googlebooks_volume("a", "T", None, categories=["Comics"]),
        googlebooks_volume("a b", "T", "Texto.", categories=["Comics"]),
        googlebooks_volume("a" * 40, "T", "Texto.", categories=["Comics"]),
        {"id": "a", "volumeInfo": "nope"},
        {"id": 5},
        "x",
    ],
)
def test_googlebooks_filters_what_is_not_a_portuguese_comic_with_text(volume: object) -> None:
    provider, _ = books(volume)  # type: ignore[arg-type]
    assert provider.search("T", LANGS) == []


def test_googlebooks_evidence_may_come_from_the_description_and_years_are_optional() -> None:
    provider, _ = books(
        googlebooks_volume("a", "T", "Um mangá sobre algo.", categories=[], published=None)
    )
    [candidate] = provider.search("T", LANGS)
    assert candidate.year is None


def test_googlebooks_get_validates_the_id_and_skips_the_evidence() -> None:
    provider, gateway = books()
    for bad in ("", "a/b", "a b", "../x", "a" * 40):
        assert provider.get(bad, LANGS) is None
    assert gateway.calls == []
    gateway.route("volumes/vol1", googlebooks_volume("vol1", "T", "Texto.", categories=["Fiction"]))
    gateway.json_routes.reverse()
    candidate = provider.get("vol1", LANGS)
    assert candidate is not None and candidate.external_id == "vol1"


def test_googlebooks_quota_error_is_a_generic_failure() -> None:
    gateway = FakeGateway()
    gateway.route("googleapis", ExternalFetchError("rate_limited"))
    with pytest.raises(ExternalFetchError) as info:
        GoogleBooksProvider(gateway).search("T", LANGS)
    assert info.value.reason == "rate_limited"


# ------------------------------------------------------------------ MyMemory


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def translator(
    answer: object, clock: Clock | None = None
) -> tuple[MyMemoryTranslator, FakeGateway]:
    gateway = FakeGateway()
    gateway.route("api.mymemory.translated.net", answer)
    return MyMemoryTranslator(gateway, clock=clock or Clock()), gateway


def test_mymemory_request_shape_has_no_email_key_or_extra_parameter() -> None:
    tr, gateway = translator(mymemory_answer("Ola, tudo bem com voce?"))
    assert tr.translate("Hello, how are you today?") == "Ola, tudo bem com voce?"
    [(_, url)] = gateway.calls
    parts = urlsplit(url)
    assert (parts.scheme, parts.netloc, parts.path) == (
        "https",
        "api.mymemory.translated.net",
        "/get",
    )
    assert parse_qs(parts.query) == {"q": ["Hello, how are you today?"], "langpair": ["en|pt-BR"]}


def test_mymemory_all_or_nothing_across_pieces() -> None:
    calls = []

    def answer(url: str) -> object:
        calls.append(url)
        if len(calls) == 2:
            return mymemory_answer("", status=200)  # the second piece fails
        return mymemory_answer("T:" + parse_qs(urlsplit(url).query)["q"][0])

    tr, gateway = translator(answer)
    text = ("First part of the text goes here. " * 12) + "\n" + ("Second part is here. " * 12)
    assert tr.translate(text) is None  # never a half-translated synopsis
    assert len(gateway.calls) == 2  # and it stopped asking after the failure


def test_mymemory_joins_the_pieces_in_order() -> None:
    tr, gateway = translator(
        lambda url: mymemory_answer("T:" + parse_qs(urlsplit(url).query)["q"][0])
    )
    text = "One sentence is here. " * 40
    result = tr.translate(text)
    assert result is not None and result.count("T:") == len(gateway.calls) > 1


@pytest.mark.parametrize("n", [0, 1])
def test_mymemory_refuses_empty_input_and_too_many_pieces(n: int) -> None:
    tr, gateway = translator(mymemory_answer("x" * 50))
    assert tr.translate("") is None and tr.translate("  \n ") is None
    assert tr.translate("A sentence that goes on. " * 400) is None  # would need > 8 requests
    assert gateway.calls == []


@pytest.mark.parametrize(
    "answer",
    [
        mymemory_answer("Traducao longa o bastante", quota=True),
        mymemory_answer("Traducao longa o bastante", status=429),
        mymemory_answer("MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY"),
        ExternalFetchError("rate_limited"),
        ExternalFetchError("bad_status"),
    ],
)
def test_mymemory_quota_makes_it_quiet_for_six_hours(answer: object) -> None:
    clock = Clock()
    tr, gateway = translator(answer, clock)
    assert tr.translate("Hello, how are you today?") is None
    assert tr.translate("Hello, how are you today?") is None
    assert len(gateway.calls) == 1  # the quota is not hammered
    clock.now += QUIET_SECONDS + 1
    tr.translate("Hello, how are you today?")
    assert len(gateway.calls) == 2


@pytest.mark.parametrize(
    "answer",
    [
        mymemory_answer("", status=200),
        mymemory_answer("hello, how are you today?"),  # echo of the original
        mymemory_answer("Ola", match=0.1),
        mymemory_answer("Ola, tudo bem com voce?", status=500),
        {"responseData": {"translatedText": 5}, "responseStatus": 200},
        {"responseStatus": 200},
        [],
        None,
        ExternalFetchError("timeout"),
        ExternalFetchError("network"),
    ],
)
def test_mymemory_untrustworthy_answers_give_none_without_going_quiet(answer: object) -> None:
    clock = Clock()
    tr, gateway = translator(answer, clock)
    assert tr.translate("Hello, how are you today?") is None
    tr.translate("Hello, how are you today?")
    assert len(gateway.calls) == 2  # a plain bad answer does not silence it
