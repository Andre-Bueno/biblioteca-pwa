"""Release rules: strict semantic versions, ordering, defensive reading of GitHub's release JSON."""

from datetime import UTC, datetime

import pytest
from app.domain.release import (
    is_operator_network,
    parse_app_version,
    parse_release,
    parse_tag,
    valid_repository,
)

REPO = "Andre-Bueno/biblioteca-pwa"


def release_json(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "tag_name": "v1.2.3",
        "name": "Version 1.2.3",
        "body": "## Changes\n- one\n- two",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-11-21T12:00:00Z",
        "html_url": f"https://github.com/{REPO}/releases/tag/v1.2.3",
    }
    return base | over


# ---------------------------------------------------------------- semver


def v(tag: str):  # type: ignore[no-untyped-def]
    version = parse_tag(tag)
    assert version is not None, tag
    return version


def test_ordering_follows_semver() -> None:
    ordered = [
        "v0.0.1",
        "v0.1.0",
        "v0.9.9",
        "v1.0.0-alpha",
        "v1.0.0-alpha.1",
        "v1.0.0-alpha.beta",
        "v1.0.0-beta",
        "v1.0.0-beta.2",
        "v1.0.0-beta.11",
        "v1.0.0-rc.1",
        "v1.0.0",
        "v1.0.1",
        "v1.1.0",
        "v2.0.0",
        "v10.0.0",
    ]
    for lower, higher in zip(ordered, ordered[1:], strict=False):
        assert v(lower) < v(higher), (lower, higher)
        assert v(higher) > v(lower)
        assert not v(higher) < v(lower)


def test_numbers_compare_as_numbers_not_text() -> None:
    assert v("v1.9.0") < v("v1.10.0") < v("v1.10.1")
    assert v("v1.0.0-rc.2") < v("v1.0.0-rc.10")


def test_a_prerelease_is_below_its_release_and_equal_versions_are_not_ordered() -> None:
    assert v("v2.0.0-rc.1") < v("v2.0.0")
    assert not v("v2.0.0") < v("v2.0.0") and not v("v2.0.0") > v("v2.0.0")
    assert v("v1.0.0").text() == "1.0.0" and v("v1.0.0-rc.1").text() == "1.0.0-rc.1"


@pytest.mark.parametrize(
    "tag",
    [
        "1.2.3",  # no v
        "V1.2.3",
        "v1.2",
        "v1",
        "v1.2.3.4",
        "v1.2.x",
        "v01.2.3" + "9" * 20,  # absurd number
        "v1.2.3-",
        "v1.2.3-a..b",
        "v1.2.3-é",
        "v1.2.3+build",
        "v1.2.3\n",
        " v1.2.3",
        "v1.2.3 ",
        "v١.٢.٣",  # non-ASCII digits
        "v1.2.3-" + "a" * 60,
        "",
        "latest",
        "v-1.2.3",
    ],
)
def test_invalid_tags(tag: str) -> None:
    assert parse_tag(tag) is None


@pytest.mark.parametrize("value", [None, 1, 1.5, [], {}, b"v1.2.3"])
def test_non_text_tags(value: object) -> None:
    assert parse_tag(value) is None


def test_app_version_dev_and_odd_values_are_unknown() -> None:
    assert parse_app_version("1.2.3") == parse_tag("v1.2.3")
    assert parse_app_version("v1.2.3") == parse_tag("v1.2.3")
    assert parse_app_version(" 1.2.3-rc.1 ") == parse_tag("v1.2.3-rc.1")
    for odd in ("dev", "", "latest", "1.2", "vv1.2.3", "1.2.3; rm -rf /", "main"):
        assert parse_app_version(odd) is None


def test_repository_names() -> None:
    assert valid_repository("Andre-Bueno/biblioteca-pwa") and valid_repository("a_b.c/d-e.f")
    for bad in ("", "x", "a/b/c", "a b/c", "a/b;c", "../x", "a/" + "b" * 101, "/b", "a/"):
        assert not valid_repository(bad)


# ---------------------------------------------------------------- release document


def test_a_good_release_is_read() -> None:
    release = parse_release(release_json(), REPO)
    assert release is not None
    assert (release.tag, release.name) == ("v1.2.3", "Version 1.2.3")
    assert release.notes == "Changes\n- one\n- two" or "one" in release.notes
    assert release.published_at == datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    assert release.url == f"https://github.com/{REPO}/releases/tag/v1.2.3"
    assert release.version == parse_tag("v1.2.3")


