from __future__ import annotations

import unittest
from datetime import UTC, datetime

from scripts.quality_evidence import select_evidence

NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)
SHA = "a" * 40
REQUIRED = {"quality-evidence-v2", "backend-coverage"}


def run(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "id": 42,
        "head_sha": SHA,
        "head_branch": "master",
        "event": "schedule",
        "status": "completed",
        "conclusion": "success",
        "completed_at": "2026-09-15T06:00:00Z",
    }
    result.update(overrides)
    return result


def artifacts(run_id: int = 42, names: set[str] | None = None) -> dict[str, object]:
    return {
        "artifacts": [
            {"name": name, "expired": False, "workflow_run": {"id": run_id}}
            for name in names or REQUIRED
        ]
    }


class QualityEvidenceTests(unittest.TestCase):
    def select(
        self,
        runs: list[dict[str, object]],
        artifact_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return select_evidence(
            {"workflow_runs": runs},
            artifact_payload or artifacts(),
            target_sha=SHA,
            current_run_id="99",
            now=NOW,
            required_artifacts=REQUIRED,
        )

    def test_reuses_recent_complete_success(self) -> None:
        result = self.select([run()])
        self.assertEqual("reused", result["decision"])
        self.assertEqual(42, result["run_id"])

    def test_requires_exact_sha_and_complete_artifacts(self) -> None:
        self.assertEqual("execute", self.select([run(head_sha="b" * 40)])["decision"])
        self.assertEqual(
            "execute",
            self.select([run()], artifacts(names={"backend-coverage"}))["decision"],
        )

    def test_rejects_old_failed_cancelled_expired_or_incomplete_evidence(self) -> None:
        self.assertEqual(
            "execute",
            self.select([run(completed_at="2026-09-14T11:59:59Z")])["decision"],
        )
        self.assertEqual("execute", self.select([run(conclusion="failure")])["decision"])
        self.assertEqual("execute", self.select([run(conclusion="cancelled")])["decision"])
        incomplete = run()
        del incomplete["completed_at"]
        self.assertEqual("execute", self.select([incomplete])["decision"])
        expired = artifacts()
        expired["artifacts"][0]["expired"] = True  # type: ignore[index]
        self.assertEqual("execute", self.select([run()], expired)["decision"])

    def test_active_matching_run_blocks_a_duplicate(self) -> None:
        result = self.select([run(id=43, status="in_progress", conclusion=None)])
        self.assertEqual("in_progress", result["decision"])
        self.assertEqual(43, result["run_id"])

    def test_current_run_is_not_existing_evidence(self) -> None:
        result = select_evidence(
            {"workflow_runs": [run(id=99, status="in_progress", conclusion=None)]},
            {"artifacts": []},
            target_sha=SHA,
            current_run_id="99",
            now=NOW,
            required_artifacts=REQUIRED,
        )
        self.assertEqual("execute", result["decision"])

    def test_explicit_full_run_bypasses_successful_evidence(self) -> None:
        result = select_evidence(
            {"workflow_runs": [run()]},
            artifacts(),
            target_sha=SHA,
            current_run_id="99",
            now=NOW,
            required_artifacts=REQUIRED,
            force_full=True,
        )
        self.assertEqual("execute", result["decision"])
