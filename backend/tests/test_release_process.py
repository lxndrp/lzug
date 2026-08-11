from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.release import (
    extract_changelog,
    finalize_release_notes,
    image_references,
    parse_release_tag,
    validate_source_metadata,
)


class ReleaseContractTests(unittest.TestCase):
    def test_only_stable_prefixed_semver_tags_are_accepted(self) -> None:
        self.assertEqual("1.2.3", parse_release_tag("v1.2.3").version)
        self.assertEqual("0.4.0", parse_release_tag("v0.4.0").version)

        for tag in ("1.2.3", "v1.2", "v01.2.3", "v1.2.3-rc.1", "latest"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                parse_release_tag(tag)

    def test_required_image_tags_share_one_release_source(self) -> None:
        sha = "a" * 40
        self.assertEqual(
            [
                "ghcr.io/lxndrp/lzug:1.2.3",
                "ghcr.io/lxndrp/lzug:1.2",
                "ghcr.io/lxndrp/lzug:1",
                f"ghcr.io/lxndrp/lzug:sha-{sha}",
            ],
            image_references("lxndrp/lzug", "v1.2.3", sha),
        )

    def test_source_and_package_versions_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frontend").mkdir()
            (root / "VERSION").write_text("1.2.3\n", encoding="utf-8")
            (root / "pyproject.toml").write_text(
                '[project]\nname = "lzug"\nversion = "1.2.3"\n', encoding="utf-8"
            )
            (root / "frontend/package.json").write_text(
                '{"name":"frontend","version":"1.2.3"}', encoding="utf-8"
            )
            (root / "frontend/package-lock.json").write_text(
                '{"name":"frontend","version":"1.2.3",' '"packages":{"":{"version":"1.2.3"}}}',
                encoding="utf-8",
            )

            validate_source_metadata(root / "VERSION", "1.2.3")
            (root / "frontend/package.json").write_text(
                '{"name":"frontend","version":"1.2.2"}', encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                validate_source_metadata(root / "VERSION", "1.2.3")

    def test_changelog_section_must_be_dated_unique_and_non_empty(self) -> None:
        changelog = """# Changelog

## [Unreleased]

### Added

- Pending work.

## [1.2.3] - 2026-08-11

### Added

- Release process.

## [1.2.2] - 2026-08-10

- Earlier work.
"""
        self.assertEqual("### Added\n\n- Release process.", extract_changelog(changelog, "1.2.3"))
        with self.assertRaises(ValueError):
            extract_changelog(changelog, "9.9.9")

    def test_final_notes_contain_digest_sbom_and_attestation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base.md"
            tags = root / "tags.txt"
            output = root / "release.md"
            base.write_text("# lzug 1.2.3\n\n- Ready.\n", encoding="utf-8")
            tags.write_text("ghcr.io/lxndrp/lzug:1.2.3\n", encoding="utf-8")

            finalize_release_notes(
                SimpleNamespace(
                    base=str(base),
                    output=str(output),
                    tags=str(tags),
                    image="ghcr.io/lxndrp/lzug",
                    digest="sha256:" + "a" * 64,
                    sbom_asset="lzug-1.2.3.sbom.cdx.json",
                    provenance_url="https://github.com/lxndrp/lzug/attestations/1",
                    sbom_url="https://github.com/lxndrp/lzug/attestations/2",
                    run_url="https://github.com/lxndrp/lzug/actions/runs/3",
                    repository="lxndrp/lzug",
                )
            )

            notes = output.read_text(encoding="utf-8")
            self.assertIn("sha256:" + "a" * 64, notes)
            self.assertIn("lzug-1.2.3.sbom.cdx.json", notes)
            self.assertIn("attestations/1", notes)
            self.assertIn("attestations/2", notes)

    def test_prepare_cli_writes_deterministic_inputs(self) -> None:
        from scripts.release import main

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changelog = root / "CHANGELOG.md"
            changelog.write_text(
                "# Changelog\n\n## [1.2.3] - 2026-08-11\n\n- Ready.\n",
                encoding="utf-8",
            )
            notes = root / "notes.md"
            tags = root / "tags.txt"
            (root / "frontend").mkdir()
            (root / "VERSION").write_text("1.2.3\n", encoding="utf-8")
            (root / "pyproject.toml").write_text(
                '[project]\nname = "lzug"\nversion = "1.2.3"\n', encoding="utf-8"
            )
            (root / "frontend/package.json").write_text(
                '{"name":"frontend","version":"1.2.3"}', encoding="utf-8"
            )
            (root / "frontend/package-lock.json").write_text(
                '{"name":"frontend","version":"1.2.3",' '"packages":{"":{"version":"1.2.3"}}}',
                encoding="utf-8",
            )

            with mock.patch(
                "sys.argv",
                [
                    "release.py",
                    "prepare",
                    "--tag",
                    "v1.2.3",
                    "--sha",
                    "a" * 40,
                    "--repository",
                    "lxndrp/lzug",
                    "--changelog",
                    str(changelog),
                    "--version-file",
                    str(root / "VERSION"),
                    "--notes",
                    str(notes),
                    "--tags",
                    str(tags),
                ],
            ):
                main()

            self.assertIn("# lzug 1.2.3", notes.read_text(encoding="utf-8"))
            self.assertEqual(4, len(tags.read_text(encoding="utf-8").splitlines()))


class ReleaseWorkflowTests(unittest.TestCase):
    def test_workflow_is_fail_closed_and_uses_pinned_actions(self) -> None:
        workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
        action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", workflow, re.MULTILINE)

        self.assertTrue(action_refs)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))
        self.assertIn('tags:\n      - "v*.*.*"', workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        for required in ("ci.yml", "oci.yml", "security.yml", "operator-cli.yml"):
            self.assertIn(required, workflow)
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("name: Test the exact release image", workflow)
        self.assertIn('scripts/container-smoke.sh "$CANONICAL_REF"', workflow)
        self.assertIn("Block high and critical image findings", workflow)

    def test_publish_permissions_tags_and_draft_release_are_explicit(self) -> None:
        workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIn("contents: write", workflow)
        self.assertIn("packages: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertIn("environment: release", workflow)
        self.assertIn("latest=false", workflow)
        self.assertIn("type=semver,pattern={{version}}", workflow)
        self.assertIn("type=semver,pattern={{major}}.{{minor}}", workflow)
        self.assertIn("type=semver,pattern={{major}}", workflow)
        self.assertIn("type=sha,format=long", workflow)
        self.assertIn("push-to-registry: true", workflow)
        self.assertIn("name: Verify anonymous GHCR access", workflow)
        self.assertIn("docker logout ghcr.io", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("--draft", workflow)
        self.assertLess(workflow.index("gh release upload"), workflow.index("--draft=false"))
        self.assertNotIn(":latest", workflow)


if __name__ == "__main__":
    unittest.main()
