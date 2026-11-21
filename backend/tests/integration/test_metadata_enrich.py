"""Metadata enrichment end to end over a real (temporary) library and database, with the real
providers, services and routes. The only fake is the HTTP gateway: no test touches the network."""

import re
import threading
from pathlib import Path

import pytest
from app import cli
from app.adapters.http.safe_gateway import DisabledGateway
from app.domain.errors import ExternalFetchError, MetadataDisabled
from sqlalchemy import text

from auth_fakes import Env
from library_env import ORV, logged_in, metadata_env, series_id_by_title
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


def berserk_gateway() -> FakeGateway:
    """MangaDex knows only "Berserk" (with a pt-br description); everything else finds nothing."""
    gateway = FakeGateway()
    gateway.route(
        "title=Berserk",
        mangadex_list(
            mangadex_entry(
                title={"ja-ro": "Berserk"},
                description={"en": "English text", "pt-br": "Um guerreiro <b>solitario</b>."},
            )
        ),
    )
    gateway.route("api.mangadex.org", mangadex_list())
    gateway.route('"search"', anilist_page())
    gateway.images[MD_COVER_URL] = good_jpeg(7)
    return gateway


def row(env: Env, series_id: str) -> dict[str, object]:
    with env.container.session_factory() as session:
        found = (
            session.execute(text("SELECT * FROM series WHERE id = :i"), {"i": series_id})
            .mappings()
            .one()
        )
        return dict(found)


def covers_dir(env: Env) -> Path:
    return env.settings.DATA_DIR / "covers"


def cover_files(env: Env) -> list[str]:
    return sorted(p.name for p in covers_dir(env).glob("*")) if covers_dir(env).exists() else []


# ------------------------------------------------------------------ the happy path


def test_enrich_fills_description_cover_and_source(db_url: str, tmp_path: Path) -> None:
    gateway = berserk_gateway()
    env, _ = metadata_env(db_url, tmp_path, gateway)
    alice = logged_in(env)
    berserk = series_id_by_title(alice, "Berserk")

    status = env.container.enrich_runner.run()

    assert (status.state.value, status.matched, status.not_found) == ("finished", 1, 4)
    assert (status.skipped, status.errors) == (0, 0)
    detail = alice.get(f"/api/v1/series/{berserk}").json()
    assert detail["metadata_state"] == "matched"
    assert detail["description"] == "Um guerreiro solitario."  # pt-br wins; HTML gone
    assert detail["description_lang"] == "pt-br"
    assert detail["source"] == {"name": "MangaDex", "url": f"https://mangadex.org/title/{MD_ID}"}
    listed = {s["title"]: s for s in alice.get("/api/v1/series").json()["items"]}
    assert listed["Berserk"]["metadata_state"] == "matched"
    assert listed["Berserk"]["description"] == "Um guerreiro solitario."
    assert listed["Solo"]["metadata_state"] == "not_found" and listed["Solo"]["description"] is None

    cover = alice.get(f"/api/v1/series/{berserk}/cover")
    assert cover.status_code == 200 and cover.content == good_jpeg(7)
    assert cover.headers["content-type"] == "image/jpeg"
    assert cover.headers["cache-control"] == "private, max-age=3600"
    assert cover.headers["x-content-type-options"] == "nosniff"
    assert cover_files(env) == [f"{berserk}.jpg"]  # named by the series uuid, nothing else


def test_only_the_clean_title_leaves_the_server(db_url: str, tmp_path: Path) -> None:
    gateway = berserk_gateway()
    env, lib = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    sent = " ".join(url for _, url in gateway.calls)
    assert "Berserk" in sent and "Solo" in sent
    for secret in (str(lib), str(tmp_path), "series_lib", ".cbz", "alice", "root", "10.0.0.1"):
        assert secret not in sent
    assert set(gateway.hosts_called()) <= {"api.mangadex.org", "uploads.mangadex.org"}
    posted = [u for k, u in gateway.calls if k == "POST"]
    assert posted and all(u.startswith("graphql.anilist.co {") for u in posted)


