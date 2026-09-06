from __future__ import annotations

import unittest

from tests.delivery.workflow_contract import (
    job_block,
    trigger_block,
    workflow_text,
)


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = workflow_text(".github/workflows/release.yml")
        cls.preflight = job_block(cls.workflow, "preflight")
        cls.publish = job_block(cls.workflow, "publish")

    def test_dispatch_requires_an_explicit_semver_tag_on_master(self) -> None:
        dispatch = trigger_block(self.workflow)
        self.assertIn("workflow_dispatch:", dispatch)
        self.assertIn("release_tag:", dispatch)
        self.assertIn("required: true", dispatch)
        self.assertIn('test "$GITHUB_REF" = refs/heads/master', self.preflight)
        self.assertIn("git/ref/heads/master", self.preflight)
        self.assertIn("BuildMetadata.create", self.preflight)
        self.assertNotIn("issues:", self.preflight)
        self.assertNotIn("milestone", self.workflow.lower())
        self.assertNotIn("type: release", self.workflow)
        self.assertNotIn("gh issue", self.workflow)

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
        self.assertIn('test "$(git rev-parse "$RELEASE_TAG^{}")" = "$TARGET_SHA"', self.publish)
        self.assertIn('test "$draft" = true', self.publish)
        self.assertIn('gh release view "$RELEASE_TAG"', self.publish)
        self.assertIn('gh release create "$RELEASE_TAG"', self.publish)
        self.assertIn("--clobber", self.publish)

    def test_release_builds_only_the_seven_visible_tag_bound_assets(self) -> None:
        self.assertIn("goreleaser release --clean", self.publish)
        self.assertIn("goreleaser/goreleaser-action@", self.publish)
        self.assertIn("linux-amd64 linux-arm64 darwin-amd64 darwin-arm64", self.publish)
        self.assertIn("scripts/sbom.py aggregate", self.publish)
        self.assertIn("release-assets/lzug-$VERSION.sbom.cdx.json", self.publish)
        self.assertIn("actions/attest@", self.publish)
        self.assertIn("subject-checksums: ${{ runner.temp }}/lzug-release-subjects", self.publish)
        self.assertIn(
            'gh release edit "$RELEASE_TAG" --repo "$GH_REPO" --draft=false', self.publish
        )
        self.assertNotIn("release-assets/lzug-$VERSION.dependencies", self.publish)
        self.assertNotIn("release-assets/lzug-$VERSION.image", self.publish)
        self.assertNotIn("release-assets/cli/$archive_stem.cdx", self.publish)
        self.assertNotIn('checksums.txt" release-assets', self.publish)
        self.assertNotIn("release-manifest.json", self.publish)


if __name__ == "__main__":
    unittest.main()
