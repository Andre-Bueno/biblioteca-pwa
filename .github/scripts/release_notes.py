#!/usr/bin/env python3
"""Validate a release tag and extract its notes from CHANGELOG.md.

Usage:
    release_notes.py <tag> [--changelog CHANGELOG.md] [--notes-out FILE] [--github-output FILE]

- The tag is validated with a strict regex (vX.Y.Z or vX.Y.Z-prerelease) and is only ever used
  as data here: it is never interpolated into a shell command.
- The release FAILS (exit 1) if the CHANGELOG has no section `## [X.Y.Z]` for that version or the
  section is empty.
- `--github-output` appends `version=`, `tag=` and `prerelease=` lines (for $GITHUB_OUTPUT).

Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TAG_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.]+)?", re.ASCII)
MAX_TAG_LENGTH = 64


class ReleaseError(Exception):
    pass


def parse_tag(tag: str) -> tuple[str, bool]:
    """Return (version without the leading v, is_prerelease). Raise ReleaseError if invalid."""
    if len(tag) > MAX_TAG_LENGTH or not TAG_RE.fullmatch(tag):
        raise ReleaseError("invalid tag: expected vX.Y.Z or vX.Y.Z-prerelease")
    version = tag[1:]
    return version, "-" in version


def extract_notes(changelog: str, version: str) -> str:
    """Body of the `## [<version>]` section (up to the next `## ` heading), stripped."""
    heading = re.compile(rf"^## \[{re.escape(version)}\](\s.*)?$")
    lines = changelog.splitlines()
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise ReleaseError(f"CHANGELOG.md has no section '## [{version}]'")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = "\n".join(lines[start + 1 : end]).strip()
    if not body:
        raise ReleaseError(f"CHANGELOG.md section '## [{version}]' is empty")
    return body + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tag")
    parser.add_argument("--changelog", default="CHANGELOG.md")
    parser.add_argument("--notes-out")
    parser.add_argument("--github-output")
    args = parser.parse_args(argv)
    try:
        version, prerelease = parse_tag(args.tag)
        notes = extract_notes(Path(args.changelog).read_text(encoding="utf-8"), version)
    except (ReleaseError, OSError) as exc:
        print(f"release_notes: {exc}", file=sys.stderr)
        return 1
    if args.notes_out:
        Path(args.notes_out).write_text(notes, encoding="utf-8")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            flag = "true" if prerelease else "false"
            handle.write(f"version={version}\ntag={args.tag}\nprerelease={flag}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
