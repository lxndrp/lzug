from __future__ import annotations

import unittest
from pathlib import Path

from scripts.classify_quality_paths import QualitySelection, classify_paths


class QualityPathClassificationTests(unittest.TestCase):
    def assert_selection(self, paths: list[str], **selected: bool) -> None:
        expected = QualitySelection(**selected)
        self.assertEqual(expected, classify_paths(paths))

    def test_process_metadata_runs_only_classification_and_gate(self) -> None:
        self.assert_selection(
            [
                "AGENTS.md",
                "CONTRIBUTING.md",
                ".github/ISSUE_TEMPLATE/bug_report.yml",
            ]
        )

    def test_technical_documentation_runs_documentation(self) -> None:
        self.assert_selection(
            ["docs/developers/documentation.md", "mkdocs.yml"],
            documentation=True,
        )

    def test_backend_tests_do_not_run_browser_jobs(self) -> None:
        self.assert_selection(["backend/tests/test_api.py"], backend=True)

    def test_productive_backend_boundaries_run_backend_docs_and_browsers(self) -> None:
        for path in (
            "backend/app.py",
            "db/migrations/010_example.sql",
            "db/schema.sql",
            "fixtures/synthetic-fixtures.json",
        ):
            with self.subTest(path=path):
                self.assert_selection(
                    [path],
                    backend=True,
                    oci=True,
                    documentation=True,
                    security=True,
                    overall=True,
                    codeql=True,
                    e2e=True,
                    a11y=True,
                )

    def test_frontend_product_runs_frontend_docs_and_browsers(self) -> None:
        self.assert_selection(
            ["frontend/src/app/app.ts"],
            frontend=True,
            oci=True,
            documentation=True,
            security=True,
            overall=True,
            codeql=True,
            e2e=True,
            a11y=True,
        )

    def test_frontend_unit_test_runs_frontend_only(self) -> None:
        self.assert_selection(["frontend/src/app/app.spec.ts"], frontend=True)

    def test_playwright_and_e2e_server_changes_keep_browser_jobs_separate(self) -> None:
        for path in (
            "frontend/e2e/quality.spec.ts",
            "frontend/playwright.config.ts",
            "backend/e2e_server.py",
        ):
            with self.subTest(path=path):
                self.assert_selection([path], overall=True, e2e=True, a11y=True)

    def test_lockfiles_run_every_job_that_installs_the_locked_runtime(self) -> None:
        self.assert_selection(
            ["uv.lock"],
            backend=True,
            oci=True,
            documentation=True,
            security=True,
            overall=True,
            e2e=True,
            a11y=True,
        )
        self.assert_selection(
            ["frontend/package-lock.json"],
            frontend=True,
            oci=True,
            documentation=True,
            security=True,
            overall=True,
            npm_security=True,
            e2e=True,
            a11y=True,
        )

    def test_compose_contract_runs_compose_job(self) -> None:
        self.assert_selection(["compose.yaml"], overall=True, compose=True)

    def test_cli_and_oci_changes_select_only_their_required_domains(self) -> None:
        self.assert_selection(
            ["cmd/lzug-admin/main.go"],
            operator_cli=True,
        )
        self.assert_selection(
            ["Dockerfile"],
            oci=True,
            overall=True,
        )

    def test_operator_protocol_boundary_selects_cli_and_web_contracts(self) -> None:
        self.assert_selection(
            ["backend/admin.py"],
            backend=True,
            operator_cli=True,
            oci=True,
            documentation=True,
            security=True,
            overall=True,
            codeql=True,
            e2e=True,
            a11y=True,
        )

    def test_security_gate_logic_selects_only_security(self) -> None:
        self.assert_selection(
            ["scripts/enforce_sarif_security.py"],
            security=True,
            codeql=True,
        )

    def test_ci_toolchain_and_unknown_paths_fail_closed_to_full_ci(self) -> None:
        full = QualitySelection.full()
        for path in (
            ".github/workflows/ci.yml",
            ".github/dependabot.yml",
            ".mise.toml",
            "Taskfile.yml",
            "scripts/classify_quality_paths.py",
            "unexpected/new-runtime-boundary",
        ):
            with self.subTest(path=path):
                self.assertEqual(full, classify_paths([path]))

    def test_mixed_changes_union_jobs_and_unknown_path_forces_full_ci(self) -> None:
        self.assert_selection(
            ["backend/tests/test_api.py", "docs/developers/documentation.md"],
            backend=True,
            documentation=True,
        )
        self.assertEqual(
            QualitySelection.full(),
            classify_paths(["AGENTS.md", "unexpected/new-runtime-boundary"]),
        )

    def test_empty_change_set_fails_closed_to_full_ci(self) -> None:
        self.assertEqual(QualitySelection.full(), classify_paths([]))


class CiWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    def test_every_pull_request_is_classified_and_full_runs_remain(self) -> None:
        self.assertIn("pull_request:\n", self.workflow)
        self.assertIn("schedule:\n", self.workflow)
        self.assertIn("workflow_dispatch:\n", self.workflow)
        self.assertIn("name: Change classification", self.workflow)
        self.assertIn("python3 scripts/classify_quality_paths.py", self.workflow)
        self.assertIn('--full-reason "full-$EVENT_NAME"', self.workflow)

    def test_quality_jobs_depend_on_classifier_outputs(self) -> None:
        for output in (
            "backend",
            "frontend",
            "npm_security",
            "documentation",
            "compose",
            "e2e",
            "a11y",
        ):
            with self.subTest(output=output):
                self.assertIn(f"if: needs.classify.outputs.{output} == 'true'", self.workflow)

    def test_stable_domain_gates_check_selected_and_skipped_results(self) -> None:
        for gate in (
            "Quality / Backend",
            "Quality / Frontend",
            "Quality / Documentation",
            "Quality / Overall",
        ):
            with self.subTest(gate=gate):
                self.assertIn(f"name: {gate}", self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn('test "$CLASSIFY_RESULT" = "success"', self.workflow)
        self.assertIn('test "$result" = "success"', self.workflow)
        self.assertIn('test "$result" = "skipped"', self.workflow)
        self.assertEqual(5, self.workflow.count('require_result "$'))
        self.assertIn("name: CI overall", self.workflow)
        self.assertIn("Kept until #305 migrates", self.workflow)

    def test_browser_jobs_keep_separate_versioned_caches_and_install_contract(self) -> None:
        self.assertEqual(2, self.workflow.count("uses: actions/cache@v6"))
        self.assertEqual(2, self.workflow.count("path: ~/.cache/ms-playwright"))
        self.assertEqual(
            2,
            self.workflow.count(
                "key: playwright-chromium-${{ runner.os }}-${{ runner.arch }}-"
                "${{ steps.playwright_version.outputs.version }}"
            ),
        )
        self.assertEqual(
            2,
            self.workflow.count("npx playwright install --with-deps chromium"),
        )
        self.assertIn("name: Browser E2E", self.workflow)
        self.assertIn("name: Accessibility", self.workflow)


class StableQualityGateContractTests(unittest.TestCase):
    def test_every_quality_workflow_uses_the_central_classifier(self) -> None:
        for path in (
            ".github/workflows/ci.yml",
            ".github/workflows/oci.yml",
            ".github/workflows/operator-cli.yml",
            ".github/workflows/security.yml",
        ):
            with self.subTest(path=path):
                workflow = Path(path).read_text(encoding="utf-8")
                self.assertIn("python3 scripts/classify_quality_paths.py", workflow)
                self.assertNotIn("classify_ci_paths.py", workflow)
                self.assertNotIn("classify_oci_paths.py", workflow)

    def test_all_stable_gate_names_exist_exactly_once(self) -> None:
        workflows = "\n".join(
            Path(path).read_text(encoding="utf-8")
            for path in (
                ".github/workflows/ci.yml",
                ".github/workflows/oci.yml",
                ".github/workflows/operator-cli.yml",
                ".github/workflows/security.yml",
            )
        )
        for gate in (
            "Quality / Backend",
            "Quality / Frontend",
            "Quality / Operator CLI",
            "Quality / OCI",
            "Quality / Documentation",
            "Quality / Security",
            "Quality / Overall",
        ):
            with self.subTest(gate=gate):
                self.assertEqual(1, workflows.count(f"name: {gate}"))

    def test_quality_workflows_cannot_publish_a_release(self) -> None:
        for path in (
            ".github/workflows/ci.yml",
            ".github/workflows/oci.yml",
            ".github/workflows/operator-cli.yml",
            ".github/workflows/security.yml",
        ):
            with self.subTest(path=path):
                workflow = Path(path).read_text(encoding="utf-8")
                self.assertNotIn("packages: write", workflow)
                self.assertNotIn("push-to-registry: true", workflow)
                self.assertNotIn("gh release create", workflow)

    def test_operator_cli_details_are_selected_and_stably_gated(self) -> None:
        workflow = Path(".github/workflows/operator-cli.yml").read_text(encoding="utf-8")
        self.assertEqual(2, workflow.count("if: needs.classify.outputs.operator_cli == 'true'"))
        self.assertIn("name: Quality / Operator CLI", workflow)
        self.assertIn("if: always()", workflow)


if __name__ == "__main__":
    unittest.main()
