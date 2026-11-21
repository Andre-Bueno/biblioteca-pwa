"""Metadata management API: authorization (anonymous / user / admin), CSRF, strict inputs, generic
errors, the per-user limit on live searches, and the cover precedence. No network: fake gateway."""

from pathlib import Path

import pytest
from app.domain.errors import ExternalFetchError
from sqlalchemy import text

from auth_fakes import ApiClient, Env
from library_env import logged_in, metadata_env, series_id_by_title
from metadata_fakes import (
    AL_COVER_URL,
    MD_COVER_URL,
    MD_ID,
    FakeGateway,
    anilist_media,
    anilist_page,
    good_jpeg,
    good_png,
    mangadex_entry,
    mangadex_list,
)

RESULT_KEYS = {
    "id",
    "title",
    "description",
    "description_lang",
    "description_origin",
    "description_source",
    "source",
    "metadata_state",
    "cover_downloaded",
}
CANDIDATE_KEYS = {
    "provider",
    "external_id",
    "title",
    "year",
    "description",
    "cover_available",
    "url",
}


def gateway_with_many() -> FakeGateway:
    gateway = FakeGateway()
    entries = [
        mangadex_entry(
            f"{i:08d}-0000-4000-8000-000000000000",
            title={"en": f"Berserk {i}"},
            description={"pt-br": "<b>" + "palavra " * 100 + "</b><script>x</script>"},
        )
        for i in range(8)
    ]
    gateway.route("api.mangadex.org/manga?", mangadex_list(*entries))
    gateway.route(
        f"/manga/{MD_ID}",
        {
            "result": "ok",
            "data": mangadex_entry(
                title={"ja-ro": "Berserk"}, description={"pt-br": "Descricao <i>escolhida</i>."}
            ),
        },
    )
    gateway.route(
        '{"id": 30002}',
        {"data": {"Media": anilist_media(30002, cover="http://evil.example/x.jpg")}},
    )
    gateway.route(
        '"', anilist_page(*[anilist_media(100 + i, english=f"Berserk AL {i}") for i in range(8)])
    )
    gateway.images[MD_COVER_URL] = good_jpeg(5)
    gateway.images[AL_COVER_URL] = good_png(5)
    return gateway


def setup(
    db_url: str, tmp_path: Path, gateway: FakeGateway | None = None, **overrides: object
) -> tuple[Env, ApiClient, str]:
    env, _ = metadata_env(db_url, tmp_path, gateway or gateway_with_many(), **overrides)
    admin = logged_in(env, "root")
    return env, admin, series_id_by_title(admin, "Berserk")


def write_calls(sid: str) -> list[tuple[str, str, object]]:
    return [
        (
            "POST",
            f"/api/v1/series/{sid}/metadata/select",
            {"provider": "mangadex", "external_id": MD_ID},
        ),
        ("PUT", f"/api/v1/series/{sid}/metadata", {"title": "X"}),
        ("DELETE", f"/api/v1/series/{sid}/metadata", None),
        ("POST", "/api/v1/library/enrich", None),
    ]


def send(client: ApiClient, method: str, path: str, body: object = None):  # type: ignore[no-untyped-def]
    if method == "GET":
        return client.get(path)
    if method == "POST":
        return client.post(path, body)
    if method == "PUT":
        return client.put(path, body)
    return client.delete(path)


# ------------------------------------------------------------------ authorization


def test_anonymous_gets_401_on_every_metadata_route(db_url: str, tmp_path: Path) -> None:
    env, _, sid = setup(db_url, tmp_path)
    anonymous = env.client()
    calls = write_calls(sid) + [
        ("GET", f"/api/v1/series/{sid}/metadata/candidates", None),
        ("GET", "/api/v1/library/enrich/status", None),
    ]
    for method, path, body in calls:
        assert send(anonymous, method, path, body).status_code == 401, (method, path)
    assert env.container.http_gateway.calls == []  # type: ignore[attr-defined]