def test_responses_never_carry_a_remote_url_or_a_local_path(db_url: str, tmp_path: Path) -> None:
    env, lib = metadata_env(db_url, tmp_path, berserk_gateway())
    env.container.enrich_runner.run()
    alice = logged_in(env)
    sid = series_id_by_title(alice, "Berserk")
    raw = alice.get("/api/v1/series").text + alice.get(f"/api/v1/series/{sid}").text
    for forbidden in (
        "cover_path",
        "uploads.mangadex.org",
        ".jpg",
        "covers",
        str(env.settings.DATA_DIR),
        str(tmp_path),
        str(lib),
        "folder_rel_path",
        "http://",
        "title_original",
        "metadata_checked_at",
    ):
        assert forbidden not in raw, forbidden
    # only https URLs, and only the source page
    urls = set(re.findall(r"https://[^\"]+", raw))
    assert urls == {f"https://mangadex.org/title/{MD_ID}"}  # the source page, nothing else


def test_cover_is_written_once_atomically_and_after_the_stage(
    db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Order: temporary file first (invisible), database change, then the atomic rename."""
    gateway = berserk_gateway()
    env, _ = metadata_env(db_url, tmp_path, gateway)
    repo = env.container.series_repository
    original = repo.update_metadata
    seen: list[tuple[list[str], str]] = []

    def spy(series_id: str, update: object, allowed: object) -> bool:
        if getattr(update, "cover_path", None):
            seen.append((cover_files(env), str(update.cover_path)))  # type: ignore[attr-defined]
        return original(series_id, update, allowed)  # type: ignore[arg-type]

    monkeypatch.setattr(repo, "update_metadata", spy)
    env.container.enrich_runner.run()
    [(during, final_name)] = seen
    assert len(during) == 1 and during[0].startswith(".") and during[0].endswith(".tmp")
    assert final_name not in during  # not visible under its final name yet
    assert cover_files(env) == [final_name]  # renamed afterwards; no temporary file is left
    assert [u for k, u in gateway.calls if k == "IMG"] == [MD_COVER_URL]  # downloaded once


def test_covers_are_named_only_by_the_series_uuid(db_url: str, tmp_path: Path) -> None:
    gateway = FakeGateway()
    hostile = mangadex_entry(title={"en": "Berserk"}, description={"en": "x"})
    hostile["id"] = MD_ID
    gateway.route("api.mangadex.org", mangadex_list(hostile))
    gateway.route('"search"', anilist_page())
    gateway.images[MD_COVER_URL] = good_png(3)
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    sid = series_id_by_title(logged_in(env), "Berserk")
    assert cover_files(env) == [f"{sid}.png"]  # extension from the magic bytes, not the .jpg URL
    assert row(env, sid)["cover_path"] == f"{sid}.png"  # relative, never absolute
    assert MD_ID not in cover_files(env)[0]


# ------------------------------------------------------------------ policy


def test_not_found_is_retried_only_after_a_week_or_when_forced(db_url: str, tmp_path: Path) -> None:
    gateway = berserk_gateway()
    env, _ = metadata_env(db_url, tmp_path, gateway)
    first = env.container.enrich_runner.run()
    assert (first.matched, first.not_found) == (1, 4)
    calls = len(gateway.calls)

    second = env.container.enrich_runner.run()  # nothing is due: no work, no requests
    assert (second.matched, second.not_found, second.skipped) == (0, 0, 0)
    assert len(gateway.calls) == calls

    env.clock.advance(6 * 86400)
    assert env.container.enrich_runner.run().not_found == 0
    env.clock.advance(2 * 86400)  # now more than 7 days
    third = env.container.enrich_runner.run()
    assert third.not_found == 4 and third.matched == 0
    assert len(gateway.calls) > calls

    before = len(gateway.calls)
    forced = env.container.enrich_runner.run(force=True)  # re-checks right away (matched too)
    assert forced.matched == 1 and forced.not_found == 4
    assert len(gateway.calls) > before


def test_a_run_is_bounded_by_metadata_max_per_run(db_url: str, tmp_path: Path) -> None:
    gateway = berserk_gateway()
    env, _ = metadata_env(db_url, tmp_path, gateway, METADATA_MAX_PER_RUN=2)
    first = env.container.enrich_runner.run()
    assert first.matched + first.not_found == 2
    assert len([1 for k, _ in gateway.calls if k == "GET"]) <= 2
    total = first.matched + first.not_found
    for _ in range(4):
        total += (r := env.container.enrich_runner.run()).matched + r.not_found
    assert total == 5  # each series was visited once, 2 per run, never twice


def test_one_search_and_one_download_per_series(db_url: str, tmp_path: Path) -> None:
    gateway = berserk_gateway()
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    kinds = [k for k, _ in gateway.calls]
    assert kinds.count("IMG") == 1
    assert kinds.count("GET") == 5  # one MangaDex search per series
    assert kinds.count("POST") == 4  # AniList only where MangaDex found nothing


def test_language_priority_and_fallbacks(db_url: str, tmp_path: Path) -> None:
    cases = {
        "pt": ({"en": "English", "pt": "Portugues"}, "Portugues", "pt"),
        "en": ({"en": "English", "ru": "Russo"}, "English", "en"),
        "none": ({"ru": "Russo", "ja": "Japones"}, None, None),
    }
    for name, (descs, text_, lang) in cases.items():
        gateway = FakeGateway()
        gateway.route(
            "title=Berserk",
            mangadex_list(mangadex_entry(title={"en": "Berserk"}, description=descs)),
        )
        gateway.route("api.mangadex.org", mangadex_list())
        gateway.route('"search"', anilist_page())
        gateway.images[MD_COVER_URL] = good_jpeg()
        sub = tmp_path / name
        sub.mkdir()
        env, _ = metadata_env(f"{db_url}-{name}", sub, gateway)
        env.container.enrich_runner.run()
        alice = logged_in(env)
        detail = alice.get(f"/api/v1/series/{series_id_by_title(alice, 'Berserk')}").json()
        assert (detail["description"], detail["description_lang"]) == (text_, lang), name
        assert detail["metadata_state"] == "matched"  # a match without description is still a match


def test_anilist_is_the_fallback_with_an_english_description(db_url: str, tmp_path: Path) -> None:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org", mangadex_list())
    gateway.route(
        '"Berserk"', anilist_page(anilist_media(30002, description="A <b>dark</b> tale."))
    )
    gateway.route('"search"', anilist_page())
    gateway.images[AL_COVER_URL] = good_png(1)
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    alice = logged_in(env)
    sid = series_id_by_title(alice, "Berserk")
    detail = alice.get(f"/api/v1/series/{sid}").json()
    assert detail["description"] == "A dark tale." and detail["description_lang"] == "en"
    assert detail["source"] == {"name": "AniList", "url": "https://anilist.co/manga/30002"}
    assert alice.get(f"/api/v1/series/{sid}/cover").content == good_png(1)


def test_below_threshold_and_edition_only_matches_become_not_found(
    db_url: str, tmp_path: Path
) -> None:
    gateway = FakeGateway()
    gateway.route(
        "title=Berserk", mangadex_list(mangadex_entry(title={"en": "Berserk Origins Anthology"}))
    )  # an edition, not the work
    gateway.route(
        "title=Solo", mangadex_list(mangadex_entry(title={"en": "Solo Leveling Ragnarok"}))
    )  # close but not the same
    gateway.route("api.mangadex.org", mangadex_list())
    gateway.route('"search"', anilist_page())
    env, _ = metadata_env(db_url, tmp_path, gateway)
    status = env.container.enrich_runner.run()
    assert (status.matched, status.not_found) == (0, 5)
    alice = logged_in(env)
    states = {s["title"]: s["metadata_state"] for s in alice.get("/api/v1/series").json()["items"]}
    assert set(states.values()) == {"not_found"}
    assert cover_files(env) == []


# ------------------------------------------------------------------ failures never break anything


def test_a_failing_source_falls_through_and_never_breaks_the_scan(
    db_url: str, tmp_path: Path
) -> None:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org", ExternalFetchError("timeout"))
    gateway.route('"Berserk"', anilist_page(anilist_media(30002)))
    gateway.route('"search"', anilist_page())
    gateway.images[AL_COVER_URL] = good_png(2)
    env, lib = metadata_env(db_url, tmp_path, gateway)
    status = env.container.enrich_runner.run()
    assert (status.matched, status.not_found, status.errors) == (1, 4, 0)  # AniList answered
    assert env.container.scan_runner.run().state.value == "finished"  # the scan is unaffected


def test_every_source_down_counts_errors_and_changes_nothing(db_url: str, tmp_path: Path) -> None:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org", ExternalFetchError("network"))
    gateway.route('"search"', ExternalFetchError("timeout"))
    env, _ = metadata_env(db_url, tmp_path, gateway)
    status = env.container.enrich_runner.run()
    assert (status.state.value, status.errors, status.matched, status.not_found) == (
        "finished",
        5,
        0,
        0,
    )
    alice = logged_in(env)
    items = alice.get("/api/v1/series").json()["items"]
    assert {s["metadata_state"] for s in items} == {"none"}  # retried on the next run
    assert env.container.scan_runner.run().state.value == "finished"


def test_an_unexpected_provider_bug_is_contained(
    db_url: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class Boom(FakeGateway):
        def get_json(self, url: str) -> object:
            raise RuntimeError("secret detail https://evil.example/token")

    env, _ = metadata_env(db_url, tmp_path, Boom())
    with caplog.at_level("DEBUG"):
        status = env.container.enrich_runner.run()
    assert status.state.value == "finished" and status.errors == 5
    assert "secret detail" not in caplog.text and "evil.example" not in caplog.text


@pytest.mark.parametrize(
    "cover_url",
    [
        "http://s4.anilist.co/x.jpg",  # not https
        "https://169.254.169.254/latest/meta-data/",  # IP literal
        "https://s4.anilist.co@evil.example/x.jpg",  # userinfo
        "https://evil.example/x.jpg",  # host outside the allowlist
        "https://s4.anilist.co:8443/x.jpg",  # port
        "file:///etc/passwd",
    ],
)
def test_a_hostile_cover_url_is_refused_and_the_match_is_kept_without_cover(
    db_url: str, tmp_path: Path, cover_url: str
) -> None:
    gateway = FakeGateway()
    gateway.route("api.mangadex.org", mangadex_list())
    gateway.route('"Berserk"', anilist_page(anilist_media(30002, cover=cover_url)))
    gateway.route('"search"', anilist_page())
    gateway.images[cover_url] = good_png()  # even if "served", the URL policy comes first
    env, _ = metadata_env(db_url, tmp_path, gateway)
    status = env.container.enrich_runner.run()
    assert status.matched == 1 and status.errors == 0
    alice = logged_in(env)
    sid = series_id_by_title(alice, "Berserk")
    assert row(env, sid)["cover_path"] is None and cover_files(env) == []
    assert alice.get(f"/api/v1/series/{sid}/cover").status_code == 200  # chapter cover instead
    assert [k for k, _ in gateway.calls if k == "IMG"] == []  # nothing was ever requested


@pytest.mark.parametrize(
    "payload",
    [
        b"<html><script>alert(1)</script></html>",
        good_jpeg() + b"<script>alert(1)</script>",
        ExternalFetchError("too_large"),
        ExternalFetchError("redirect"),
        ExternalFetchError("bad_content_type"),
    ],
)
def test_a_bad_cover_download_leaves_no_file_and_keeps_the_match(
    db_url: str, tmp_path: Path, payload: bytes | Exception
) -> None:
    gateway = berserk_gateway()
    gateway.images[MD_COVER_URL] = payload
    env, _ = metadata_env(db_url, tmp_path, gateway)
    assert env.container.enrich_runner.run().matched == 1
    assert cover_files(env) == []
    alice = logged_in(env)
    assert (
        alice.get(f"/api/v1/series/{series_id_by_title(alice, 'Berserk')}/cover").status_code == 200
    )


# ------------------------------------------------------------------ manual state is sacred


def test_manual_is_never_overwritten_by_automatic_enrichment(db_url: str, tmp_path: Path) -> None:
    gateway = berserk_gateway()
    env, _ = metadata_env(db_url, tmp_path, gateway)
    admin = logged_in(env, "root")
    sid = series_id_by_title(admin, "Berserk")
    edited = admin.put(f"/api/v1/series/{sid}/metadata", {"description": "Minha descricao"})
    assert edited.status_code == 200 and edited.json()["metadata_state"] == "manual"

    for force in (False, True):
        env.container.enrich_runner.run(force=force)
    resp = admin.post("/api/v1/library/enrich?force=true")
    assert resp.status_code == 202
    env.container.enrich_runner.wait(10)

    detail = admin.get(f"/api/v1/series/{sid}").json()
    assert detail["metadata_state"] == "manual" and detail["description"] == "Minha descricao"
    assert detail["source"] is None and cover_files(env) == []
    assert not any("title=Berserk" in u for _, u in gateway.calls)  # not even searched


def test_a_single_series_run_skips_a_manual_one(db_url: str, tmp_path: Path) -> None:
    env, _ = metadata_env(db_url, tmp_path, berserk_gateway())
    admin = logged_in(env, "root")
    sid = series_id_by_title(admin, "Berserk")
    admin.put(f"/api/v1/series/{sid}/metadata", {"title": "Meu Berserk"})
    status = env.container.enrich_runner.run(force=True, series_id=sid)
    assert (status.matched, status.skipped) == (0, 1)


def test_force_does_not_downgrade_a_good_match_that_stops_matching(
    db_url: str, tmp_path: Path
) -> None:
    gateway = berserk_gateway()
    env, _ = metadata_env(db_url, tmp_path, gateway)
    env.container.enrich_runner.run()
    gateway.json_routes.insert(0, ("title=Berserk", mangadex_list()))  # the source lost it
    env.container.enrich_runner.run(force=True)
    alice = logged_in(env)
    detail = alice.get(f"/api/v1/series/{series_id_by_title(alice, 'Berserk')}").json()
    assert detail["metadata_state"] == "matched" and detail["description"]


# ------------------------------------------------------------------ switched off


def test_disabled_opens_no_socket_and_refuses_every_external_action(
    db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import http.client
    import socket
    import ssl

    touched: list[str] = []

    def trap(name: str) -> object:
        def inner(*_a: object, **_k: object) -> None:
            touched.append(name)
            raise OSError("network is off in tests")

        return inner

    monkeypatch.setattr(socket, "create_connection", trap("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", trap("getaddrinfo"))
    monkeypatch.setattr(http.client.HTTPConnection, "connect", trap("connect"))
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", trap("wrap_socket"))

    env, _ = metadata_env(db_url, tmp_path, None, METADATA_ENABLED=False)
    assert isinstance(env.container.http_gateway, DisabledGateway)
    admin = logged_in(env, "root")
    sid = series_id_by_title(admin, ORV)

    assert admin.post("/api/v1/library/enrich").status_code == 503
    assert admin.get(f"/api/v1/series/{sid}/metadata/candidates").status_code == 503
    selected = admin.post(
        f"/api/v1/series/{sid}/metadata/select", {"provider": "mangadex", "external_id": MD_ID}
    )
    assert selected.status_code == 503
    with pytest.raises(MetadataDisabled):
        env.container.metadata_service.require_enabled()
    assert env.container.enrich_runner.run().state.value == "failed"  # contained, no socket
    monkeypatch.setattr(cli, "build_container", lambda: env.container)
    assert cli.main(["enrich"]) == 1
    assert "disabled" in capsys.readouterr().err

    # Manual editing needs no network and keeps working.
    assert admin.put(f"/api/v1/series/{sid}/metadata", {"title": "Manual"}).status_code == 200
    assert admin.delete(f"/api/v1/series/{sid}/metadata").status_code == 200
    assert env.container.scan_runner.run().state.value == "finished"
    assert touched == []


def test_default_gateway_is_lazy_and_never_built_at_startup(
    db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    touched: list[str] = []
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *a, **k: touched.append("x") or (_ for _ in ()).throw(OSError()),
    )
    env, _ = metadata_env(db_url, tmp_path, None)
    alice = logged_in(env)
    assert alice.get("/api/v1/series").status_code == 200  # browsing never reaches out
    assert touched == []


# ------------------------------------------------------------------ concurrency


def test_a_second_enrich_while_one_runs_is_409(db_url: str, tmp_path: Path) -> None:
    class Blocking(FakeGateway):
        def __init__(self) -> None:
            super().__init__()
            self.entered = threading.Event()
            self.release = threading.Event()

        def get_json(self, url: str) -> object:
            self.entered.set()
            self.release.wait(10)
            return super().get_json(url)

    gateway = Blocking()
    gateway.route("api.mangadex.org", mangadex_list())
    gateway.route('"search"', anilist_page())
    env, _ = metadata_env(db_url, tmp_path, gateway)
    admin = logged_in(env, "root")
    first = admin.post("/api/v1/library/enrich")
    assert first.status_code == 202 and first.json()["state"] == "running"
    assert gateway.entered.wait(10)
    second = admin.post("/api/v1/library/enrich")
    assert second.status_code == 409
    assert second.json() == {"detail": "An enrichment is already running"}
    assert admin.get("/api/v1/library/enrich/status").json()["state"] == "running"
    gateway.release.set()
    assert env.container.enrich_runner.wait(15)
    done = admin.get("/api/v1/library/enrich/status").json()
    assert done["state"] == "finished" and done["not_found"] == 5
    assert set(done) == {
        "state",
        "started_at",
        "finished_at",
        "matched",
        "not_found",
        "skipped",
        "errors",
    }
    assert admin.post("/api/v1/library/enrich").status_code == 202  # free again


def test_the_lock_is_released_when_the_job_crashes(db_url: str, tmp_path: Path) -> None:
    env, _ = metadata_env(db_url, tmp_path, FakeGateway())
    runner = env.container.enrich_runner

    def broken(force: bool, series_id: str | None) -> object:
        raise RuntimeError("boom with https://evil.example")

    runner._job = broken  # type: ignore[assignment,attr-defined]
    assert runner.run().state.value == "failed"
    assert runner.run().state.value == "failed"  # not stuck "running", not "already running"


# ------------------------------------------------------------------ CLI


def test_cli_enrich_runs_and_prints_counts_only(
    db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env, _ = metadata_env(db_url, tmp_path, berserk_gateway())
    monkeypatch.setattr(cli, "build_container", lambda: env.container)
    assert cli.main(["enrich"]) == 0
    out = capsys.readouterr().out
    assert out.strip() == "enrich finished: matched=1 not_found=4 skipped=0 errors=0"
    assert "Berserk" not in out and str(tmp_path) not in out


def test_cli_enrich_single_series_force_and_bad_id(
    db_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env, _ = metadata_env(db_url, tmp_path, berserk_gateway())
    monkeypatch.setattr(cli, "build_container", lambda: env.container)
    sid = series_id_by_title(logged_in(env), "Berserk")
    assert cli.main(["enrich", "--series", sid]) == 0
    assert "matched=1" in capsys.readouterr().out
    assert cli.main(["enrich", "--series", sid]) == 0  # matched is not eligible without --force
    assert "skipped=1" in capsys.readouterr().out
    assert cli.main(["enrich", "--series", sid, "--force"]) == 0
    assert "matched=1" in capsys.readouterr().out
    assert cli.main(["enrich", "--series", "../../etc/passwd"]) == 1
    assert cli.main(["enrich", "--series", "11111111-2222-4333-8444-555555555555"]) == 1
    assert "not found" in capsys.readouterr().err
