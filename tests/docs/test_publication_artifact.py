"""Contracts for public-site artifact reuse and reproducibility selection."""

from __future__ import annotations

import unittest
from datetime import datetime

from scripts.publication_artifact import needs_reproducibility_check, reusable_run

NOW = datetime.fromisoformat("2026-09-26T12:00:00+00:00")
REVISION = "a" * 40


def run(run_id: int = 100, **overrides: object) -> dict[str, object]:
    return {
        "id": run_id,
        "head_sha": REVISION,
        "head_branch": "master",
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        **overrides,
    }


def artifact(run_id: int = 100, **overrides: object) -> dict[str, object]:
    return {
        "id": run_id + 1000,
        "name": "lzug-public-site",
        "expired": False,
        "size_in_bytes": 123,
        "created_at": "2026-09-26T10:00:00Z",
        "expires_at": "2026-10-03T10:00:00Z",
        "workflow_run": {"id": run_id},
        **overrides,
    }


class PublicationArtifactTests(unittest.TestCase):
    def select(
        self,
        runs: list[dict[str, object]],
        artifacts: list[dict[str, object]],
    ) -> str | None:
        return reusable_run(
            {"workflow_runs": runs},
            {"artifacts": artifacts},
            revision=REVISION,
            now=NOW,
        )

    def test_reuses_newest_nonexpired_artifact_from_successful_exact_master_run(self) -> None:
        selected = self.select(
            [run(), run(101)],
            [artifact(), artifact(101, created_at="2026-09-26T11:00:00Z")],
        )
        self.assertEqual("101", selected)

    def test_rejects_wrong_revision_branch_event_run_and_expired_or_empty_artifacts(self) -> None:
        wrong_revision = run(101, head_sha="b" * 40)
        wrong_branch = run(102, head_branch="feature")
        wrong_event = run(103, event="pull_request")
        failed = run(104, conclusion="failure")
        runs = [run(), wrong_revision, wrong_branch, wrong_event, failed]
        artifacts = [
            artifact(),
            artifact(101),
            artifact(102),
            artifact(103),
            artifact(104),
            artifact(100, id=2000, expired=True),
            artifact(100, id=2001, size_in_bytes=0),
            artifact(100, id=2002, expires_at="2026-09-26T11:59:59Z"),
        ]
        self.assertEqual("100", self.select(runs, artifacts))
        self.assertIsNone(self.select(runs[1:], artifacts[1:]))

    def test_reproducibility_is_limited_to_generator_configuration_and_dependencies(self) -> None:
        self.assertTrue(needs_reproducibility_check(["docs/publication/hugo.toml"]))
        self.assertTrue(needs_reproducibility_check(["frontend/package-lock.json"]))
        self.assertTrue(needs_reproducibility_check(["uv.lock"]))
        self.assertFalse(needs_reproducibility_check(["docs/portal/produkt.md"]))
        self.assertFalse(needs_reproducibility_check(["frontend/src/app/login/login.ts"]))


if __name__ == "__main__":
    unittest.main()