def test_a_plain_user_gets_403_and_causes_no_outbound_request(db_url: str, tmp_path: Path) -> None:
    env, _, sid = setup(db_url, tmp_path)
    alice = logged_in(env)
    calls = write_calls(sid) + [
        ("GET", f"/api/v1/series/{sid}/metadata/candidates", None),
        ("GET", "/api/v1/library/enrich/status", None),
    ]
    for method, path, body in calls:
        assert send(alice, method, path, body).status_code == 403, (method, path)
    assert env.container.http_gateway.calls == []  # type: ignore[attr-defined]
    detail = send(alice, "GET", f"/api/v1/series/{sid}")
    assert detail.status_code == 200  # reading is still allowed


def test_an_admin_is_allowed(db_url: str, tmp_path: Path) -> None:
    _, admin, sid = setup(db_url, tmp_path)
    assert admin.get(f"/api/v1/series/{sid}/metadata/candidates").status_code == 200
    assert admin.get("/api/v1/library/enrich/status").status_code == 200
    assert admin.put(f"/api/v1/series/{sid}/metadata", {"title": "Ok"}).status_code == 200


def test_writes_without_the_csrf_token_are_refused(db_url: str, tmp_path: Path) -> None:
    _, admin, sid = setup(db_url, tmp_path)
    for method, path, body in write_calls(sid):
        bare = admin.http.request(method, path, json=body, headers={"Origin": admin.ORIGIN})
        assert bare.status_code == 403, (method, path)
        foreign = admin.http.request(
            method,
            path,
            json=body,
            headers={
                "Origin": "https://evil.example",
                "X-CSRF-Token": admin.cookie("csrf_token") or "",
            },
        )
        assert foreign.status_code == 403, (method, path)


def test_ids_are_validated_and_unknown_series_are_404(db_url: str, tmp_path: Path) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    chapter = admin.get(f"/api/v1/series/{sid}").json()["chapters"][0]["id"]
    for bad in ("not-a-uuid", "11111111-2222-4333-8444-555555555555", chapter, "%2e%2e", "a" * 99):
        for method, path, body in (
            ("GET", f"/api/v1/series/{bad}/metadata/candidates", None),
            (
                "POST",
                f"/api/v1/series/{bad}/metadata/select",
                {"provider": "mangadex", "external_id": MD_ID},
            ),
            ("PUT", f"/api/v1/series/{bad}/metadata", {"title": "X"}),
            ("DELETE", f"/api/v1/series/{bad}/metadata", None),
        ):
            response = send(admin, method, path, body)
            assert response.status_code == 404, (bad, method)
            assert response.json() == {"detail": "Not found"}
    assert env.container.http_gateway.calls == []  # type: ignore[attr-defined]


# ------------------------------------------------------------------ candidates


def test_candidates_are_limited_shaped_and_sanitized(db_url: str, tmp_path: Path) -> None:
    _, admin, sid = setup(db_url, tmp_path)
    response = admin.get(f"/api/v1/series/{sid}/metadata/candidates?q=Berserk")
    assert response.status_code == 200
    items = response.json()["items"]
    assert set(response.json()) == {"items"}
    assert len(items) == 10  # 5 per source, at most 10 in all
    assert all(set(c) == CANDIDATE_KEYS for c in items)
    assert {c["provider"] for c in items} == {"mangadex", "anilist"}
    described = next(c for c in items if c["provider"] == "mangadex")
    assert len(described["description"]) <= 300 and described["description"].startswith("palavra")
    assert (
        "<" not in response.text and "<script" not in response.text and "alert" not in response.text
    )
    assert described["cover_available"] is True
    assert described["url"].startswith("https://mangadex.org/title/")
    assert all(c["url"] is None or c["url"].startswith("https://") for c in items)
    assert "cover_url" not in response.text and "uploads.mangadex.org" not in response.text


