from __future__ import annotations

import re
import unittest
from pathlib import Path

from backend.tests.workflow_contract import (
    action_blocks,
    action_references,
    job_block,
    trigger_block,
    workflow_name,
    workflow_text,
)

PR_GATES = {
    "docs-gate": "Pull Request / Documentation",
    "backend-gate": "Pull Request / Backend",
    "frontend-gate": "Pull Request / Frontend",
    "cli-gate": "Pull Request / CLI",
    "container-gate": "Pull Request / Container",
}

SYNTHETIC_FIXTURE_PATHS = {
    "fixtures/synthetic-fixtures.json",
    "scripts/generate_synthetic_fixtures.py",
    "db/seed_demo.sql",
    "frontend/src/app/testing/synthetic-fixtures.generated.ts",
    "prototypes/pruefungsrunde-prototyp/synthetic-fixtures.generated.js",
}


class QualityWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.codeql = workflow_text(".github/workflows/ci.yml")
        cls.pull_request = workflow_text(".github/workflows/pull-request.yml")
        cls.quality = workflow_text(".github/workflows/quality.yml")
        cls.dependabot = workflow_text(".github/workflows/dependabot-auto-merge.yml")

    def test_pull_requests_use_five_stable_domain_gates(self) -> None:
        self.assertIn("pull_request:", trigger_block(self.pull_request))
        for job_id, check_name in PR_GATES.items():
            with self.subTest(job=job_id):
                gate = job_block(self.pull_request, job_id)
                self.assertIn(f"name: {check_name}", gate)
                self.assertIn("if: always()", gate)
                self.assertIn("codeql", gate)
                self.assertIn("source-scan", gate)
                self.assertIn(
                    'test "$CHANGES:$CODEQL:$SOURCE_SCAN" = success:success:success',
                    gate,
                )
                self.assertIn("true:success", gate)
                self.assertIn("false:skipped", gate)

    def test_path_selection_is_standard_based_and_fails_closed(self) -> None:
        self.assertIn(
            "dorny/paths-filter@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d",
            self.pull_request,
        )
        for domain in (
            "fixtures",
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
        self.assertIn("codeql_languages: ${{ steps.codeql.outputs.changes }}", self.pull_request)
        self.assertIn("- '.github/**'", self.pull_request)
        self.assertIn("- 'uv.lock'", self.pull_request)
        self.assertIn("- 'frontend/package-lock.json'", self.pull_request)

    def test_productive_web_changes_select_separate_browser_contracts(self) -> None:
        self.assertIn("browser:\n              - 'backend/**'", self.pull_request)
        self.assertIn("- 'frontend/src/**'", self.pull_request)
        self.assertIn("- '!backend/tests/**'", self.pull_request)
        self.assertIn("- '!frontend/**/*.spec.ts'", self.pull_request)
        self.assertIn("needs: changes", job_block(self.pull_request, "e2e"))
        self.assertIn("needs: changes", job_block(self.pull_request, "a11y"))

    def test_master_schedule_and_manual_runs_are_unconditionally_complete(self) -> None:
        triggers = trigger_block(self.quality)
        self.assertIn("push:", triggers)
        self.assertIn("schedule:", triggers)
        self.assertIn("workflow_dispatch:", triggers)
        self.assertNotIn("pull_request:", triggers)
        self.assertNotIn("paths-filter", self.quality)
        self.assertNotIn("needs: changes", self.quality)
        self.assertNotIn("if: always()", self.quality)
        for job_id in (
            "backend",
            "frontend",
            "docs",
            "cli",
            "infra",
            "container",
            "e2e",
            "a11y",
        ):
            with self.subTest(job=job_id):
                self.assertIn("runs-on:", job_block(self.quality, job_id))

    def test_quality_is_reusable_for_an_explicit_immutable_revision(self) -> None:
        workflow_call = trigger_block(self.quality)
        self.assertIn("workflow_call:", workflow_call)
        self.assertIn("revision:", workflow_call)
        self.assertIn("required: false", workflow_call)
        revision = "${{ inputs.revision || github.event.workflow_run.head_sha || github.sha }}"
        self.assertIn(f"QUALITY_REVISION: {revision}", self.quality)
        checkout_blocks = action_blocks(self.quality, "actions/checkout")
        self.assertTrue(checkout_blocks)
        self.assertTrue(all(f"ref: {revision}" in block for block in checkout_blocks))
        self.assertIn("ref: ${{ inputs.revision || github.sha }}", self.codeql)
        self.assertIn('--revision "$QUALITY_REVISION"', self.quality)

    def test_dependabot_merge_starts_exact_revision_quality_baseline(self) -> None:
        triggers = trigger_block(self.quality)
        self.assertIn("workflow_run:", triggers)
        dependabot_name = workflow_name(self.dependabot)
        self.assertIn(f"- {dependabot_name}", triggers)
        self.assertIn("- completed", triggers)
        self.assertIn("- master", triggers)

        revision = "${{ inputs.revision || github.event.workflow_run.head_sha || github.sha }}"
        self.assertIn(f"QUALITY_REVISION: {revision}", self.quality)
        self.assertIn("group: quality-${{ github.ref }}-" + revision, self.quality)
        checkout_blocks = action_blocks(self.quality, "actions/checkout")
        self.assertTrue(checkout_blocks)
        self.assertTrue(all(f"ref: {revision}" in block for block in checkout_blocks))
        self.assertIn(f"revision: {revision}", self.quality)

    def test_local_quality_tasks_are_the_ci_domain_contract(self) -> None:
        taskfile = workflow_text("Taskfile.yml")
        for task in (
            "task fixtures:check",
            "task quality:backend",
            "task quality:frontend quality:security",
            "task quality:operator",
            "task quality:infra",
            "task quality:oci quality:container quality:compose "
            "quality:operator-container quality:demo quality:sbom",
            "task docs",
        ):
            with self.subTest(task=task):
                self.assertIn(task, self.pull_request)
                self.assertIn(task, self.quality)

        self.assertIn("docs:check:", taskfile)
        self.assertIn("python3 -m scripts.check_documentation", taskfile)

    def test_synthetic_fixture_check_has_a_complete_trigger_and_ci_contract(self) -> None:
        taskfile = workflow_text("Taskfile.yml")
        changes = job_block(self.pull_request, "changes")
        pull_request_check = job_block(self.pull_request, "fixtures")
        full_quality_check = job_block(self.quality, "fixtures")
        backend_gate = job_block(self.pull_request, "backend-gate")
        fixture_filter = re.search(
            r"^            fixtures:\n(?P<paths>(?:              - .+\n)+)",
            changes,
            re.MULTILINE,
        )

        self.assertIn("fixtures:check:", taskfile)
        self.assertIn("python3 scripts/generate_synthetic_fixtures.py --check", taskfile)
        self.assertIn("- fixtures:check", taskfile)
        self.assertIn("fixtures: ${{", changes)
        self.assertIsNotNone(fixture_filter)
        for path in SYNTHETIC_FIXTURE_PATHS:
            with self.subTest(path=path):
                self.assertIn(f"- '{path}'", fixture_filter.group("paths"))
        self.assertIn("task fixtures:check", pull_request_check)
        self.assertIn("task fixtures:check", full_quality_check)
        self.assertIn("fixtures", backend_gate)

    def test_quality_actions_are_pinned_and_quality_cannot_publish(self) -> None:
        for path in (
            Path(".github/workflows/ci.yml"),
            Path(".github/workflows/pull-request.yml"),
            Path(".github/workflows/quality.yml"),
        ):
            workflow = path.read_text(encoding="utf-8")
            action_refs = [
                reference.rsplit("@", 1)[1]
                for reference in action_references(workflow)
                if not reference.startswith("./")
            ]
            with self.subTest(workflow=path.name):
                self.assertTrue(action_refs)
                self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))
                self.assertNotIn("packages: write", workflow)
                self.assertNotIn("gh release create", workflow)

    def test_codeql_analysis_identity_survives_the_workflow_split(self) -> None:
        category = 'category: ".github/workflows/ci.yml:codeql/language:${{ matrix.language }}"'
        self.assertIn(category, self.codeql)
        self.assertIn("uses: ./.github/workflows/ci.yml", self.pull_request)
        self.assertIn("uses: ./.github/workflows/ci.yml", self.quality)
        self.assertNotIn("github/codeql-action/analyze@", self.pull_request)
        self.assertNotIn("github/codeql-action/analyze@", self.quality)

    def test_codeql_reuses_only_validated_exact_base_analyses(self) -> None:
        self.assertIn("BASE_SHA: ${{ inputs.baseline-sha }}", self.codeql)
        self.assertIn('.commit_sha == $sha and .error == "" and .rules_count > 0', self.codeql)
        self.assertIn("Accept: application/sarif+json", self.codeql)
        self.assertIn('.runs[0].tool.driver.name == "CodeQL"', self.codeql)
        self.assertIn(".runs | length == 1", self.codeql)
        self.assertIn("tool.extensions[]?.rules[]?", self.codeql)
        self.assertIn("results_count", self.codeql)
        revisions: set[str] = set()
        for action in ("init", "analyze", "upload-sarif"):
            with self.subTest(action=action):
                blocks = action_blocks(self.codeql, f"github/codeql-action/{action}")
                self.assertEqual(1, len(blocks))
                match = re.search(
                    rf"uses:\s*github/codeql-action/{re.escape(action)}@([^\s#]+)",
                    blocks[0],
                )
                self.assertIsNotNone(match)
                assert match is not None
                revision = match.group(1)
                self.assertRegex(revision, r"[0-9a-f]{40}")
                revisions.add(revision)
        self.assertEqual(1, len(revisions))
        self.assertNotIn('"results": []', self.codeql)

    def test_codeql_falls_back_to_full_analysis_for_unusable_baselines(self) -> None:
        analyze = job_block(self.codeql, "analyze")
        unchanged = job_block(self.codeql, "unchanged")

        self.assertIn("needs: unchanged", analyze)
        self.assertIn(
            "fallback_languages: ${{ steps.baselines.outputs.fallback_languages }}",
            unchanged,
        )
        condition = (
            "if: contains(fromJSON(inputs.languages), matrix.language) || "
            "contains(fromJSON(needs.unchanged.outputs.fallback_languages), matrix.language)"
        )
        self.assertEqual(3, analyze.count(condition))
        self.assertIn(
            'language: ${{ fromJSON(\'["python","javascript-typescript","go"]\') }}',
            analyze,
        )
        self.assertIn("fallback='[]'", unchanged)
        self.assertIn("fallback_languages=$fallback", unchanged)
        self.assertIn(
            "No usable CodeQL baseline for $language; scheduling a full analysis.",
            unchanged,
        )
        self.assertIn(
            "CodeQL baseline lookup unavailable; scheduling full analyses for unchanged languages.",
            unchanged,
        )
        self.assertIn(
            "Unusable CodeQL SARIF baseline for $language; scheduling a full analysis.",
            unchanged,
        )
        self.assertIn("continue", unchanged)
        self.assertNotIn(
            'error("missing successful CodeQL baseline for " + $language)',
            unchanged,
        )

    def test_pull_request_codeql_matrix_uses_selected_languages(self) -> None:
        self.assertIn(
            'language: ${{ fromJSON(\'["python","javascript-typescript","go"]\') }}',
            self.codeql,
        )
        self.assertIn(
            "languages: ${{ needs.changes.outputs.codeql_languages }}",
            self.pull_request,
        )
        for path in (
            "'**/*.py'",
            "'pyproject.toml'",
            "'uv.lock'",
            "'**/*.ts'",
            "'frontend/package.json'",
            "'frontend/package-lock.json'",
            "'**/*.go'",
            "'go.mod'",
            "'.github/workflows/ci.yml'",
        ):
            with self.subTest(path=path):
                self.assertIn(f"- {path}", self.pull_request)
        self.assertIn(
            'languages: \'["python","javascript-typescript","go"]\'',
            self.quality,
        )


if __name__ == "__main__":
    unittest.main()
