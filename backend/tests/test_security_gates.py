from __future__ import annotations

import re
import unittest
from pathlib import Path


class SecurityGateTests(unittest.TestCase):
    def test_security_workflow_uses_blocking_gates(self) -> None:
        workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn('exit-code: "1"', workflow)
        self.assertIn("scanners: secret,misconfig", workflow)
        self.assertIn("security-events: write", workflow)
        self.assertIn('python-version: "3.14.6"', workflow)
        self.assertIn("python3 scripts/classify_quality_paths.py", workflow)
        self.assertIn(
            "if: github.event_name == 'pull_request' || " "needs.classify.outputs.codeql == 'true'",
            workflow,
        )
        self.assertIn("- language: go", workflow)
        self.assertIn("build-mode: autobuild", workflow)
        self.assertNotIn("Block high and critical SAST findings", workflow)
        self.assertNotIn("scripts/enforce_sarif_security.py", workflow)
        self.assertIn("name: Quality / Security", workflow)
        self.assertIn("SECURITY_SELECTED: ${{ needs.classify.outputs.security }}", workflow)
        self.assertIn('case "$SECURITY_SELECTED:$CODEQL_SELECTED" in', workflow)
        self.assertIn(
            'if [ "$EVENT_NAME" = "pull_request" ] || ' '[ "$CODEQL_SELECTED" = "true" ]; then',
            workflow,
        )
        self.assertIn('test "$SOURCE_SCAN_RESULT" = "success"', workflow)

        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("LZUG_AUTH_RATE_LIMIT=", dockerfile)
        self.assertNotIn("LZUG_AUTH_RATE_WINDOW_SECONDS=", dockerfile)

    def test_all_workflow_actions_use_full_commit_shas(self) -> None:
        for path in sorted(Path(".github/workflows").glob("*.yml")):
            with self.subTest(workflow=path.name):
                workflow = path.read_text(encoding="utf-8")
                action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", workflow, re.MULTILINE)
                self.assertTrue(action_refs)
                self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))


if __name__ == "__main__":
    unittest.main()
