from __future__ import annotations

import unittest
from pathlib import Path

from backend.tests.workflow_contract import (
    action_references,
    job_block,
    trigger_block,
    workflow_text,
)


class SecurityGateTests(unittest.TestCase):
    def test_all_workflow_actions_use_full_commit_shas(self) -> None:
        for path in sorted(Path(".github/workflows").glob("*.yml")):
            workflow = path.read_text(encoding="utf-8")
            uses_values = action_references(workflow)
            with self.subTest(workflow=path.name):
                self.assertTrue(uses_values)
                for uses in uses_values:
                    if uses.startswith("./"):
                        continue
                    action, separator, revision = uses.rpartition("@")
                    self.assertTrue(action and separator)
                    self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_pr_and_full_workflows_keep_source_and_code_scanning(self) -> None:
        for path in (
            Path(".github/workflows/pull-request.yml"),
            Path(".github/workflows/quality.yml"),
        ):
            workflow = path.read_text(encoding="utf-8")
            with self.subTest(workflow=path.name):
                self.assertIn("security-events: write", workflow)
                self.assertIn("uses: ./.github/workflows/ci.yml", workflow)
                self.assertIn("scanners: secret,misconfig", workflow)
                self.assertIn('exit-code: "1"', workflow)
        codeql = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("github/codeql-action/init@", codeql)
        self.assertIn("github/codeql-action/analyze@", codeql)
        self.assertIn("github/codeql-action/upload-sarif@", codeql)
        self.assertIn(
            "languages: ${{ needs.changes.outputs.codeql_languages }}",
            Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8"),
        )
        self.assertIn(
            'languages: \'["python","javascript-typescript","go"]\'',
            Path(".github/workflows/quality.yml").read_text(encoding="utf-8"),
        )

    def test_pr_gates_require_the_common_security_results(self) -> None:
        workflow = workflow_text(".github/workflows/pull-request.yml")
        for job_id in (
            "docs-gate",
            "backend-gate",
            "frontend-gate",
            "cli-gate",
            "container-gate",
        ):
            with self.subTest(job=job_id):
                gate = job_block(workflow, job_id)
                self.assertIn("CODEQL: ${{ needs.codeql.result }}", gate)
                self.assertIn("SOURCE_SCAN: ${{ needs.source-scan.result }}", gate)
                self.assertIn(
                    'test "$CHANGES:$CODEQL:$SOURCE_SCAN" = success:success:success',
                    gate,
                )

    def test_dependabot_auto_merge_uses_safe_base_branch_classification(self) -> None:
        workflow = workflow_text(".github/workflows/dependabot-auto-merge.yml")
        self.assertIn("pull_request_target:", trigger_block(workflow))
        job = job_block(workflow, "enable-auto-merge")
        self.assertIn("permissions:\n      contents: write\n      pull-requests: write", job)
        self.assertNotIn("actions/checkout@", job)
        self.assertNotIn("github.event.pull_request.head", job)
        for classification in (
            "npm_and_yarn:version-update:semver-patch",
            "npm_and_yarn:version-update:semver-minor",
            "uv:version-update:semver-patch",
            "uv:version-update:semver-minor",
        ):
            with self.subTest(classification=classification):
                self.assertIn(classification, job)
        self.assertIn("steps.eligibility.outputs.eligible == 'true'", job)
        self.assertIn('gh pr merge --auto --squash "$PR_URL"', job)


if __name__ == "__main__":
    unittest.main()
