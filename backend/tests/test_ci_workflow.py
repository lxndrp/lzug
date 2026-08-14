from __future__ import annotations

import re
import unittest
from pathlib import Path

PR_GATES = (
    "Pull Request / Documentation",
    "Pull Request / Backend",
    "Pull Request / Frontend",
    "Pull Request / CLI",
    "Pull Request / Container",
)


class QualityWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pull_request = Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8")
        cls.quality = Path(".github/workflows/quality.yml").read_text(encoding="utf-8")

    def test_pull_requests_use_five_stable_domain_gates(self) -> None:
        self.assertIn("pull_request:\n", self.pull_request)
        for gate in PR_GATES:
            with self.subTest(gate=gate):
                self.assertEqual(1, self.pull_request.count(f"name: {gate}"))
        self.assertEqual(5, self.pull_request.count("-gate:\n"))
        self.assertGreaterEqual(self.pull_request.count("if: always()"), 5)

    def test_path_selection_is_standard_based_and_fails_closed(self) -> None:
        self.assertIn(
            "dorny/paths-filter@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d",
            self.pull_request,
        )
        for domain in (
            "docs",
            "backend",
            "frontend",
            "cli",
            "container",
            "browser",
            "infra",
        ):
            with self.subTest(domain=domain):
                self.assertIn(f"      {domain}: ${{{{", self.pull_request)
        self.assertIn("predicate-quantifier: every", self.pull_request)
        self.assertIn("steps.unknown.outputs.unknown == 'true'", self.pull_request)
        self.assertIn("- '.github/**'", self.pull_request)
        self.assertIn("- 'uv.lock'", self.pull_request)
        self.assertIn("- 'frontend/package-lock.json'", self.pull_request)
        self.assertFalse(Path("scripts/classify_quality_paths.py").exists())

    def test_productive_web_changes_select_separate_browser_contracts(self) -> None:
        self.assertIn("browser:\n              - 'backend/**'", self.pull_request)
        self.assertIn("- 'frontend/src/**'", self.pull_request)
        self.assertIn("- '!backend/tests/**'", self.pull_request)
        self.assertIn("- '!frontend/**/*.spec.ts'", self.pull_request)
        self.assertIn("name: Browser E2E details", self.pull_request)
        self.assertIn("name: Accessibility details", self.pull_request)

    def test_master_schedule_and_manual_runs_are_unconditionally_complete(self) -> None:
        self.assertIn("push:\n", self.quality)
        self.assertIn("schedule:\n", self.quality)
        self.assertIn("workflow_dispatch:\n", self.quality)
        self.assertNotIn("pull_request:\n", self.quality)
        self.assertNotIn("paths-filter", self.quality)
        self.assertNotIn("needs: changes", self.quality)
        self.assertNotIn("if: always()", self.quality)
        for job in (
            "name: Backend",
            "name: Frontend",
            "name: Documentation",
            "name: CLI",
            "name: Infrastructure",
            "name: Container",
            "name: Browser E2E",
            "name: Accessibility",
        ):
            with self.subTest(job=job):
                self.assertIn(job, self.quality)

    def test_local_quality_tasks_are_the_ci_domain_contract(self) -> None:
        for task in (
            "task quality:backend",
            "task quality:frontend quality:security",
            "task quality:operator",
            "task quality:infra",
            "task quality:oci quality:container quality:compose "
            "quality:operator-container quality:sbom",
            "task docs",
        ):
            with self.subTest(task=task):
                self.assertIn(task, self.pull_request)
                self.assertIn(task, self.quality)

    def test_quality_actions_are_pinned_and_quality_cannot_publish(self) -> None:
        for path in (
            Path(".github/workflows/pull-request.yml"),
            Path(".github/workflows/quality.yml"),
        ):
            workflow = path.read_text(encoding="utf-8")
            action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", workflow, re.MULTILINE)
            with self.subTest(workflow=path.name):
                self.assertTrue(action_refs)
                self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))
                self.assertNotIn("packages: write", workflow)
                self.assertNotIn("gh release create", workflow)

    def test_codeql_analysis_identity_survives_the_workflow_split(self) -> None:
        category = 'category: ".github/workflows/ci.yml:codeql/language:${{ matrix.language }}"'
        self.assertEqual(1, self.pull_request.count(category))
        self.assertEqual(1, self.quality.count(category))


if __name__ == "__main__":
    unittest.main()
