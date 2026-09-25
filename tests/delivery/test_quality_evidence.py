from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.quality_evidence import select_evidence

NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)
SHA = "a" * 40
REQUIRED = {"quality-evidence-v2", "backend-coverage"}
FIXTURES = Path(__file__).parent / "fixtures" / "quality-evidence"


def run(**overrides: object) -> dict[str, object]:
    result = json.loads((FIXTURES / "runs.json").read_text())["workflow_runs"][0]
    result.update(overrides)
    return result


def artifacts(run_id: int = 42, names: set[str] | None = None) -> dict[str, object]:
    return {
        "artifacts": [
            {
                **json.loads((FIXTURES / "artifacts.json").read_text())["artifacts"][0],
                "id": index,
                "name": name,
                "expired": False,
                "size_in_bytes": 100,
                "created_at": "2026-09-15T06:00:00Z",
                "updated_at": "2026-09-15T06:00:00Z",
                "expires_at": "2026-09-22T06:00:00Z",
                "workflow_run": {"id": run_id, "head_sha": SHA, "head_branch": "master"},
            }
            for index, name in enumerate(names or REQUIRED, start=1)
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
            artifacts() if artifact_payload is None else artifact_payload,
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
        old = artifacts()
        old["artifacts"][0]["created_at"] = "2026-09-14T11:59:59Z"  # type: ignore[index]
        self.assertEqual("execute", self.select([run()], old)["decision"])
        self.assertEqual("execute", self.select([run(conclusion="failure")])["decision"])
        self.assertEqual("execute", self.select([run(conclusion="cancelled")])["decision"])
        incomplete = run()
        del incomplete["run_started_at"]
        self.assertEqual("execute", self.select([incomplete])["decision"])
        expired = artifacts()
        expired["artifacts"][0]["expired"] = True  # type: ignore[index]
        self.assertEqual("execute", self.select([run()], expired)["decision"])

    def test_active_matching_run_blocks_a_duplicate(self) -> None:
        result = self.select([run(id=43, status="in_progress", conclusion=None)])
        self.assertEqual("in_progress", result["decision"])
        self.assertEqual(43, result["run_id"])

    def test_queued_successor_does_not_deadlock_older_run(self) -> None:
        self.assertEqual(
            "execute", self.select([run(id=100, status="queued", conclusion=None)])["decision"]
        )

    def test_timestamp_and_artifact_metadata_fail_closed(self) -> None:
        for field, value in (
            ("created_at", None),
            ("created_at", "not-a-time"),
            ("created_at", "2026-09-15T06:00:00"),
            ("created_at", "2026-09-15T13:00:00Z"),
            ("expires_at", "2026-09-15T12:00:00Z"),
            ("expires_at", None),
            ("expired", None),
            ("size_in_bytes", 0),
        ):
            with self.subTest(field=field, value=value):
                payload = artifacts()
                payload["artifacts"][0][field] = value
                self.assertEqual("execute", self.select([run()], payload)["decision"])

    def test_rerun_cannot_rejuvenate_retained_artifacts(self) -> None:
        rerun = run(run_attempt=2, run_started_at="2026-09-15T07:00:00Z")
        self.assertEqual("execute", self.select([rerun])["decision"])
        # A complete fresh attempt is eligible; updated_at never dates evidence.
        rerun["run_started_at"] = "2026-09-15T05:59:00Z"
        self.assertEqual("reused", self.select([rerun])["decision"])
        self.assertEqual(6, self.select([run(updated_at="2026-09-15T12:00:00Z")])["age_hours"])

    def test_exact_age_boundary_and_oldest_artifact(self) -> None:
        payload = artifacts()
        payload["artifacts"][0]["created_at"] = "2026-09-14T12:00:00Z"
        origin = run(run_started_at="2026-09-14T11:00:00Z")
        self.assertEqual("reused", self.select([origin], payload)["decision"])
        payload["artifacts"][0]["created_at"] = "2026-09-14T11:59:59Z"
        self.assertEqual("execute", self.select([origin], payload)["decision"])

    def test_reuse_run_without_marker_keeps_original_origin(self) -> None:
        result = self.select([run(id=43), run()])
        self.assertEqual(42, result["run_id"])
        self.assertEqual(6, result["age_hours"])

    def test_rejects_wrong_branch_event_contract_and_artifact_origin(self) -> None:
        for change in ({"head_branch": "topic"}, {"event": "pull_request"}):
            self.assertEqual("execute", self.select([run(**change)])["decision"])
        payload = artifacts()
        payload["artifacts"][0]["workflow_run"]["head_sha"] = "b" * 40
        self.assertEqual("execute", self.select([run()], payload)["decision"])
        payload = artifacts(names={"quality-evidence-v1", "backend-coverage"})
        self.assertEqual("execute", self.select([run()], payload)["decision"])

    def test_api_error_objects_are_not_empty_successful_responses(self) -> None:
        for payload in ({"message": "API rate limit exceeded"}, [], {"artifacts": None}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.select([run()], payload)

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

    def test_publication_cannot_bypass_newer_failed_audits(self) -> None:
        for newer in (
            run(id=43, conclusion="failure", run_started_at="2026-09-15T07:00:00Z"),
            run(id=41, run_attempt=2, conclusion="failure", run_started_at="2026-09-15T07:00:00Z"),
        ):
            runs = [run(), newer]
            # Quality retries the time-dependent audit with the retained image.
            self.assertEqual("reused", self.select(runs)["decision"])
            result = select_evidence(
                {"workflow_runs": runs},
                artifacts(),
                target_sha=SHA,
                current_run_id=None,
                now=NOW,
                required_artifacts=REQUIRED,
            )
            self.assertEqual("execute", result["decision"])
