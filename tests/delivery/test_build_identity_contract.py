from __future__ import annotations

import unittest
from pathlib import Path


class BuildIdentityContractTests(unittest.TestCase):
    def test_legacy_version_file_is_removed(self) -> None:
        self.assertFalse(Path("VERSION").exists())
        active_contract = "\n".join(
            Path(path).read_text(encoding="utf-8")
            for path in (
                "Dockerfile",
                "Taskfile.yml",
                ".github/workflows/pull-request.yml",
                ".github/workflows/quality.yml",
                ".github/workflows/release.yml",
                "tests/pester/Container.Tests.ps1",
            )
        )
        self.assertNotIn("cat VERSION", active_contract)
        self.assertNotIn("/app/VERSION", active_contract)
        self.assertNotIn("--version-file", active_contract)

    def test_oci_embeds_one_metadata_file_for_backend_and_frontend(self) -> None:
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

        self.assertIn("/build-metadata.json ./backend/src/build-metadata.json", dockerfile)
        self.assertIn("/build-metadata.json ./public/build-metadata.json", dockerfile)
        self.assertIn('org.opencontainers.image.version="$BUILD_IDENTITY"', dockerfile)
        self.assertIn('org.opencontainers.image.revision="$VCS_REF"', dockerfile)

    def test_oci_runtime_embeds_a_built_operator_cli_without_its_toolchain(self) -> None:
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

        self.assertIn("AS operator-cli-build", dockerfile)
        self.assertIn('GOOS="$TARGETOS" GOARCH="$TARGETARCH"', dockerfile)
        self.assertIn("go build -trimpath", dockerfile)
        self.assertIn("/usr/local/bin/lzug-admin", dockerfile)
        self.assertTrue(Path("tests/pester/Container.Tests.ps1").exists())

    def test_runtime_contract_compares_backend_frontend_cli_and_oci(self) -> None:
        harness = Path("tests/pester/LzugHarness.ps1").read_text(encoding="utf-8")
        container = Path("tests/pester/Container.Tests.ps1").read_text(encoding="utf-8")

        self.assertIn("org.opencontainers.image.revision", container)
        self.assertIn("Wait-LzugReady", harness)
        self.assertIn("Invoke-LzugNative", harness)

    def test_ci_and_release_derive_identity_from_commit_and_tag(self) -> None:
        workflows = "\n".join(
            Path(path).read_text(encoding="utf-8")
            for path in (
                ".github/workflows/pull-request.yml",
                ".github/workflows/quality.yml",
            )
        )
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")
        release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
        product = Path(".github/workflows/product-publish.yml").read_text(encoding="utf-8")

        self.assertIn("task quality:oci", workflows)
        self.assertIn('--revision "$revision" --field identity', taskfile)
        self.assertIn('--build-arg "BUILD_IDENTITY=$build_identity"', taskfile)
        self.assertIn('--tag "$RELEASE_TAG" --revision "$TARGET_SHA"', product)
        self.assertIn("RELEASE_TAG: ${{ inputs.product_tag }}", product)
        self.assertIn("VCS_REF=${{ env.TARGET_SHA }}", product)
        self.assertNotIn("CANDIDATE_SHA", release)


if __name__ == "__main__":
    unittest.main()