def test_candidates_default_to_the_series_title_and_validate_q(db_url: str, tmp_path: Path) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    admin.get(f"/api/v1/series/{sid}/metadata/candidates")
    assert "title=Berserk&" in env.container.http_gateway.calls[0][1]  # type: ignore[attr-defined]
    assert admin.get(f"/api/v1/series/{sid}/metadata/candidates?q={'a' * 100}").status_code == 200
    assert admin.get(f"/api/v1/series/{sid}/metadata/candidates?q={'a' * 101}").status_code == 422
    blank = admin.get(f"/api/v1/series/{sid}/metadata/candidates?q=%20%20")
    assert blank.status_code == 200  # blank means "the series title"


def test_candidates_are_rate_limited_per_user_before_any_request(
    db_url: str, tmp_path: Path
) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    gateway = env.container.http_gateway
    other = logged_in(env, "root2")
    statuses = [
        admin.get(f"/api/v1/series/{sid}/metadata/candidates").status_code for _ in range(11)
    ]
    assert statuses == [200] * 10 + [429]
    blocked = admin.get(f"/api/v1/series/{sid}/metadata/candidates")
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1
    assert blocked.json() == {"detail": "Too many requests. Try again later."}
    calls_when_blocked = len(gateway.calls)  # type: ignore[attr-defined]
    admin.get(f"/api/v1/series/{sid}/metadata/candidates")
    assert len(gateway.calls) == calls_when_blocked  # type: ignore[attr-defined]
    # the limit belongs to the user, not to the address or to everybody
    assert other.get(f"/api/v1/series/{sid}/metadata/candidates").status_code == 200


def test_every_source_down_is_a_generic_502(db_url: str, tmp_path: Path) -> None:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org", ExternalFetchError("network"))
    gateway.route('"', ExternalFetchError("timeout"))
    _, admin, sid = setup(db_url, tmp_path, gateway)
    response = admin.get(f"/api/v1/series/{sid}/metadata/candidates")
    assert response.status_code == 502
    assert response.json() == {"detail": "Metadata source unavailable"}
    for leak in ("mangadex", "anilist", "network", "timeout", "http"):
        assert leak not in response.text.lower().replace("metadata source unavailable", "")


def test_one_source_down_still_returns_the_other(db_url: str, tmp_path: Path) -> None:
    gateway = gateway_with_many()
    gateway.json_routes.insert(0, ("api.mangadex.org/manga?", ExternalFetchError("timeout")))
    _, admin, sid = setup(db_url, tmp_path, gateway)
    items = admin.get(f"/api/v1/series/{sid}/metadata/candidates").json()["items"]
    assert items and {c["provider"] for c in items} == {"anilist"}


# ------------------------------------------------------------------ select


