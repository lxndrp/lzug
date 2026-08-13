from __future__ import annotations

import unittest
from pathlib import Path


class OciWorkflowContractTests(unittest.TestCase):
    def test_pr_and_full_workflows_keep_the_packaged_runtime_contract(self) -> None:
        for path in (
            Path(".github/workflows/pull-request.yml"),
            Path(".github/workflows/quality.yml"),
        ):
            workflow = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertIn(
                    "task quality:oci quality:container quality:compose "
                    "quality:operator-container quality:sbom",
                    workflow,
                )
                self.assertIn("anchore/sbom-action/download-syft@", workflow)
                self.assertIn("scripts/sbom.py generate-image", workflow)
                self.assertIn("scripts/sbom.py validate --kind image", workflow)
                self.assertIn("scanners: vuln,secret,misconfig", workflow)
                self.assertIn('exit-code: "1"', workflow)

    def test_local_image_build_supports_docker_and_podman(self) -> None:
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")
        self.assertIn('engine="${CONTAINER_ENGINE:-}"', taskfile)
        self.assertIn("command -v docker", taskfile)
        self.assertIn("command -v podman", taskfile)
        self.assertIn("CONTAINER_ENGINE must be docker or podman.", taskfile)
        self.assertIn('build_identity="$(python3 scripts/build_metadata.py', taskfile)
        self.assertIn('--build-arg "BUILD_IDENTITY=$build_identity"', taskfile)
        self.assertIn('--build-arg "VCS_REF=$revision"', taskfile)

    def test_compose_health_probe_tolerates_an_empty_process_list(self) -> None:
        smoke = Path("scripts/compose-smoke.sh").read_text(encoding="utf-8")
        self.assertIn('if parsed else ""', smoke)


if __name__ == "__main__":
    unittest.main()
