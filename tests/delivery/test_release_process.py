from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tests.delivery.workflow_contract import (
    job_block,
    trigger_block,
    workflow_text,
)


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = workflow_text(".github/workflows/release.yml")
        cls.product_workflow = workflow_text(".github/workflows/product-publish.yml")
        cls.preflight = job_block(cls.workflow, "preflight")
        cls.product = job_block(cls.workflow, "product")
        cls.publish = job_block(cls.product_workflow, "publish")

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

    def test_stable_product_publish_inherits_minimal_preflight_actions_permission(self) -> None:
        self.assertIn("actions: read", self.product)
        self.assertNotIn("actions: write", self.product)
        self.assertIn("actions: read", job_block(self.product_workflow, "preflight"))

    def test_preflight_loads_build_metadata_from_checkout_src_layout(self) -> None:
        python_path = re.search(r"^\s+PYTHONPATH:\s+(\S+)\s*$", self.preflight, re.MULTILINE)
        self.assertIsNotNone(python_path)

        _, heredoc, remainder = self.preflight.partition("python3 - <<'PY'\n")
        self.assertTrue(heredoc)
        python_source, terminator, _ = remainder.partition("\n          PY\n")
        self.assertTrue(terminator)

        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONPATH": python_path.group(1),
                "RELEASE_TAG": "v0.8.0",
                "TARGET_SHA": "a" * 40,
            }
        )
        result = subprocess.run(
            [sys.executable, "-S", "-"],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            input=textwrap.dedent(python_source),
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout.strip(), "0.8.0")

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

    def test_release_builds_only_the_six_cli_assets_and_attests_the_oci_image(self) -> None:
        self.assertIn('image="ghcr.io/${GH_REPO,,}-app"', self.publish)
        self.assertIn("platforms: linux/amd64,linux/arm64", self.publish)
        self.assertNotIn('image="ghcr.io/${GH_REPO,,}"', self.publish)
        self.assertIn("goreleaser release --clean", self.publish)
        self.assertIn("goreleaser/goreleaser-action@", self.publish)
        self.assertIn('lzug-admin-"$VERSION"-*.tar.gz', self.publish)
        self.assertIn('lzug-admin-"$VERSION"-*.zip', self.publish)
        self.assertIn("Generate the OCI image SBOM", self.publish)
        self.assertIn('"${SYFT_BINARY:-syft}" scan --config .syft.yaml "$IMAGE"', self.publish)
        self.assertNotIn("scripts/sbom.py", self.publish)
        self.assertNotIn("release-assets/lzug-$VERSION.sbom.cdx.json", self.publish)
        self.assertIn("actions/attest@", self.publish)
        self.assertIn(
            'gh release edit "$RELEASE_TAG" --repo "$GH_REPO" --draft=false', self.publish
        )
        self.assertNotIn("release-assets/lzug-$VERSION.dependencies", self.publish)
        self.assertNotIn("release-assets/lzug-$VERSION.image", self.publish)
        self.assertNotIn("release-assets/cli/$archive_stem.cdx", self.publish)
        self.assertNotIn("subject-checksums", self.publish)
        self.assertNotIn('checksums.txt" release-assets', self.publish)
        self.assertNotIn("release-manifest.json", self.publish)

    def test_stable_product_publish_defines_syft_before_using_its_output(self) -> None:
        syft_step = "id: syft\n        uses: anchore/sbom-action/download-syft@"
        self.assertIn(syft_step, self.publish)
        self.assertLess(self.publish.index(syft_step), self.publish.index("SYFT_BINARY:"))


if __name__ == "__main__":
    unittest.main()
