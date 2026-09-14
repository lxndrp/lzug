from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

from tests.delivery.workflow_contract import (
    job_block,
    mapping_block,
    trigger_block,
    workflow_text,
)

PR_GATES = {
    "docs-gate": "Pull Request / Documentation",
    "backend-gate": "Pull Request / Backend",
    "frontend-gate": "Pull Request / Frontend",
    "cli-gate": "Pull Request / CLI",
    "container-gate": "Pull Request / Container",
}


class QualityWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.codeql = workflow_text(".github/workflows/ci.yml")
        cls.dependabot_config = workflow_text(".github/dependabot.yml")
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
                    'test "$CHANGES" = success',
                    gate,
                )
                self.assertIn("true:success", gate)
                self.assertIn("false:skipped", gate)

    def test_locked_go_modules_receive_grouped_dependabot_updates(self) -> None:
        self.assertIn("package-ecosystem: gomod", self.dependabot_config)
        self.assertIn("golang-x:", self.dependabot_config)
        self.assertIn("golang-x-security:", self.dependabot_config)
        self.assertIn("directory: /operator-cli", self.dependabot_config)

    def test_hosted_runner_images_are_versioned(self) -> None:
        for path in sorted(Path(".github/workflows").glob("*.yml")):
            with self.subTest(path=path):
                workflow = path.read_text(encoding="utf-8")
                self.assertNotRegex(workflow, r"runs-on:\s*\S+-latest\b")

    def test_quality_validates_all_workflows_with_actionlint(self) -> None:
        workflow_job = job_block(self.quality, "workflows")
        self.assertIn("name: GitHub Actions workflows", workflow_job)
        self.assertIn("mise install aqua:rhysd/actionlint@1.7.12", workflow_job)
        self.assertIn("mise exec -- task quality:workflows", workflow_job)

    def test_pull_requests_run_the_same_workflow_quality_task(self) -> None:
        workflow_job = job_block(self.pull_request, "workflow-lint")
        self.assertIn("name: GitHub Actions workflow syntax", workflow_job)
        self.assertIn("mise install aqua:rhysd/actionlint@1.7.12", workflow_job)
        self.assertIn("mise exec -- task quality:workflows", workflow_job)

    def test_pull_request_codeql_matrix_covers_all_configured_languages(self) -> None:
        self.assertIn(
            "language: ${{ fromJSON(inputs.languages) }}",
            self.codeql,
        )
        changes = job_block(self.pull_request, "changes")
        self.assertIn(
            'codeql_languages: \'["python","javascript-typescript","go"]\'',
            changes,
        )
        self.assertNotIn("Select CodeQL languages", changes)
        self.assertNotIn("steps.codeql.outputs.changes", changes)
        self.assertIn(
            "languages: ${{ needs.changes.outputs.codeql_languages }}",
            self.pull_request,
        )
        self.assertNotIn(
            "if: needs.changes.outputs.codeql_languages != '[]'",
            job_block(self.pull_request, "codeql"),
        )
        self.assertIn(
            'languages: \'["python","javascript-typescript","go"]\'',
            self.quality,
        )

    def test_codeql_categories_are_stable_across_callers(self) -> None:
        category = ".github/workflows/ci.yml:codeql/language:${{ matrix.language }}"
        self.assertIn(category, self.codeql)
        self.assertEqual(
            self.pull_request.count("languages: ${{ needs.changes.outputs.codeql_languages }}"),
            1,
        )

    def test_codeql_go_cache_uses_component_lockfile(self) -> None:
        self.assertIn("cache-dependency-path: operator-cli/go.sum", self.codeql)

    def test_native_socket_endpoints_and_backend_contract_selection(self) -> None:
        cli = job_block(self.pull_request, "cli")
        for platform in ("ubuntu-24.04", "macos-14", "windows-2025"):
            self.assertIn(platform, cli)
        self.assertIn("-run TestEndpoint", cli)
        self.assertIn(
            "'operator-cli/**'",
            mapping_block(job_block(self.pull_request, "changes"), "cli", indent=12),
        )

    def test_gates_reject_missing_failed_or_cancelled_selected_evidence(self) -> None:
        for gate_id in PR_GATES:
            gate = job_block(self.pull_request, gate_id)
            command = gate.split("        run: |\n", 1)[1]
            command = "\n".join(line[10:] for line in command.splitlines())
            selected = {
                "CHANGES": "success",
                "CODEQL_SELECTED": "true",
                "CODEQL": "success",
                "SCAN_SELECTED": "true",
                "SOURCE_SCAN": "success",
                "SELECTED": "true",
                "DETAIL": "success",
                "INFRA_SELECTED": "true",
                "INFRA_DETAIL": "success",
                "DELIVERY_SELECTED": "true",
                "DELIVERY": "success",
                "TRANSPORT_SELECTED": "true",
                "TRANSPORT": "success",
            }

            def check(values: dict[str, str], script: str = command) -> int:
                return subprocess.run(
                    ["bash", "-e", "-c", script],
                    env=os.environ | values,
                    capture_output=True,
                    check=False,
                ).returncode

            with self.subTest(gate=gate_id):
                self.assertEqual(0, check(selected))
                for key in (
                    "CHANGES",
                    "CODEQL",
                    "SOURCE_SCAN",
                    "DETAIL",
                    "INFRA_DETAIL",
                    "DELIVERY",
                    "TRANSPORT",
                ):
                    if f"${key}" not in command and f"{key}:" not in command:
                        continue
                    for bad in ("failure", "cancelled", "skipped", ""):
                        self.assertNotEqual(0, check(selected | {key: bad}), (gate_id, key, bad))
                skipped = {
                    key: ("false" if value == "true" else "skipped")
                    for key, value in selected.items()
                }
                skipped["CHANGES"] = "success"
                self.assertEqual(0, check(skipped))
                self.assertNotEqual(0, check(skipped | {"CHANGES": "failure"}))

    def test_known_scripts_have_owners_and_new_scripts_fail_closed(self) -> None:
        changes = job_block(self.pull_request, "changes")
        full = mapping_block(changes, "full", indent=12)
        unknown = mapping_block(changes, "unknown", indent=12)
        self.assertNotIn("'scripts/**'", full)
        self.assertNotIn("'!scripts/**'", unknown)
        self.assertIn("'Taskfile.yml'", full)
        for path, owner in {
            "scripts/check_documentation.py": "docs",
            "scripts/build-frontend.sh": "frontend",
            "scripts/verify_cli_release.py": "cli",
            "scripts/compose-smoke.sh": "container",
            "scripts/demo_deployment.py": "delivery",
            "scripts/generate_frontend_transport.py": "transport",
            "scripts/sbom.py": "full",
        }.items():
            with self.subTest(path=path):
                self.assertIn(f"'{path}'", mapping_block(changes, owner, indent=12))
        self.assertIn("steps.unknown.outputs.unknown == 'true'", changes)
        self.assertIn("steps.domains.outputs.full == 'true'", changes)

    def test_dependency_manifests_select_component_checks_without_full_suite(self) -> None:
        changes = job_block(self.pull_request, "changes")
        full = mapping_block(changes, "full", indent=12)
        frontend = mapping_block(changes, "frontend", indent=12)
        transport = mapping_block(changes, "transport", indent=12)
        cli = mapping_block(changes, "cli", indent=12)
        container = mapping_block(changes, "container", indent=12)

        for manifest in ("frontend/package.json", "frontend/package-lock.json"):
            self.assertIn("'frontend/**'", frontend)
            self.assertIn(f"'{manifest}'", transport)
            self.assertNotIn(f"'{manifest}'", full)

        for manifest in ("operator-cli/go.mod", "operator-cli/go.sum"):
            self.assertIn(f"'{manifest}'", cli)
            self.assertIn("'operator-cli/**'", container)
            self.assertNotIn(f"'{manifest}'", full)

        for manifest in (".python-version", "pyproject.toml", "uv.lock"):
            for domain in ("docs", "backend", "delivery", "infra", "container"):
                self.assertIn(
                    f"'{manifest}'",
                    mapping_block(changes, domain, indent=12),
                )
            self.assertNotIn(f"'{manifest}'", full)

    def test_dependabot_groups_routine_updates_and_keeps_security_separate(self) -> None:
        config = self.dependabot_config
        for routine_group in (
            "gomod-routine:",
            "python-routine:",
            "frontend-routine:",
            "actions-routine:",
        ):
            self.assertIn(routine_group, config)
            routine_pattern = (
                rf"{routine_group}\n"
                r"        applies-to: version-updates\n"
                r"        update-types: \[\"minor\", \"patch\"\]"
            )
            self.assertRegex(
                config,
                routine_pattern,
            )
        for security_group in (
            "golang-x-security:",
            "python-security:",
            "frontend-security:",
            "actions-security:",
        ):
            self.assertIn(security_group, config)
        self.assertNotIn('update-types: ["major"]', config)

    def test_documentation_contract_sources_do_not_select_all_domains(self) -> None:
        changes = job_block(self.pull_request, "changes")
        docs = mapping_block(changes, "docs", indent=12)
        full = mapping_block(changes, "full", indent=12)
        unknown = mapping_block(changes, "unknown", indent=12)
        for path, unknown_exclusion in {
            ".github/workflows/publication.yml": ".github/**",
            ".lychee.toml": ".lychee.toml",
            "tests/docs/**": "tests/**",
        }.items():
            with self.subTest(path=path):
                self.assertIn(f"'{path}'", docs)
                self.assertNotIn(f"'{path}'", full)
                self.assertIn(f"'!{unknown_exclusion}'", unknown)
        self.assertIn("'Taskfile.yml'", full)
        self.assertIn("'.mise.toml'", full)

    def test_nightly_and_dispatch_evidence_are_bound_to_the_recorded_run_sha(self) -> None:
        triggers = trigger_block(self.quality)
        self.assertNotIn("push:", triggers)
        self.assertNotIn("workflow_run:", triggers)
        self.assertNotIn("workflow_call:", triggers)
        self.assertIn('cron: "17 3 * * *"', triggers)
        self.assertIn("workflow_dispatch:", triggers)
        # An input checkout override would make run.head_sha lie about tested sources.
        self.assertNotIn("inputs.revision", self.quality)
        self.assertIn("QUALITY_REVISION: ${{ github.sha }}", self.quality)

    def test_quality_reuses_complete_evidence_but_keeps_audit_frequency(self) -> None:
        revision = job_block(self.quality, "revision")
        self.assertIn("actions/workflows/quality.yml/runs", revision)
        self.assertIn("actions/artifacts", revision)
        self.assertIn("quality-evidence-v2", revision)
        self.assertIn("source_run_id", revision)
        self.assertIn("force_full", self.quality)
        self.assertIn("cancel-in-progress: false", self.quality)
        audits = job_block(self.quality, "audits")
        self.assertIn(
            "decision == 'execute' || needs.revision.outputs.decision == 'reused'",
            audits,
        )
        self.assertIn("task quality:security", audits)
        self.assertIn(
            "decision == 'execute' || needs.revision.outputs.decision == 'reused'",
            job_block(self.quality, "source-scan"),
        )

    def test_complete_evidence_requires_all_deterministic_jobs(self) -> None:
        evidence = job_block(self.quality, "complete-evidence")
        jobs = (
            "fixtures",
            "backend",
            "frontend",
            "transport",
            "docs",
            "cli",
            "infra",
            "delivery",
            "container",
            "e2e",
            "a11y",
            "codeql",
            "source-scan",
            "audits",
        )
        for job in jobs:
            self.assertIn(job, evidence)
        self.assertIn("quality-evidence-v2", evidence)

    def test_pr_defers_product_browser_packaging_and_demo_checks_to_quality(self) -> None:
        self.assertNotIn("\n  fixtures:\n", self.pull_request)
        self.assertNotIn("\n  e2e:\n", self.pull_request)
        self.assertNotIn("\n  a11y:\n", self.pull_request)
        self.assertNotIn("quality:oci", job_block(self.pull_request, "container"))
        self.assertNotIn("quality:container", job_block(self.pull_request, "container"))
        self.assertNotIn("task test:demo", job_block(self.pull_request, "delivery"))
        self.assertIn("task delivery:oci", job_block(self.pull_request, "container"))
        self.assertIn("task fixtures:check delivery:fixtures", self.quality)
        self.assertIn("quality:oci quality:container quality:compose", self.quality)
        self.assertIn("npm --prefix frontend run test:e2e", self.quality)
        self.assertIn("npm --prefix frontend run test:a11y", self.quality)
        self.assertIn("npm --prefix frontend run test:ui-review", self.quality)

    def test_backend_pr_quality_omits_coverage_but_complete_quality_retains_it(self) -> None:
        pull_request_backend = job_block(self.pull_request, "backend")
        quality_backend = job_block(self.quality, "backend")

        self.assertIn("task backend:quality:pr", pull_request_backend)
        self.assertNotIn("coverage", pull_request_backend)
        self.assertIn("task backend:quality", quality_backend)
        self.assertNotIn("coverage xml", quality_backend)
        self.assertIn("name: backend-coverage", quality_backend)

    def test_openapi_transport_drift_is_checked_for_backend_and_frontend_changes(self) -> None:
        changes = job_block(self.pull_request, "changes")
        transport_paths = mapping_block(changes, "transport", indent=12)
        self.assertIn("'backend/**'", transport_paths)
        self.assertIn("'frontend/src/app/api/generated/**'", transport_paths)

        pull_request_transport = job_block(self.pull_request, "transport")
        quality_transport = job_block(self.quality, "transport")
        for job in (pull_request_transport, quality_transport):
            self.assertIn("uv sync --locked --extra dev", job)
            self.assertIn("npm ci --prefix frontend", job)
            self.assertIn("task frontend:transport", job)

        frontend_gate = job_block(self.pull_request, "frontend-gate")
        self.assertIn("transport", frontend_gate)
        self.assertIn("TRANSPORT_SELECTED", frontend_gate)

    def test_release_and_promotion_workflows_require_the_complete_selector(self) -> None:
        for path in ("release", "product-publish", "demo-publish", "snapshot"):
            workflow = workflow_text(f".github/workflows/{path}.yml")
            with self.subTest(workflow=path):
                self.assertIn("scripts/quality_evidence.py", workflow)
                self.assertIn("quality-evidence-v2", workflow)
                self.assertIn('.decision == "reused"', workflow)

    def test_dispatch_rejects_a_moved_master_or_another_branch(self) -> None:
        gate = job_block(self.quality, "revision")
        command = gate.split("        run: |\n", 1)[1]
        command = command.split("      - name: Select reusable complete evidence", 1)[0]
        command = "\n".join(line[10:] for line in command.splitlines())
        valid = {
            "GITHUB_SHA": "a" * 40,
            "EXPECTED_SHA": "a" * 40,
            "GITHUB_REF": "refs/heads/master",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
        }
        for change, accepted in (
            ({}, True),
            ({"EXPECTED_SHA": "b" * 40}, False),
            ({"EXPECTED_SHA": ""}, False),
            ({"GITHUB_REF": "refs/heads/topic"}, False),
            ({"GITHUB_EVENT_NAME": "schedule", "EXPECTED_SHA": ""}, True),
        ):
            with self.subTest(change=change):
                result = subprocess.run(
                    ["bash", "-e", "-c", command],
                    env=os.environ | valid | change,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(accepted, result.returncode == 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
