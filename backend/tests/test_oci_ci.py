from __future__ import annotations

import re
import unittest
from pathlib import Path


class OciWorkflowContractTests(unittest.TestCase):
    def test_workflow_reuses_one_checksummed_image_for_smoke_and_scan(self) -> None:
        workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
        action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", workflow, re.MULTILINE)

        self.assertTrue(action_refs)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))
        self.assertEqual(1, workflow.count("docker/build-push-action@"))
        self.assertEqual(4, workflow.count("sha256sum --check lzug-image.tar.sha256"))
        self.assertEqual(5, workflow.count("name: lzug-quality-image"))
        self.assertIn('scripts/container-smoke.sh "$IMAGE_REF"', workflow)
        self.assertIn("scripts/compose-smoke.sh", workflow)
        self.assertIn('scripts/operator-container-smoke.sh "$IMAGE_REF"', workflow)
        self.assertIn("scanners: vuln,secret,misconfig", workflow)
        self.assertIn("format: cyclonedx", workflow)
        self.assertIn("python3 scripts/classify_quality_paths.py", workflow)
        self.assertIn("if: needs.classify.outputs.image == 'true'", workflow)
        self.assertIn("if: needs.classify.outputs.oci == 'true'", workflow)
        self.assertIn("name: Quality / OCI", workflow)
        self.assertNotIn("name: OCI pull request gate", workflow)
        self.assertNotIn("oci-required-check-compatibility", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn('test "$BUILD_RESULT" = "success"', workflow)
        self.assertIn('test "$SCAN_RESULT" = "success"', workflow)

    def test_cache_and_permissions_are_conservative(self) -> None:
        workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("packages: write", workflow)
        self.assertIn("cache-from: type=gha", workflow)
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("provenance: false", workflow)
        self.assertIn("sbom: false", workflow)

    def test_local_image_build_supports_docker_and_podman(self) -> None:
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")

        self.assertIn('engine="${CONTAINER_ENGINE:-}"', taskfile)
        self.assertIn("command -v docker", taskfile)
        self.assertIn("command -v podman", taskfile)
        self.assertIn("CONTAINER_ENGINE must be docker or podman.", taskfile)
        self.assertIn('command -v "$engine"', taskfile)
        self.assertIn('"$engine" info', taskfile)
        self.assertIn('"$engine" build --build-arg VCS_REF=local', taskfile)

    def test_compose_health_probe_tolerates_an_empty_process_list(self) -> None:
        smoke = Path("scripts/compose-smoke.sh").read_text(encoding="utf-8")

        self.assertIn('if parsed else ""', smoke)


if __name__ == "__main__":
    unittest.main()