@pytest.mark.parametrize(
    "over",
    [
        {"draft": True},
        {"prerelease": True},
        {"draft": None},
        {"prerelease": "false"},
        {"tag_name": "1.2.3"},
        {"tag_name": "v1.2"},
        {"tag_name": "v1.2.3-rc.1"},  # a pre-release by tag even if the flag says otherwise
        {"tag_name": None},
        {"tag_name": 5},
        {"published_at": "not a date"},
        {"published_at": "2026-11-21T12:00:00"},  # no zone
        {"published_at": None},
        {"published_at": "2026-11-21T12:00:00Z" + "0" * 50},
    ],
)
def test_unusable_releases_are_ignored(over: dict[str, object]) -> None:
    assert parse_release(release_json(**over), REPO) is None


@pytest.mark.parametrize("payload", [None, [], "release", 5, [release_json()]])
def test_a_document_that_is_not_an_object(payload: object) -> None:
    assert parse_release(payload, REPO) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/Andre-Bueno/biblioteca-pwa/releases/tag/v1.2.3",
        "https://github.com.evil.example/Andre-Bueno/biblioteca-pwa/releases/tag/v1.2.3",
        "https://github.com/Other/repo/releases/tag/v1.2.3",
        "https://github.com/Andre-Bueno/biblioteca-pwa-evil/releases/tag/v1.2.3",
        "http://github.com/Andre-Bueno/biblioteca-pwa/releases/tag/v1.2.3",
        "javascript:alert(1)",
        "https://github.com/Andre-Bueno/biblioteca-pwa/issues/1",
        "https://user@github.com/Andre-Bueno/biblioteca-pwa/releases/x",
        "https://github.com/Andre-Bueno/biblioteca-pwa/releases/ x",
        "https://github.com/Andre-Bueno/biblioteca-pwa/releases/" + "a" * 400,
        None,
        5,
    ],
)
def test_html_url_outside_the_repository_is_dropped_but_the_release_stays(url: object) -> None:
    release = parse_release(release_json(html_url=url), REPO)
    assert release is not None and release.url is None


def test_html_url_is_compared_case_insensitively() -> None:
    url = f"https://github.com/{REPO.lower()}/releases/tag/v1.2.3"
    release = parse_release(release_json(html_url=url), REPO)
    assert release is not None and release.url == url


def test_notes_and_name_become_plain_text() -> None:
    body = (
        "<script>alert(1)</script><b>bold</b> [link](http://evil.example/x) "
        "![img](http://evil.example/p.png)‮ hidden\x00 <img src=x onerror=alert(1)>"
        " &lt;i&gt;x&lt;/i&gt;\n\n\n\n**strong**"
    )
    name = "<b>Rel</b>‮\x1b[31m ease\n2 <script>x</script>"
    release = parse_release(release_json(body=body, name=name), REPO)
    assert release is not None
    for text in (release.notes, release.name):
        assert "<" not in text and ">" not in text
        assert "‮" not in text and "\x00" not in text and "\x1b" not in text
        assert "alert" not in text or "script" not in text
    assert "http://evil" not in release.notes
    assert "bold" in release.notes and "link" in release.notes and "strong" in release.notes


def test_sizes_are_capped() -> None:
    release = parse_release(release_json(body="x" * 50_000, name="n" * 1000), REPO)
    assert release is not None
    assert len(release.notes) <= 4000 and len(release.name) <= 200


def test_missing_name_and_body_fall_back() -> None:
    release = parse_release(release_json(name=None, body=None), REPO)
    assert release is not None and release.name == "v1.2.3" and release.notes == ""
    blank = parse_release(release_json(name="   ", body=5), REPO)
    assert blank is not None and blank.name == "v1.2.3" and blank.notes == ""


# ---------------------------------------------------------------- operator networks


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.1.2.3",
        "::1",
        "10.0.0.5",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.10",
        "100.64.0.1",
        "100.100.100.100",
        "100.127.255.255",
        "fd00::1",
        "::ffff:127.0.0.1",
        "::ffff:10.1.2.3",
    ],
)
def test_operator_networks_are_accepted(address: str) -> None:
    assert is_operator_network(address)


@pytest.mark.parametrize(
    "address",
    [
        "8.8.8.8",
        "1.1.1.1",
        "100.63.255.255",
        "100.128.0.0",
        "172.32.0.1",
        "169.254.169.254",  # cloud metadata
        "fe80::1",
        "0.0.0.0",  # noqa: S104
        "::",
        "224.0.0.1",
        "240.0.0.1",
        "2606:4700::1111",
        "::ffff:8.8.8.8",
        "not an address",
        "",
        "127.0.0.1.evil.example",
    ],
)
def test_other_addresses_are_refused(address: str) -> None:
    assert not is_operator_network(address)
