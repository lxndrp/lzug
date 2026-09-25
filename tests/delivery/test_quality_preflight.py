"""Execute the workflow's actual pre-setup selector command without publishing."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.delivery.test_quality_evidence import SHA, artifacts, run
from tests.delivery.workflow_contract import job_block, workflow_text

ROOT = Path(__file__).resolve().parents[2]
NAMES = {
    "quality-evidence-v2",
    "backend-coverage",
    "frontend-coverage",
    "lzug-documentation",
    "lzug-sboms",
    "quality-container-image",
}


class QualityPreflightTests(unittest.TestCase):
    def execute(
        self,
        workflow: str,
        *,
        event: str = "schedule",
        api_error: bool = False,
        force_full: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object] | None]:
        document = workflow_text(f".github/workflows/{workflow}.yml")
        if workflow == "quality":
            block = job_block(document, "revision")
            block = block.split("      - name: Select reusable complete evidence", 1)[1]
            command = block.split("        run: |\n", 1)[1]
        else:
            # Execute only the evidence gate: no tag mutation or publication.
            start = document.index('          gh api --paginate --slurp "repos/')
            end = document.index('quality-decision.json" >/dev/null', start)
            command = document[start : end + len('quality-decision.json" >/dev/null')]
        command = "set -euo pipefail\n" + "\n".join(
            line[10:] for line in command.splitlines() if line.strip()
        )
        command = command.replace("${{ github.repository }}", "example/project")
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            (temp / "runs.json").write_text(json.dumps([{"workflow_runs": [run(event=event)]}]))
            (temp / "artifacts.json").write_text(json.dumps([artifacts(names=NAMES)]))
            executables = {
                "gh": '#!/bin/sh\n[ "$API_ERROR" = false ] || exit 1\n'
                'case "$*" in\n'
                '  *actions/workflows/quality.yml/runs*) cat "$RUNNER_TEMP/runs.json" ;;\n'
                '  *actions/artifacts*) cat "$RUNNER_TEMP/artifacts.json" ;;\n'
                "  *) exit 2 ;;\nesac\n",
                "date": "#!/bin/sh\nprintf '%s\\n' 2026-09-15T12:00:00Z\n",
                "python3": f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n',
            }
            for name, source in executables.items():
                path = temp / name
                path.write_text(source)
                path.chmod(0o755)
            result = subprocess.run(
                ["bash", "-c", command],
                cwd=ROOT,
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "PATH": f"{temp}{os.pathsep}{os.environ['PATH']}",
                    "RUNNER_TEMP": directory,
                    "GH_REPO": "example/project",
                    "TARGET_SHA": SHA,
                    "target_sha": SHA,
                    "GITHUB_SHA": SHA,
                    "CURRENT_RUN_ID": "99",
                    "FORCE_FULL": str(force_full).lower(),
                    "API_ERROR": str(api_error).lower(),
                    "GITHUB_OUTPUT": str(temp / "outputs"),
                    "GITHUB_STEP_SUMMARY": str(temp / "summary"),
                },
            )
            decision = temp / "quality-decision.json"
            return result, json.loads(decision.read_text()) if decision.exists() else None

    def test_actual_preflight_invocation_reuses_original_evidence(self) -> None:
        for workflow in ("quality", "release", "snapshot", "product-publish", "demo-publish"):
            with self.subTest(workflow=workflow):
                result, decision = self.execute(workflow)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("reused", decision["decision"])
                self.assertEqual(42, decision["run_id"])

    def test_gates_reject_pr_evidence_and_api_failures(self) -> None:
        for workflow in ("release", "snapshot", "product-publish", "demo-publish"):
            with self.subTest(workflow=workflow):
                result, decision = self.execute(workflow, event="pull_request")
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("execute", decision["decision"])
                result, decision = self.execute(workflow, api_error=True)
                self.assertNotEqual(0, result.returncode)
                self.assertIsNone(decision)

    def test_quality_force_full_and_api_error(self) -> None:
        result, decision = self.execute("quality", force_full=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("execute", decision["decision"])
        result, decision = self.execute("quality", api_error=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIsNone(decision)

    def test_runner_regression_runs_before_project_python_setup(self) -> None:
        for workflow in ("quality", "pull-request"):
            job = job_block(workflow_text(f".github/workflows/{workflow}.yml"), "delivery")
            self.assertLess(
                job.index("python3 -m unittest tests.delivery.test_quality_preflight"),
                job.index("actions/setup-python@"),
            )
