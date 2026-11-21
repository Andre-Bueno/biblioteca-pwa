"""Bug: the real series "Omniscient Reader's Viewpoint" was matched only by AniList (English text)
and MangaDex was left out.

Cause: MangaDex answers three EDITIONS first ("(Book Version)", two "(Doujinshi)") whose
alternative titles equal the library title, and the real work (title in romanized Korean, the
library title only as an alternative) 4th. The matcher scored the book edition and the work the
same (0.97), saw a near tie between different works and gave up on the whole source. Editions are
now penalized (unless the searched title asks for one) and real ties are broken by the oldest year.
Also: the work has NO pt-br description, so the English text is machine-translated and marked.
"""

from pathlib import Path

from app.domain.metadata import MetadataCandidate, pick_best

from library_env import logged_in, metadata_env, series_id_by_title
from metadata_fakes import (
    MD_COVER_URL,
    ORV,
    ORV_COVER_URL,
    ORV_WORK_ID,
    FakeGateway,
    anilist_page,
    good_jpeg,
    mangadex_list,
    orv_anilist_answer,
    orv_mangadex_answer,
)


def test_reg_022_the_mangadex_work_wins_over_its_editions(db_url: str, tmp_path: Path) -> None:
    gateway = FakeGateway()
    gateway.route("title=Omniscient", orv_mangadex_answer())
    gateway.route("api.mangadex.org", mangadex_list())
    gateway.route("Omniscient", orv_anilist_answer())
    gateway.route('"search"', anilist_page())
    gateway.images[ORV_COVER_URL] = good_jpeg(3)
    env, _ = metadata_env(db_url, tmp_path, gateway, METADATA_TRANSLATE_ENABLED=False)
    env.container.enrich_runner.run()

    alice = logged_in(env)
    body = alice.get(f"/api/v1/series/{series_id_by_title(alice, ORV)}").json()
    assert body["source"] == {
        "name": "MangaDex",
        "url": f"https://mangadex.org/title/{ORV_WORK_ID}",
    }
    assert alice.get(f"/api/v1/series/{body['id']}/cover").content == good_jpeg(3)
    assert [u for k, u in gateway.calls if k == "IMG"] == [ORV_COVER_URL]
    assert MD_COVER_URL not in str(gateway.calls)


def test_reg_022_matching_on_the_real_answer_structure() -> None:
    entries = orv_mangadex_answer()["data"]
    assert isinstance(entries, list)
    candidates = [
        MetadataCandidate(
            provider="mangadex",
            external_id=str(e["id"]),
            title=next(iter(e["attributes"]["title"].values())),
            alt_titles=tuple(v for alt in e["attributes"]["altTitles"] for v in alt.values()),
            year=e["attributes"]["year"],
        )
        for e in entries
    ]
    chosen = pick_best(ORV, candidates)
    assert chosen is not None and chosen.external_id == ORV_WORK_ID
