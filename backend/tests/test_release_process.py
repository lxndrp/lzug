from __future__ import annotations

import re
import unittest
from pathlib import Path


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
        self.assertIn("actions/attest@", self.workflow)
        self.assertIn("gh release create", self.workflow)
        self.assertIn("--draft", self.workflow)
        self.assertNotIn("scripts/container-smoke.sh", self.workflow)
        self.assertNotIn("scripts/operator-container-smoke.sh", self.workflow)
        self.assertNotIn("trivy-action", self.workflow)
        self.assertNotIn("release-manifest.json", self.workflow)
        self.assertNotIn("upload-artifact", self.workflow)
        self.assertNotIn("download-artifact", self.workflow)

    def test_removed_release_control_scripts_are_not_reintroduced(self) -> None:
        self.assertFalse(Path(".github/workflows/release-candidate.yml").exists())
        self.assertFalse(Path(".github/ISSUE_TEMPLATE/release_gate.yml").exists())
        self.assertFalse(Path("scripts/release.py").exists())
        self.assertFalse(Path("scripts/release_gate.py").exists())


if __name__ == "__main__":
    unittest.main()
