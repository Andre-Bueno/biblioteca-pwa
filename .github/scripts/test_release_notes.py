"""Tests for release_notes.py (`python -m unittest`, no network)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import release_notes as rn  # noqa: E402

CHANGELOG = """# Changelog

## [Não lançado]

### Added
- future thing

## [0.2.0-rc.1] - 2026-12-01

### Added
- rc thing

## [0.1.0] - 2026-11-21

### Added
- first thing

### Fixed
- a bug

## [0.0.9] - 2026-11-01

### Added
- old
"""


class ParseTagTests(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertEqual(rn.parse_tag("v0.1.0"), ("0.1.0", False))
        self.assertEqual(rn.parse_tag("v10.20.30"), ("10.20.30", False))
        self.assertEqual(rn.parse_tag("v1.2.3-rc.1"), ("1.2.3-rc.1", True))

    def test_invalid(self) -> None:
        bad = [
            "0.1.0",
            "v1.2",
            "v1.2.3.4",
            "v1.2.3\n",
            "v1.2.3 ",
            "latest",
            "v1.2.3-",
            "v1.2.3-$(id)",
            "v1.2.3; echo x",
            "v1.2.3-a b",
            "../v1.2.3",
            "v١.2.3",
            "v1.2.3-" + "a" * 80,
            "",
        ]
        for tag in bad:
            with self.subTest(tag=tag), self.assertRaises(rn.ReleaseError):
                rn.parse_tag(tag)


class ExtractTests(unittest.TestCase):
    def test_extracts_only_the_requested_section(self) -> None:
        notes = rn.extract_notes(CHANGELOG, "0.1.0")
        self.assertIn("first thing", notes)
        self.assertIn("a bug", notes)
        self.assertNotIn("rc thing", notes)
        self.assertNotIn("old", notes)
        self.assertNotIn("## [", notes)

    def test_prerelease_section(self) -> None:
        self.assertEqual(rn.extract_notes(CHANGELOG, "0.2.0-rc.1").strip(), "### Added\n- rc thing")

    def test_last_section_runs_to_end(self) -> None:
        self.assertIn("- old", rn.extract_notes(CHANGELOG, "0.0.9"))

    def test_missing_section_fails(self) -> None:
        for version in ("9.9.9", "0.1", "0.1.0-rc.1"):
            with self.subTest(version=version), self.assertRaises(rn.ReleaseError):
                rn.extract_notes(CHANGELOG, version)

    def test_version_is_not_a_regex(self) -> None:
        with self.assertRaises(rn.ReleaseError):
            rn.extract_notes(CHANGELOG, "0.1.")  # "." must not match any character

    def test_empty_section_fails(self) -> None:
        with self.assertRaises(rn.ReleaseError):
            rn.extract_notes("## [1.0.0] - 2026-01-01\n\n## [0.9.0]\n- x\n", "1.0.0")


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.changelog = Path(self.dir.name) / "CHANGELOG.md"
        self.changelog.write_text(CHANGELOG, encoding="utf-8")
        self.notes = Path(self.dir.name) / "notes.md"
        self.out = Path(self.dir.name) / "gh_output"

    def run_cli(self, tag: str) -> int:
        return rn.main(
            [
                tag,
                "--changelog",
                str(self.changelog),
                "--notes-out",
                str(self.notes),
                "--github-output",
                str(self.out),
            ]
        )

    def test_ok_writes_notes_and_outputs(self) -> None:
        self.assertEqual(self.run_cli("v0.2.0-rc.1"), 0)
        self.assertIn("rc thing", self.notes.read_text(encoding="utf-8"))
        self.assertEqual(
            self.out.read_text(encoding="utf-8"),
            "version=0.2.0-rc.1\ntag=v0.2.0-rc.1\nprerelease=true\n",
        )

    def test_missing_section_fails_and_writes_nothing(self) -> None:
        self.assertEqual(self.run_cli("v9.9.9"), 1)
        self.assertFalse(self.notes.exists())
        self.assertFalse(self.out.exists())

    def test_invalid_tag_fails(self) -> None:
        self.assertEqual(self.run_cli("v1.2.3; id"), 1)
        self.assertFalse(self.out.exists())

    def test_missing_changelog_fails(self) -> None:
        self.changelog.unlink()
        self.assertEqual(self.run_cli("v0.1.0"), 1)

    def test_real_changelog_is_parseable(self) -> None:
        real = Path(__file__).resolve().parents[2] / "CHANGELOG.md"
        text = real.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Changelog"))
        with self.assertRaises(rn.ReleaseError):
            rn.extract_notes(text, "999.999.999")


if __name__ == "__main__":
    unittest.main()
