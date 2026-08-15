from __future__ import annotations

import unittest
from datetime import UTC, datetime

from scripts.demo_snapshot import (
    SnapshotContractError,
    snapshot_identity,
    validate_milestones,
    validate_quality_runs,
    validate_releases,
)


class DemoSnapshotTests(unittest.TestCase):
    revision = "abcdef0123456789abcdef0123456789abcdef01"
    tag = "demo/v0.2.0-SNAPSHOT.abcdef0"

    def test_identity_is_derived_only_from_tag_and_matching_full_revision(self) -> None:
        identity = snapshot_identity(self.tag, self.revision)

        self.assertEqual("v0.2.0", identity.target_version)
        self.assertEqual("v0.2.0-SNAPSHOT@abcdef0", identity.identity)
        self.assertEqual("v0.2.0-SNAPSHOT-abcdef0", identity.oci_tag)
        self.assertEqual("snapshot", identity.channel)

        for tag, revision in (
            ("v0.2.0", self.revision),
            ("demo/v0.2.0-SNAPSHOT.abcdef", self.revision),
            ("demo/v0.2.0-SNAPSHOT.abcdef0", "0" * 40),
            ("demo/v0.2.0-nightly.abcdef0", self.revision),
        ):
            with self.subTest(tag=tag), self.assertRaises(SnapshotContractError):
                snapshot_identity(tag, revision)

    def test_quality_evidence_requires_complete_successful_master_push_for_exact_sha(self) -> None:
        valid = {
            "id": 42,
            "html_url": "https://example.invalid/runs/42",
            "head_sha": self.revision,
            "head_branch": "master",
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "path": ".github/workflows/quality.yml",
            "created_at": "2026-08-15T08:00:00Z",
        }
        self.assertEqual(valid, validate_quality_runs({"workflow_runs": [valid]}, self.revision))

        for changed in (
            {"head_sha": "0" * 40},
            {"head_branch": "feature"},
            {"event": "workflow_dispatch"},
            {"status": "in_progress"},
            {"conclusion": "failure"},
            {"path": ".github/workflows/pull-request.yml"},
        ):
            with self.subTest(changed=changed), self.assertRaises(SnapshotContractError):
                validate_quality_runs({"workflow_runs": [{**valid, **changed}]}, self.revision)

    def test_target_is_exactly_one_open_future_stable_milestone(self) -> None:
        now = datetime(2026, 8, 15, tzinfo=UTC)
        valid = {
            "number": 5,
            "title": "v0.2.0",
            "state": "open",
            "due_on": "2026-10-23T00:00:00Z",
        }
        self.assertEqual(valid, validate_milestones([valid], "v0.2.0", now=now))

        for payload in (
            [],
            [{**valid, "state": "closed"}],
            [{**valid, "due_on": None}],
            [{**valid, "due_on": "2026-08-14T00:00:00Z"}],
            [valid, dict(valid)],
        ):
            with self.subTest(payload=payload), self.assertRaises(SnapshotContractError):
                validate_milestones(payload, "v0.2.0", now=now)
        with self.assertRaises(ValueError):
            validate_milestones([valid], "v0.2.0-rc.1", now=now)

    def test_target_version_must_be_newer_and_not_released(self) -> None:
        releases = [
            {"tag_name": "v0.1.2", "draft": False},
            {"tag_name": "v0.2.0-rc.1", "draft": False},
            {"tag_name": "not-semver", "draft": False},
        ]
        validate_releases(releases, "v0.2.0")

        for target, payload in (
            ("v0.1.2", releases),
            ("v0.1.1", releases),
            ("v0.2.0", [*releases, {"tag_name": "v0.2.0", "draft": False}]),
        ):
            with self.subTest(target=target), self.assertRaises(SnapshotContractError):
                validate_releases(payload, target)


if __name__ == "__main__":
    unittest.main()
