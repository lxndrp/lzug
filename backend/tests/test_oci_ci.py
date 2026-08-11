from __future__ import annotations

import re
import unittest
from pathlib import Path

from scripts.classify_oci_paths import requires_oci_pipeline


class OciPathClassificationTests(unittest.TestCase):
    def test_known_documentation_and_metadata_only_changes_are_skipped(self) -> None:
        self.assertFalse(
            requires_oci_pipeline(
                [
                    "README.md",
                    "docs/developers/architecture/oci-runtime.md",
                    ".github/ISSUE_TEMPLATE/bug_report.yml",
                    ".vscode/setup.md",
                    "prototypes/pruefungsrunde-prototyp/index.html",
                ]
            )
        )

    def test_runtime_and_unknown_paths_run_the_pipeline(self) -> None:
        for path in (
            "Dockerfile",
            "backend/app.py",
            "frontend/src/main.ts",
            "scripts/container-smoke.sh",
            ".github/workflows/oci.yml",
            "unexpected/new-build-input",
        ):
            with self.subTest(path=path):
                self.assertTrue(requires_oci_pipeline(["README.md", path]))

    def test_empty_change_set_fails_closed(self) -> None:
        self.assertTrue(requires_oci_pipeline([]))


class OciWorkflowContractTests(unittest.TestCase):
    def test_workflow_reuses_one_checksummed_image_for_smoke_and_scan(self) -> None:
        workflow = Path(".github/workflows/oci.yml").read_text(encoding="utf-8")
        action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", workflow, re.MULTILINE)

        self.assertTrue(action_refs)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))
        self.assertEqual(1, workflow.count("docker/build-push-action@"))
        self.assertEqual(2, workflow.count("sha256sum --check lzug-image.tar.sha256"))
        self.assertEqual(3, workflow.count("name: lzug-oci-image"))
        self.assertIn('scripts/container-smoke.sh "$IMAGE_REF"', workflow)
        self.assertIn("scanners: vuln,secret,misconfig", workflow)
        self.assertIn("format: cyclonedx", workflow)
        self.assertIn("name: OCI pull request gate", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn('test "$BUILD_RESULT" = "success"', workflow)
        self.assertIn('test "$SMOKE_RESULT" = "success"', workflow)
        self.assertIn('test "$SCAN_RESULT" = "success"', workflow)

    def test_cache_and_permissions_are_conservative(self) -> None:
        workflow = Path(".github/workflows/oci.yml").read_text(encoding="utf-8")

        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("packages: write", workflow)
        self.assertIn("cache-from: type=gha", workflow)
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("provenance: false", workflow)
        self.assertIn("sbom: false", workflow)


if __name__ == "__main__":
    unittest.main()