def test_select_saves_description_source_and_cover_as_manual(db_url: str, tmp_path: Path) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    response = admin.post(
        f"/api/v1/series/{sid}/metadata/select", {"provider": "mangadex", "external_id": MD_ID}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == RESULT_KEYS
    assert body["metadata_state"] == "manual" and body["title"] == "Berserk"
    assert body["description"] == "Descricao escolhida." and body["description_lang"] == "pt-br"
    assert body["source"] == {"name": "MangaDex", "url": f"https://mangadex.org/title/{MD_ID}"}
    assert body["cover_downloaded"] is True
    alice = logged_in(env)
    assert alice.get(f"/api/v1/series/{sid}/cover").content == good_jpeg(5)
    covers = env.settings.DATA_DIR / "covers"
    assert [p.name for p in covers.iterdir()] == [f"{sid}.jpg"]
    env.container.enrich_runner.run(force=True)  # an automatic run cannot undo a manual choice
    assert alice.get(f"/api/v1/series/{sid}").json()["description"] == "Descricao escolhida."


def test_select_refetches_by_id_and_never_trusts_the_client(db_url: str, tmp_path: Path) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    gateway = env.container.http_gateway
    admin.post(
        f"/api/v1/series/{sid}/metadata/select", {"provider": "mangadex", "external_id": MD_ID}
    )
    assert [u for k, u in gateway.calls if k == "GET"] == [  # type: ignore[attr-defined]
        f"https://api.mangadex.org/manga/{MD_ID}?includes%5B%5D=cover_art"
    ]


def test_select_with_a_bad_cover_keeps_the_choice_and_drops_the_old_cover(
    db_url: str, tmp_path: Path
) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    admin.post(
        f"/api/v1/series/{sid}/metadata/select", {"provider": "mangadex", "external_id": MD_ID}
    )
    covers = env.settings.DATA_DIR / "covers"
    assert [p.name for p in covers.iterdir()] == [f"{sid}.jpg"]
    second = admin.post(
        f"/api/v1/series/{sid}/metadata/select", {"provider": "anilist", "external_id": "30002"}
    )
    assert second.status_code == 200  # the AniList cover URL is off the allowlist
    assert second.json()["cover_downloaded"] is False
    assert second.json()["source"]["name"] == "AniList"
    assert list(covers.iterdir()) == []  # the cover of the previous choice is gone


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"provider": "mangadex"},
        {"external_id": MD_ID},
        {"provider": "mangadex", "external_id": MD_ID, "cover_url": "https://evil.example/x"},
        {"provider": 5, "external_id": MD_ID},
        {"provider": "mangadex", "external_id": 5},
        {"provider": "", "external_id": MD_ID},
        {"provider": "../etc", "external_id": MD_ID},
        {"provider": "mangadex", "external_id": "../../x"},
        {"provider": "mangadex", "external_id": "a" * 129},
        {"provider": "mangadex", "external_id": "x y"},
        {"provider": "mangadex", "external_id": "https://evil.example/"},
        [],
        "x",
    ],
)
def test_select_rejects_malformed_bodies_with_a_generic_422(
    db_url: str, tmp_path: Path, body: object
) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    response = admin.post(f"/api/v1/series/{sid}/metadata/select", body)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid request"}
    assert env.container.http_gateway.calls == []  # type: ignore[attr-defined]


def test_select_unknown_provider_or_id_is_404(db_url: str, tmp_path: Path) -> None:
    _, admin, sid = setup(db_url, tmp_path)
    path = f"/api/v1/series/{sid}/metadata/select"
    assert admin.post(path, {"provider": "unknown", "external_id": "1"}).status_code == 404
    assert admin.post(path, {"provider": "anilist", "external_id": "abc"}).status_code == 404
    assert (
        admin.post(path, {"provider": "mangadex", "external_id": "not-a-uuid"}).status_code == 404
    )


def test_select_when_the_source_fails_is_a_generic_502_and_changes_nothing(
    db_url: str, tmp_path: Path
) -> None:
    gateway = gateway_with_many()
    gateway.json_routes.insert(0, (f"/manga/{MD_ID}", ExternalFetchError("timeout")))
    _, admin, sid = setup(db_url, tmp_path, gateway)
    response = admin.post(
        f"/api/v1/series/{sid}/metadata/select", {"provider": "mangadex", "external_id": MD_ID}
    )
    assert response.status_code == 502 and response.json() == {
        "detail": "Metadata source unavailable"
    }
    assert admin.get(f"/api/v1/series/{sid}").json()["metadata_state"] == "none"


# ------------------------------------------------------------------ manual edit


def test_manual_edit_changes_the_title_but_not_the_group(db_url: str, tmp_path: Path) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    response = admin.put(
        f"/api/v1/series/{sid}/metadata",
        {"title": "  Berserk <b>Edicao</b> Definitiva  ", "description": "Linha 1\n\n\n\nLinha 2"},
    )
    assert response.status_code == 200 and set(response.json()) == RESULT_KEYS
    body = response.json()
    assert body["metadata_state"] == "manual" and body["description_lang"] is None
    assert body["title"] == "Berserk b Edicao /b Definitiva"  # same rule as a folder name
    assert body["description"] == "Linha 1\n\nLinha 2"
    listed = [s["title"] for s in admin.get("/api/v1/series").json()["items"]]
    assert body["title"] in listed and "Berserk" not in listed
    env.container.scan_runner.run()  # a rescan neither duplicates the series nor resets the title
    again = admin.get("/api/v1/series").json()["items"]
    assert len(again) == 5 and [s["id"] for s in again if s["id"] == sid] == [sid]
    assert admin.get(f"/api/v1/series/{sid}").json()["title"] == body["title"]
    with env.container.session_factory() as session:
        folder = session.execute(
            text("SELECT folder_rel_path FROM series WHERE id = :i"), {"i": sid}
        ).scalar_one()
    assert folder is None  # "Berserk v03.cbz" is a standalone series: the key was never touched


