from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.build_cli_release import CLI_TARGETS, archive_name, sbom_name
from scripts.release import (
    check_release_manifest,
    extract_changelog,
    finalize_release_notes,
    image_references,
    parse_release_tag,
    write_cli_checksums,
    write_release_manifest,
)


class ReleaseContractTests(unittest.TestCase):
    def test_only_supported_prefixed_semver_tags_are_accepted(self) -> None:
        self.assertEqual("1.2.3", parse_release_tag("v1.2.3").version)
        self.assertEqual("0.4.0", parse_release_tag("v0.4.0").version)
        self.assertEqual("1.0.0-rc.1", parse_release_tag("v1.0.0-rc.1").version)

        for tag in ("1.2.3", "v1.2", "v01.2.3", "v1.2.3-beta.1", "latest"):
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

    def test_release_candidate_does_not_move_stable_image_aliases(self) -> None:
        sha = "b" * 40
        self.assertEqual(
            [
                "ghcr.io/lxndrp/lzug:1.0.0-rc.1",
                f"ghcr.io/lxndrp/lzug:sha-{sha}",
            ],
            image_references("lxndrp/lzug", "v1.0.0-rc.1", sha),
        )

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
                    image_sbom_asset="lzug-1.2.3.image.sbom.cdx.json",
                    dependency_sbom_asset="lzug-1.2.3.dependencies.sbom.cdx.json",
                    provenance_url="https://github.com/lxndrp/lzug/attestations/1",
                    sbom_url="https://github.com/lxndrp/lzug/attestations/2",
                    cli_provenance_url="https://github.com/lxndrp/lzug/attestations/3",
                    cli_manifest_asset="release-manifest.json",
                    cli_checksums_asset="cli/lzug-admin-1.2.3.checksums.txt",
                    run_url="https://github.com/lxndrp/lzug/actions/runs/3",
                    issue_url="https://github.com/lxndrp/lzug/issues/4",
                    repository="lxndrp/lzug",
                )
            )

            notes = output.read_text(encoding="utf-8")
            self.assertIn("sha256:" + "a" * 64, notes)
            self.assertIn("lzug-1.2.3.image.sbom.cdx.json", notes)
            self.assertIn("lzug-1.2.3.dependencies.sbom.cdx.json", notes)
            self.assertIn("attestations/1", notes)
            self.assertIn("attestations/2", notes)
            self.assertIn("issues/4", notes)

    def test_release_manifest_reserves_a_checksummed_cli_asset_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tags = root / "tags.txt"
            assets = root / "assets"
            output = root / "manifest.json"
            assets.mkdir()
            sha = "a" * 40
            version = "1.2.3"
            cli = assets / "cli"
            cli.mkdir()
            for goos, goarch, extension in CLI_TARGETS:
                (cli / archive_name(version, goos, goarch, extension)).write_bytes(
                    f"{goos}-{goarch}".encode()
                )
                stem = Path(archive_name(version, goos, goarch, extension)).stem.removesuffix(
                    ".tar"
                )
                (cli / sbom_name(version, goos, goarch, extension)).write_text(
                    json.dumps(
                        {
                            "metadata": {
                                "component": {
                                    "type": "file",
                                    "name": stem,
                                    "version": version,
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )
            write_cli_checksums(
                SimpleNamespace(
                    version=version,
                    assets=str(assets),
                    output=str(cli / "lzug-admin-1.2.3.checksums.txt"),
                )
            )
            tags.write_text(
                "\n".join(image_references("lxndrp/lzug", "v1.2.3", sha)) + "\n",
                encoding="utf-8",
            )
            arguments = SimpleNamespace(
                tag="v1.2.3",
                sha=sha,
                repository="lxndrp/lzug",
                tags=str(tags),
                assets=str(assets),
                output=str(output),
                manifest=str(output),
            )

            write_release_manifest(arguments)
            check_release_manifest(arguments)
            (cli / archive_name(version, "linux", "amd64", "tar.gz")).write_bytes(b"changed")
            with self.assertRaises(ValueError):
                check_release_manifest(arguments)
            (cli / archive_name(version, "linux", "amd64", "tar.gz")).unlink()
            with self.assertRaisesRegex(ValueError, "CLI asset set must contain exactly six"):
                check_release_manifest(arguments)

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
            with (
                mock.patch("scripts.release.verify_tag_target"),
                mock.patch(
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
                        "--notes",
                        str(notes),
                        "--tags",
                        str(tags),
                    ],
                ),
            ):
                main()

            self.assertIn("# lzug 1.2.3", notes.read_text(encoding="utf-8"))
            self.assertEqual(4, len(tags.read_text(encoding="utf-8").splitlines()))


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_scripts_run_directly_without_an_installed_project(self) -> None:
        for script in (
            "scripts/release.py",
            "scripts/release_gate.py",
            "scripts/build_cli_release.py",
        ):
            with self.subTest(script=script):
                result = subprocess.run(
                    ["python3", script, "--help"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, result.returncode, result.stderr)

    def test_workflow_is_fail_closed_and_uses_pinned_actions(self) -> None:
        workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
        action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", workflow, re.MULTILINE)

        self.assertTrue(action_refs)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))
        self.assertIn("issues:\n    types:\n      - closed", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertIn("python3 scripts/release_gate.py", workflow)
        self.assertIn("name: Qualify exact candidate without publishing", workflow)
        self.assertIn("Create a local annotated tag as the build identity source", workflow)
        self.assertIn("name: Test the exact release image and CLI identity", workflow)
        self.assertIn("name: Generate and validate both canonical CycloneDX SBOMs", workflow)
        self.assertIn("anchore/sbom-action/download-syft@", workflow)
        self.assertIn("lzug.dependencies.sbom.cdx.json", workflow)
        self.assertIn("lzug.image.sbom.cdx.json", workflow)
        self.assertIn('scripts/container-smoke.sh "$CANONICAL_REF"', workflow)
        self.assertIn("Block high and critical image findings", workflow)
        self.assertIn("scripts/build_cli_release.py", workflow)
        self.assertIn(
            "for target in linux-amd64 linux-arm64 darwin-amd64 darwin-arm64 "
            "windows-amd64 windows-arm64",
            workflow,
        )
        self.assertIn("scripts/sbom.py generate-cli", workflow)
        self.assertIn("cli-checksums", workflow)
        self.assertIn("name: Attest the six CLI archives", workflow)

        candidate = Path(".github/workflows/release-candidate.yml").read_text(encoding="utf-8")
        candidate_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", candidate, re.MULTILINE)
        self.assertTrue(candidate_refs)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in candidate_refs))
        self.assertIn("issues: write", candidate)
        self.assertNotIn("contents: write", candidate)
        self.assertNotIn("packages: write", candidate)

    def test_publish_permissions_tags_and_draft_release_are_explicit(self) -> None:
        workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
        publish = workflow.split("\n  publish:\n", 1)[1].split("\n  recover:\n", 1)[0]

        self.assertIn("contents: write", workflow)
        self.assertIn("packages: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertIn("environment: release", workflow)
        self.assertIn("GH_REPO: ${{ github.repository }}", publish)
        self.assertIn("create-tag", workflow)
        self.assertIn("release-manifest.json", workflow)
        self.assertIn("release-assets/cli", workflow)
        self.assertIn("push-to-registry: true", workflow)
        self.assertIn("name: Verify anonymous image and signed provenance", workflow)
        self.assertIn("docker logout ghcr.io", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("--draft", workflow)
        self.assertLess(
            workflow.index("Upload every checksummed release asset"),
            workflow.index("Publish only the complete release"),
        )
        self.assertIn("gh attestation verify", workflow)
        self.assertIn('gh attestation verify "$asset"', workflow)
        self.assertIn("Reopen incomplete release gate", workflow)
        self.assertNotIn(":latest", workflow)


if __name__ == "__main__":
    unittest.main()
