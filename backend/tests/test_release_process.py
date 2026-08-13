from __future__ import annotations

import re
import unittest
from pathlib import Path


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
        cls.preflight, cls.publish = cls.workflow.split("\n  publish:\n", 1)

    def test_release_uses_only_pinned_actions(self) -> None:
        action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", self.workflow, re.MULTILINE)

        self.assertTrue(action_refs)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))

    def test_dispatch_requires_an_explicit_semver_tag_on_master(self) -> None:
        self.assertIn("workflow_dispatch:", self.preflight)
        self.assertIn("release_tag:", self.preflight)
        self.assertIn('test "$GITHUB_REF" = refs/heads/master', self.preflight)
        self.assertIn("git/ref/heads/master", self.preflight)
        self.assertIn("BuildMetadata.create", self.preflight)
        self.assertIn("CHANGELOG.md must contain exactly one dated section", self.preflight)
        self.assertNotIn("issues:", self.preflight)
        self.assertNotIn("milestone", self.workflow.lower())
        self.assertNotIn("type: release", self.workflow)
        self.assertNotIn("gh issue", self.workflow)

    def test_preflight_reads_one_complete_master_quality_workflow(self) -> None:
        self.assertIn("actions/workflows/quality.yml/runs", self.preflight)
        self.assertIn(".head_sha == $sha", self.preflight)
        self.assertIn('.head_branch == "master"', self.preflight)
        self.assertIn('.conclusion == "success"', self.preflight)
        self.assertNotIn("check-runs", self.workflow)
        self.assertNotIn("Quality / Backend", self.workflow)
        self.assertNotIn("Quality / Overall", self.workflow)
        self.assertNotIn("sleep ", self.workflow)

    def test_environment_approval_precedes_immutable_tag_and_tag_checkout(self) -> None:
        self.assertIn("environment: release", self.publish)
        self.assertIn('git cat-file -t "$RELEASE_TAG"', self.publish)
        self.assertIn('git rev-parse "$RELEASE_TAG^{}"', self.publish)
        self.assertIn('tag --annotate "$RELEASE_TAG" "$TARGET_SHA"', self.publish)
        self.assertIn('git checkout --detach "$RELEASE_TAG"', self.publish)
        self.assertIn('--tag "$RELEASE_TAG" --revision "$TARGET_SHA"', self.publish)
        self.assertNotIn("git tag --force", self.workflow)
        self.assertNotIn("git push --force", self.workflow)

    def test_retry_only_reuses_the_exact_tag_and_an_unpublished_draft(self) -> None:
        self.assertIn("Existing release tag points to a different commit.", self.publish)
        self.assertIn("A published GitHub Release is terminal", self.publish)
        self.assertIn('test "$draft" = true', self.publish)
        self.assertIn("Create or update the draft release", self.publish)
        self.assertIn("--clobber", self.publish)
        self.assertNotIn("release_assets.py", self.workflow)
        self.assertNotIn("v0.1.0", self.workflow)
        self.assertFalse(Path("scripts/release_assets.py").exists())

    def test_release_builds_only_the_seven_visible_tag_bound_assets(self) -> None:
        self.assertIn("goreleaser release --clean", self.publish)
        self.assertIn("goreleaser/goreleaser-action@", self.publish)
        self.assertIn("linux-amd64 linux-arm64 darwin-amd64 darwin-arm64", self.publish)
        self.assertIn("scripts/sbom.py aggregate", self.publish)
        self.assertIn("release-assets/lzug-$VERSION.sbom.cdx.json", self.publish)
        self.assertIn("actions/attest@", self.publish)
        self.assertIn("subject-checksums: ${{ runner.temp }}/lzug-release-subjects", self.publish)
        self.assertIn("Upload the seven release assets and publish last", self.publish)
        self.assertNotIn("release-assets/lzug-$VERSION.dependencies", self.publish)
        self.assertNotIn("release-assets/lzug-$VERSION.image", self.publish)
        self.assertNotIn("release-assets/cli/$archive_stem.cdx", self.publish)
        self.assertNotIn('checksums.txt" release-assets', self.publish)
        self.assertNotIn("release-manifest.json", self.publish)

    def test_release_does_not_repeat_quality_or_security_checks(self) -> None:
        for forbidden in (
            "task quality",
            "container-smoke.sh",
            "operator-container-smoke.sh",
            "compose-smoke.sh",
            "trivy-action",
            "npm test",
            "python -m unittest",
            "upload-artifact",
            "download-artifact",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.publish)

    def test_removed_release_control_files_stay_absent(self) -> None:
        for path in (
            ".github/workflows/release-candidate.yml",
            ".github/ISSUE_TEMPLATE/release_gate.yml",
            "scripts/release.py",
            "scripts/release_gate.py",
            "scripts/release_assets.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
