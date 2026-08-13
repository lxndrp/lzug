from __future__ import annotations

import re
import unittest
from pathlib import Path


class SecurityGateTests(unittest.TestCase):
    def test_all_workflow_actions_use_full_commit_shas(self) -> None:
        for path in sorted(Path(".github/workflows").glob("*.yml")):
            workflow = path.read_text(encoding="utf-8")
            action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", workflow, re.MULTILINE)
            with self.subTest(workflow=path.name):
                self.assertTrue(action_refs)
                self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))

    def test_pr_and_full_workflows_keep_source_and_code_scanning(self) -> None:
        for path in (
            Path(".github/workflows/pull-request.yml"),
            Path(".github/workflows/quality.yml"),
        ):
            workflow = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertIn("security-events: write", workflow)
                self.assertIn("language: [python, javascript-typescript, go]", workflow)
                self.assertIn("github/codeql-action/init@", workflow)
                self.assertIn("github/codeql-action/analyze@", workflow)
                self.assertIn("scanners: secret,misconfig", workflow)
                self.assertIn('exit-code: "1"', workflow)

    def test_pr_gates_require_the_common_security_results(self) -> None:
        workflow = Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8")
        self.assertEqual(5, workflow.count("CODEQL: ${{ needs.codeql.result }}"))
        self.assertEqual(5, workflow.count("SOURCE_SCAN: ${{ needs.source-scan.result }}"))
        self.assertEqual(
            5,
            workflow.count('test "$CHANGES:$CODEQL:$SOURCE_SCAN" = success:success:success'),
        )


if __name__ == "__main__":
    unittest.main()
