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
                self.assertIn("github/codeql-action/init@", workflow)
                self.assertIn("github/codeql-action/analyze@", workflow)
                self.assertIn("scanners: secret,misconfig", workflow)
                self.assertIn('exit-code: "1"', workflow)
        self.assertIn(
            "language: ${{ fromJSON(needs.changes.outputs.codeql_languages) }}",
            Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "language: [python, javascript-typescript, go]",
            Path(".github/workflows/quality.yml").read_text(encoding="utf-8"),
        )

    def test_pr_gates_require_the_common_security_results(self) -> None:
        workflow = Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8")
        self.assertEqual(
            5, workflow.count("CODEQL_SELECTED: ${{ needs.changes.outputs.codeql_selected }}")
        )
        self.assertEqual(5, workflow.count("CODEQL: ${{ needs.codeql.result }}"))
        self.assertEqual(5, workflow.count("SOURCE_SCAN: ${{ needs.source-scan.result }}"))
        self.assertEqual(
            5,
            workflow.count('test "$CHANGES:$SOURCE_SCAN" = success:success'),
        )
        self.assertEqual(
            5,
            workflow.count(
                'test "$CODEQL_SELECTED:$CODEQL" = true:success || '
                'test "$CODEQL_SELECTED:$CODEQL" = false:skipped'
            ),
        )

    def test_dependabot_auto_merge_keeps_classification_without_polling(self) -> None:
        workflow = Path(".github/workflows/dependabot-auto-merge.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", workflow)
        self.assertNotIn("actions/checkout@", workflow)
        for classification in (
            "npm_and_yarn:version-update:semver-patch",
            "npm_and_yarn:version-update:semver-minor",
            "uv:version-update:semver-patch",
            "uv:version-update:semver-minor",
        ):
            with self.subTest(classification=classification):
                self.assertIn(classification, workflow)
        self.assertNotIn("gh pr view", workflow)
        self.assertNotIn("sleep 2", workflow)
        self.assertNotIn("mergeable=", workflow)
        self.assertIn('run: gh pr merge --auto --squash "$PR_URL"', workflow)


if __name__ == "__main__":
    unittest.main()
