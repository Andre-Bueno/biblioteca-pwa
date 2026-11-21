"""Bug: an automatic enrichment run reads a series (state `none`), searches, downloads the cover
and then writes the result. If the admin edited the series by hand in between (state `manual`), a
write that did not look at the CURRENT state would overwrite the manual text and cover.

Cause (what the design must prevent): "read the state, decide, write later". The fix is that the
write is one conditional statement (`UPDATE ... WHERE metadata_state IN (allowed states)`), and the
downloaded cover is only staged until that statement is accepted (then renamed), or discarded.
"""

from pathlib import Path

from library_env import logged_in, metadata_env, series_id_by_title
from metadata_fakes import (
    MD_COVER_URL,
    FakeGateway,
    anilist_page,
    good_jpeg,
    mangadex_entry,
    mangadex_list,
)


def test_reg_021_manual_edit_made_during_a_run_is_not_overwritten(
    db_url: str, tmp_path: Path
) -> None:
    gateway = FakeGateway()
    gateway.route(
        "title=Berserk",
        mangadex_list(mangadex_entry(title={"en": "Berserk"}, description={"pt-br": "Automatica"})),
    )
    gateway.route("api.mangadex.org", mangadex_list())
    gateway.route('"search"', anilist_page())
    gateway.images[MD_COVER_URL] = good_jpeg(4)
    env, _ = metadata_env(db_url, tmp_path, gateway)
    sid = series_id_by_title(logged_in(env), "Berserk")

    fired: list[bool] = []

    def admin_edits_meanwhile() -> None:  # runs after the search, before the write
        if not fired:
            fired.append(True)
            env.container.metadata_service.set_manual(sid, "Titulo do admin", "Texto do admin")

    gateway.on_image.append(admin_edits_meanwhile)
    status = env.container.enrich_runner.run(series_id=sid)

    assert fired == [True]
    assert (status.matched, status.skipped, status.errors) == (0, 1, 0)
    detail = logged_in(env).get(f"/api/v1/series/{sid}").json()
    assert detail["metadata_state"] == "manual"
    assert (detail["title"], detail["description"]) == ("Titulo do admin", "Texto do admin")
    assert detail["source"] is None
    covers = env.settings.DATA_DIR / "covers"
    assert not covers.exists() or list(covers.iterdir()) == []  # staged cover discarded, no leak