def test_manual_edit_keeps_the_folder_key_of_a_folder_series(db_url: str, tmp_path: Path) -> None:
    env, admin, _ = setup(db_url, tmp_path)
    sid = series_id_by_title(admin, "Mixed Series")
    admin.put(f"/api/v1/series/{sid}/metadata", {"title": "Serie Mista"})
    with env.container.session_factory() as session:
        folder = session.execute(
            text("SELECT folder_rel_path FROM series WHERE id = :i"), {"i": sid}
        ).scalar_one()
    assert folder == "Mixed Series"
    env.container.scan_runner.run()
    assert series_id_by_title(admin, "Serie Mista") == sid  # same series, not a new "Mixed Series"
    assert all(s["title"] != "Mixed Series" for s in admin.get("/api/v1/series").json()["items"])


def test_manual_edit_of_one_field_keeps_the_other(db_url: str, tmp_path: Path) -> None:
    _, admin, sid = setup(db_url, tmp_path)
    admin.put(f"/api/v1/series/{sid}/metadata", {"description": "Primeira"})
    only_title = admin.put(f"/api/v1/series/{sid}/metadata", {"title": "Novo"}).json()
    assert (only_title["title"], only_title["description"]) == ("Novo", "Primeira")
    cleared = admin.put(f"/api/v1/series/{sid}/metadata", {"description": ""}).json()
    assert cleared["description"] is None and cleared["metadata_state"] == "manual"


def test_manual_description_is_always_plain_text(db_url: str, tmp_path: Path) -> None:
    _, admin, sid = setup(db_url, tmp_path)
    hostile = (
        "<script>alert(1)</script><img src=x onerror=alert(1)>[x](javascript:alert(1)) "
        "**b** ‮evil‬ \x00\x07"
    )
    body = admin.put(f"/api/v1/series/{sid}/metadata", {"description": hostile}).json()
    description = body["description"]
    for bad in ("<", ">", "script", "javascript", "](", "**", "‮", "\x00"):
        assert bad not in description
    assert description.startswith("x") and "evil" in description


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": None},
        {"title": None, "description": None},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"description": "x" * 4001},
        {"title": 5},
        {"description": ["a"]},
        {"title": "ok", "state": "matched"},
        {"title": "ok", "cover_path": "../../x"},
        {"title": "ok", "source": {"name": "x"}},
        [],
        "x",
    ],
)
def test_manual_edit_rejects_bad_bodies(db_url: str, tmp_path: Path, body: object) -> None:
    _, admin, sid = setup(db_url, tmp_path)
    response = admin.put(f"/api/v1/series/{sid}/metadata", body)
    assert response.status_code == 422, body
    assert response.json() == {"detail": "Invalid request"}
    assert admin.get(f"/api/v1/series/{sid}").json()["metadata_state"] == "none"


def test_manual_edit_limits_are_inclusive(db_url: str, tmp_path: Path) -> None:
    _, admin, sid = setup(db_url, tmp_path)
    ok = admin.put(
        f"/api/v1/series/{sid}/metadata", {"title": "t" * 200, "description": "d" * 4000}
    )
    assert ok.status_code == 200 and len(ok.json()["description"]) == 4000


