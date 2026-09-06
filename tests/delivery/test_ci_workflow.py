from __future__ import annotations

import json
import os
import re
import subprocess
import unittest

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

    def test_pull_request_codeql_matrix_uses_selected_languages(self) -> None:
        self.assertIn(
            "language: ${{ fromJSON(inputs.languages) }}",
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
            "'frontend/.node-version'",
            "'frontend/package.json'",
            "'frontend/package-lock.json'",
            "'**/*.go'",
            "'operator-cli/go.mod'",
            "'.github/workflows/ci.yml'",
        ):
            with self.subTest(path=path):
                self.assertIn(f"- {path}", self.pull_request)
        self.assertIn(
            'languages: \'["python","javascript-typescript","go"]\'',
            self.quality,
        )

    def test_codeql_go_cache_uses_component_lockfile(self) -> None:
        self.assertIn("cache-dependency-path: operator-cli/go.sum", self.codeql)

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
            "scripts/sbom.py": "full",
        }.items():
            with self.subTest(path=path):
                self.assertIn(f"'{path}'", mapping_block(changes, owner, indent=12))
        self.assertIn("steps.unknown.outputs.unknown == 'true'", changes)
        self.assertIn("steps.domains.outputs.full == 'true'", changes)

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

    def test_pr_defers_product_browser_packaging_and_demo_checks_to_quality(self) -> None:
        self.assertNotIn("\n  fixtures:\n", self.pull_request)
        self.assertNotIn("\n  e2e:\n", self.pull_request)
        self.assertNotIn("\n  a11y:\n", self.pull_request)
        self.assertNotIn("quality:oci", job_block(self.pull_request, "container"))
        self.assertNotIn("quality:container", job_block(self.pull_request, "container"))
        self.assertNotIn("task test:demo", job_block(self.pull_request, "delivery"))
        self.assertIn("task test:oci", job_block(self.pull_request, "container"))
        self.assertIn("task fixtures:check test:fixtures", self.quality)
        self.assertIn("quality:oci quality:container quality:compose", self.quality)
        self.assertIn("npm --prefix frontend run test:e2e", self.quality)
        self.assertIn("npm --prefix frontend run test:a11y", self.quality)
        self.assertIn("npm --prefix frontend run test:ui-review", self.quality)

    def test_backend_pr_quality_omits_coverage_but_complete_quality_retains_it(self) -> None:
        pull_request_backend = job_block(self.pull_request, "backend")
        quality_backend = job_block(self.quality, "backend")

        self.assertIn("task quality:backend:pr", pull_request_backend)
        self.assertNotIn("coverage", pull_request_backend)
        self.assertIn("task quality:backend", quality_backend)
        self.assertNotIn("coverage xml", quality_backend)
        self.assertIn("name: backend-coverage", quality_backend)

    def test_release_and_both_promotion_channels_reject_wrong_quality_evidence(self) -> None:
        sha = "a" * 40
        valid = {
            "head_sha": sha,
            "head_branch": "master",
            "conclusion": "success",
            "event": "schedule",
        }
        for path in ("release", "demo-publish", "demo-snapshot"):
            workflow = workflow_text(f".github/workflows/{path}.yml")
            expression = re.search(
                r"jq -e --arg sha [^\n]+ '(.*?)' <<<\"\$quality_runs", workflow, re.S
            )
            self.assertIsNotNone(expression, path)
            assert expression is not None
            for change, accepted in (
                ({}, True),
                ({"event": "workflow_dispatch"}, True),
                ({"head_sha": "b" * 40}, False),
                ({"head_branch": "topic"}, False),
                ({"conclusion": "failure"}, False),
                ({"conclusion": "cancelled"}, False),
                ({"event": "push"}, False),
                ({"event": "workflow_call"}, False),
            ):
                with self.subTest(workflow=path, change=change):
                    result = subprocess.run(
                        ["jq", "-e", "--arg", "sha", sha, expression.group(1)],
                        input=json.dumps({"workflow_runs": [valid | change]}),
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(accepted, result.returncode == 0, result.stderr)

    def test_dispatch_rejects_a_moved_master_or_another_branch(self) -> None:
        gate = job_block(self.quality, "revision")
        command = gate.split("        run: |\n", 1)[1]
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
