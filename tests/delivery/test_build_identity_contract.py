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
                "scripts/container-smoke.sh",
                "scripts/operator-container-smoke.sh",
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

    def test_runtime_contract_compares_backend_frontend_cli_and_oci(self) -> None:
        container_smoke = Path("scripts/container-smoke.sh").read_text(encoding="utf-8")
        operator_smoke = Path("scripts/operator-container-smoke.sh").read_text(encoding="utf-8")
        container_contract = Path("scripts/container-contract.sh").read_text(encoding="utf-8")
        runtime_contract = "\n".join((container_smoke, operator_smoke, container_contract))

        self.assertIn('cmp "$temporary_directory/backend-metadata.json"', runtime_contract)
        self.assertIn("frontend-metadata.json", runtime_contract)
        self.assertIn("org.opencontainers.image.version", runtime_contract)
        self.assertIn("org.opencontainers.image.revision", runtime_contract)
        self.assertNotIn("--init --seed", container_contract)
        self.assertIn("--build-metadata", runtime_contract)
        self.assertIn('cmp "$temporary_directory/container-metadata.json"', runtime_contract)

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

        self.assertIn("task quality:oci", workflows)
        self.assertIn('--revision "$revision" --field identity', taskfile)
        self.assertIn('--build-arg "BUILD_IDENTITY=$build_identity"', taskfile)
        self.assertIn('--tag "$RELEASE_TAG" --revision "$TARGET_SHA"', release)
        self.assertIn("RELEASE_TAG: ${{ needs.preflight.outputs.release_tag }}", release)
        self.assertIn("VCS_REF=${{ env.TARGET_SHA }}", release)
        self.assertNotIn("CANDIDATE_SHA", release)


if __name__ == "__main__":
    unittest.main()
