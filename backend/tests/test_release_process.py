from __future__ import annotations

import re
import unittest
from pathlib import Path

from scripts.release_assets import expected_release_asset_names, validate_published_release


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    def test_release_uses_only_pinned_actions(self) -> None:
        action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", self.workflow, re.MULTILINE)

        self.assertTrue(action_refs)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))

    def test_last_regular_milestone_issue_creates_a_gate(self) -> None:
        self.assertIn("issues:\n    types:\n      - closed", self.workflow)
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("type: release", self.workflow)
        self.assertIn("gh issue create", self.workflow)
        self.assertIn("open_regular", self.workflow)
        self.assertIn("Milestone $release_tag has multiple release gates.", self.workflow)

    def test_ci_is_read_once_before_environment_approval(self) -> None:
        preflight, publish = self.workflow.split("\n  publish:\n", 1)

        self.assertIn("/commits/$target_sha/check-runs", preflight)
        self.assertIn("Quality / Overall", preflight)
        self.assertIn("environment: release", publish)
        self.assertNotIn("/commits/$target_sha/check-runs", publish)
        self.assertNotIn("sleep 30", self.workflow)

    def test_tag_is_the_only_release_identity_after_approval(self) -> None:
        publish = self.workflow.split("\n  publish:\n", 1)[1]

        self.assertIn('tag --annotate "$RELEASE_TAG" "$TARGET_SHA"', publish)
        self.assertIn('git checkout --detach "$RELEASE_TAG"', publish)
        self.assertIn('--tag "$RELEASE_TAG" --revision "$TARGET_SHA"', publish)
        self.assertIn("Release $RELEASE_TAG wurde veröffentlicht", publish)
        self.assertNotIn("CANDIDATE_SHA", self.workflow)
        self.assertNotIn("release-candidate", self.workflow)

    def test_release_packages_without_repeating_quality_gates(self) -> None:
        self.assertIn("scripts/build_cli_release.py", self.workflow)
        self.assertIn("scripts/sbom.py generate-dependencies", self.workflow)
        self.assertIn("scripts/sbom.py generate-image", self.workflow)
        self.assertIn("scripts/sbom.py aggregate", self.workflow)
        self.assertIn("actions/attest@", self.workflow)
        self.assertIn("subject-checksums: ${{ runner.temp }}/lzug-release-subjects", self.workflow)
        self.assertIn("release-assets/lzug-$VERSION.sbom.cdx.json", self.workflow)
        self.assertNotIn("release-assets/lzug-$VERSION.dependencies.sbom", self.workflow)
        self.assertNotIn("release-assets/lzug-$VERSION.image.sbom", self.workflow)
        self.assertNotIn("release-assets/cli/$archive_stem.sbom", self.workflow)
        self.assertNotIn("release-assets/cli/lzug-admin-$VERSION.checksums", self.workflow)
        self.assertIn("gh release create", self.workflow)
        self.assertIn("--draft", self.workflow)
        self.assertNotIn("scripts/container-smoke.sh", self.workflow)
        self.assertNotIn("scripts/operator-container-smoke.sh", self.workflow)
        self.assertNotIn("trivy-action", self.workflow)
        self.assertNotIn("release-manifest.json", self.workflow)
        self.assertNotIn("upload-artifact", self.workflow)
        self.assertNotIn("download-artifact", self.workflow)

    def test_complete_published_release_skips_every_publication_step(self) -> None:
        existing_release = self.workflow.index("Accept an already complete published release")
        setup = self.workflow.index("Set up Go")
        self.assertLess(existing_release, setup)
        self.assertIn(
            'gh api --paginate --slurp "repos/$GH_REPO/releases?per_page=100"',
            self.workflow,
        )

        guarded_steps = (
            "Set up Go",
            "Set up Python",
            "Set up UV",
            "Install locked SBOM dependencies",
            "Download Syft",
            "Set up Docker Buildx",
            "Log in to GHCR",
            "Reuse an existing version image when completing v0.1.0",
            "Resolve the published image digest",
            "Build CLI archives and aggregate release SBOM",
            "Attest CLI archives",
            "Attest aggregate release SBOM",
            "Attest OCI provenance and SBOM",
            "Attest OCI SBOM",
            "Create or update the draft release",
            "Upload release assets and publish",
        )
        for step in guarded_steps:
            with self.subTest(step=step):
                self.assertRegex(
                    self.workflow,
                    rf"- name: {re.escape(step)}\n"
                    r"\s+if: steps\.existing_release\.outputs\.complete != 'true'",
                )
        self.assertRegex(
            self.workflow,
            r"- name: Build and publish OCI image from the tag\n"
            r"\s+if: >-\n"
            r"\s+steps\.existing_release\.outputs\.complete != 'true'",
        )

    def test_complete_matching_published_release_is_accepted(self) -> None:
        release = complete_release("v1.2.3", "1.2.3")

        validate_published_release(release, "v1.2.3", "1.2.3")

    def test_visible_asset_contract_is_exact_and_generation_aware(self) -> None:
        current = expected_release_asset_names("1.2.3")
        legacy = expected_release_asset_names("0.1.0")

        self.assertEqual(7, len(current))
        self.assertEqual({"lzug-1.2.3.sbom.cdx.json"}, {name for name in current if "sbom" in name})
        self.assertEqual(20, len(legacy))
        self.assertIn("lzug-0.1.0.release-manifest.json", legacy)

    def test_unexpected_future_release_asset_is_rejected(self) -> None:
        release = complete_release("v1.2.3", "1.2.3")
        release["assets"].append(asset("legacy-provenance.json"))

        with self.assertRaisesRegex(ValueError, "contains unexpected assets"):
            validate_published_release(release, "v1.2.3", "1.2.3")

    def test_incomplete_published_release_is_rejected(self) -> None:
        release = complete_release("v1.2.3", "1.2.3")
        release["assets"].pop()

        with self.assertRaisesRegex(ValueError, "is missing assets"):
            validate_published_release(release, "v1.2.3", "1.2.3")

    def test_incomplete_published_asset_metadata_is_rejected(self) -> None:
        for field, value, message in (
            ("state", "new", "is not uploaded"),
            ("size", 0, "is empty"),
            ("digest", None, "has no SHA-256 digest"),
        ):
            with self.subTest(field=field):
                release = complete_release("v1.2.3", "1.2.3")
                release["assets"][0][field] = value

                with self.assertRaisesRegex(ValueError, message):
                    validate_published_release(release, "v1.2.3", "1.2.3")

    def test_mismatched_published_release_is_rejected(self) -> None:
        release = complete_release("v1.2.3", "1.2.3")

        with self.assertRaisesRegex(ValueError, "does not belong to canonical tag"):
            validate_published_release(release, "v1.2.4", "1.2.4")

    def test_removed_release_control_scripts_are_not_reintroduced(self) -> None:
        self.assertFalse(Path(".github/workflows/release-candidate.yml").exists())
        self.assertFalse(Path(".github/ISSUE_TEMPLATE/release_gate.yml").exists())
        self.assertFalse(Path("scripts/release.py").exists())
        self.assertFalse(Path("scripts/release_gate.py").exists())


def asset(name: str) -> dict[str, object]:
    return {
        "name": name,
        "state": "uploaded",
        "size": 1,
        "digest": "sha256:" + "a" * 64,
    }


def complete_release(tag: str, version: str) -> dict[str, object]:
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": "-rc." in version,
        "published_at": "2026-08-13T10:37:56Z",
        "assets": [asset(name) for name in expected_release_asset_names(version)],
    }


if __name__ == "__main__":
    unittest.main()
