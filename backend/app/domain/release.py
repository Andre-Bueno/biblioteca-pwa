"""Releases of the app itself: strict semantic versions, comparison and a defensive reading of the
public release document. Pure rules, no I/O. Everything from the network is untrusted text."""

import ipaddress
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.domain.library import sanitize_title
from app.domain.metadata import MAX_DESCRIPTION_LENGTH, sanitize_description

MAX_TAG_LENGTH = 64
MAX_NAME_LENGTH = 200
_NUMBER_DIGITS = 9
# Strict, ASCII only, whole-string match (`$` would accept a trailing newline: fullmatch is used).
_TAG = re.compile(r"v([0-9]{1,9})\.([0-9]{1,9})\.([0-9]{1,9})(?:-([0-9A-Za-z.]{1,40}))?", re.ASCII)
_REPOSITORY = re.compile(r"[A-Za-z0-9_.\-]{1,100}/[A-Za-z0-9_.\-]{1,100}", re.ASCII)


class UpdateStateName(StrEnum):
    IDLE = "idle"
    REQUESTED = "requested"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    def _key(self) -> tuple[int, int, int, int, tuple[tuple[int, int, str], ...]]:
        # A release ranks above any of its pre-releases; identifiers: numbers < words, by value.
        ident = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in self.prerelease)
        return (self.major, self.minor, self.patch, 0 if self.prerelease else 1, ident)

    def __lt__(self, other: "Version") -> bool:
        return self._key() < other._key()

    def __gt__(self, other: "Version") -> bool:
        return self._key() > other._key()

    def text(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{'.'.join(self.prerelease)}" if self.prerelease else base


def parse_tag(tag: object) -> Version | None:
    """`v1.2.3` or `v1.2.3-rc.1` -> Version; anything else (no `v`, 2 parts, spaces...) -> None."""
    if not isinstance(tag, str) or len(tag) > MAX_TAG_LENGTH:
        return None
    match = _TAG.fullmatch(tag)
    if match is None:
        return None
    pre = match.group(4)
    parts = tuple(pre.split(".")) if pre else ()
    if any(not p for p in parts):
        return None  # `v1.0.0-` / `v1.0.0-a..b`
    return Version(int(match.group(1)), int(match.group(2)), int(match.group(3)), parts)


def parse_app_version(raw: str) -> Version | None:
    """The running version (`APP_VERSION`: `1.2.3` or `v1.2.3`); None for `dev` or anything odd."""
    text = raw.strip()
    return parse_tag(text if text.startswith("v") else f"v{text}")


def valid_repository(value: str) -> bool:
    if _REPOSITORY.fullmatch(value) is None:
        return False
    # `.` and `..` match the character class but are path segments, not names.
    return all(part not in (".", "..") for part in value.split("/"))


_CGNAT = ipaddress.ip_network("100.64.0.0/10")  # Tailscale and carrier-grade NAT


def is_operator_network(address: str) -> bool:
    """True for an address an operator may legitimately keep a webhook on: loopback, a private
    network (RFC 1918, ULA) or CGNAT 100.64.0.0/10. Never link-local (cloud metadata), unspecified,
    multicast or public."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_loopback:
        return True
    if ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return False
    if ip.is_private:
        return True
    return isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT


@dataclass(frozen=True, slots=True)
class Release:
    tag: str
    version: Version
    name: str
    notes: str  # plain text
    published_at: datetime
    url: str | None  # https page of the release on github.com for THIS repository, else None


def parse_published_at(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00") if value.endswith("Z") else value
        )
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


def parse_release(payload: object, repository: str) -> Release | None:
    """The release described by GitHub's `releases/latest` document, or None when it is unusable
    (not an object, draft, pre-release, tag not strictly `vX.Y.Z[-pre]`, no valid date)."""
    if not isinstance(payload, dict):
        return None
    if payload.get("draft") is not False or payload.get("prerelease") is not False:
        return None  # only a real, published release counts; a missing flag is not trusted
    tag = payload.get("tag_name")
    version = parse_tag(tag)
    published = parse_published_at(payload.get("published_at"))
    if version is None or published is None or not isinstance(tag, str):
        return None
    if version.prerelease:
        return None  # the tag says pre-release even when the flag does not
    raw_name = payload.get("name")
    name = sanitize_title(raw_name) if isinstance(raw_name, str) and raw_name.strip() else tag
    body = payload.get("body")
    notes = sanitize_description(body, MAX_DESCRIPTION_LENGTH) if isinstance(body, str) else ""
    url = payload.get("html_url")
    prefix = f"https://github.com/{repository}/releases/".lower()
    safe_url = (
        url
        if isinstance(url, str)
        and len(url) <= 300
        and url.lower().startswith(prefix)
        and url.isascii()
        and all(32 < ord(c) < 127 for c in url)
        else None
    )
    return Release(
        tag=tag,
        version=version,
        name=name[:MAX_NAME_LENGTH],
        notes=notes,
        published_at=published,
        url=safe_url,
    )


@dataclass(frozen=True, slots=True)
class ConditionalJson:
    """Answer of a conditional GET: 200 (data), 304 (nothing new), or a throttling status."""

    status: int
    data: object | None = None
    etag: str | None = None
    remaining: int | None = None  # X-RateLimit-Remaining
    reset_at: int | None = None  # X-RateLimit-Reset (unix seconds)
    retry_after: float | None = None


@dataclass(frozen=True, slots=True)
class UpdateRequest:
    """What the operator's deploy agent is asked to do. Never carries a URL or a secret."""

    repository: str
    tag: str
    requested_at: datetime
