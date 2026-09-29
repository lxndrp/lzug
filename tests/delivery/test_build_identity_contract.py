from __future__ import annotations

import unittest
from pathlib import Path


class BuildIdentityContractTests(unittest.TestCase):
    def test_ci_and_release_derive_identity_from_commit_and_tag(self) -> None:
        workflows = "\n".join(
            Path(path).read_text(encoding="utf-8")
            for path in (
                ".github/workflows/pull-request.yml",
                ".github/workflows/quality.yml",
            )
        )
        taskfile = "\n".join(
            Path(path).read_text(encoding="utf-8")
            for path in ("Taskfile.yml", "packaging/Taskfile.yml", "packaging/product/Taskfile.yml")
        )
        delivery_taskfile = Path("packaging/product/Taskfile.yml").read_text(encoding="utf-8")
        release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
        product = Path(".github/workflows/product-publish.yml").read_text(encoding="utf-8")

        self.assertIn("task quality:oci", workflows)
        self.assertIn('--revision "$revision" --field identity', delivery_taskfile)
        self.assertIn('--build-arg "BUILD_IDENTITY=$build_identity"', taskfile)
        self.assertIn('--tag "$RELEASE_TAG" --revision "$TARGET_SHA"', product)
        self.assertIn("RELEASE_TAG: ${{ inputs.product_tag }}", product)
        self.assertIn("VCS_REF=${{ env.TARGET_SHA }}", product)
        self.assertNotIn("CANDIDATE_SHA", release)


if __name__ == "__main__":
    unittest.main()