def test_a_title_made_only_of_control_characters_is_refused(db_url: str, tmp_path: Path) -> None:
    _, admin, sid = setup(db_url, tmp_path)
    response = admin.put(f"/api/v1/series/{sid}/metadata", {"title": "\x00\x07‮"})
    assert response.status_code == 422


# ------------------------------------------------------------------ clear


def test_delete_clears_metadata_cover_and_source_but_keeps_the_title(
    db_url: str, tmp_path: Path
) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    admin.post(
        f"/api/v1/series/{sid}/metadata/select", {"provider": "mangadex", "external_id": MD_ID}
    )
    admin.put(f"/api/v1/series/{sid}/metadata", {"title": "Meu Titulo"})
    covers = env.settings.DATA_DIR / "covers"
    assert len(list(covers.iterdir())) == 1
    response = admin.delete(f"/api/v1/series/{sid}/metadata")
    assert response.status_code == 200
    assert response.json() == {
        "id": sid,
        "title": "Meu Titulo",
        "description": None,
        "description_lang": None,
        "description_origin": None,
        "description_source": None,
        "source": None,
        "metadata_state": "none",
        "cover_downloaded": False,
    }
    assert list(covers.iterdir()) == []
    alice = logged_in(env)
    cover = alice.get(f"/api/v1/series/{sid}/cover")
    assert cover.status_code == 200 and cover.content != good_jpeg(5)  # the chapter cover again
    status = env.container.enrich_runner.run()  # `none` is eligible for automatic runs again
    assert status.matched + status.not_found >= 1


# ------------------------------------------------------------------ cover precedence and safety


def test_a_missing_or_corrupt_downloaded_cover_falls_back_to_the_chapter(
    db_url: str, tmp_path: Path
) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    admin.post(
        f"/api/v1/series/{sid}/metadata/select", {"provider": "mangadex", "external_id": MD_ID}
    )
    alice = logged_in(env)
    stored = env.settings.DATA_DIR / "covers" / f"{sid}.jpg"
    assert alice.get(f"/api/v1/series/{sid}/cover").content == good_jpeg(5)
    stored.write_bytes(b"<html><script>alert(1)</script></html>")  # replaced by a non-image
    html_cover = alice.get(f"/api/v1/series/{sid}/cover")
    assert html_cover.status_code == 200 and html_cover.headers["content-type"].startswith("image/")
    assert b"script" not in html_cover.content
    stored.unlink()  # gone altogether
    gone = alice.get(f"/api/v1/series/{sid}/cover")
    assert gone.status_code == 200 and gone.content != good_jpeg(5)


def test_a_tampered_cover_path_in_the_database_never_reads_outside_the_covers_folder(
    db_url: str, tmp_path: Path
) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    secret = tmp_path / "secret.png"
    secret.write_bytes(good_png(9))
    covers = env.settings.DATA_DIR / "covers"
    covers.mkdir(parents=True)
    (covers / "plain.png").write_bytes(good_png(8))
    alice = logged_in(env)
    chapter_cover = alice.get(f"/api/v1/series/{sid}/cover").content
    for evil in (
        "../secret.png",
        "..\\secret.png",
        str(secret),
        "plain.png",  # inside the folder but not a `<uuid>.<ext>` name
        f"{sid}.png/../../secret.png",
        f"{sid}.svg",
        "",
    ):
        with env.container.session_factory() as session, session.begin():
            session.execute(
                text("UPDATE series SET cover_path = :p WHERE id = :i"), {"p": evil, "i": sid}
            )
        response = alice.get(f"/api/v1/series/{sid}/cover")
        assert response.status_code == 200, evil
        assert response.content == chapter_cover, evil


def test_an_extra_or_unknown_series_never_exposes_paths_in_errors(
    db_url: str, tmp_path: Path
) -> None:
    env, admin, sid = setup(db_url, tmp_path)
    raw = ""
    for method, path, body in write_calls(sid)[:3]:
        raw += send(admin, method, path.replace(sid, "x" * 36), body).text
    assert str(tmp_path) not in raw and ".cbz" not in raw and "covers" not in raw
