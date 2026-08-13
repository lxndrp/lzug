from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.closeout_monitor import (
    Artifact,
    Runner,
    Worktree,
    check_state,
    classify,
    inspect_worktree,
    parse_remote_heads,
    parse_worktrees,
)


class CloseoutMonitorTests(unittest.TestCase):
    def test_parse_worktrees_ignores_detached_checkout(self) -> None:
        parsed = parse_worktrees(
            "worktree /repo\nHEAD abc\nbranch refs/heads/master\n\n"
            "worktree /tmp/detached\nHEAD def\ndetached\n\n"
        )

        self.assertEqual(parsed, {"master": Path("/repo")})

    def test_parse_remote_heads_reports_only_live_codex_branches(self) -> None:
        parsed = parse_remote_heads(
            "abc\trefs/heads/codex/12-example\n"
            "def\trefs/heads/master\n"
            "ghi\trefs/heads/codex/13-another\n"
        )

        self.assertEqual(parsed, {"codex/12-example", "codex/13-another"})

    def test_clean_and_intentionally_dirty_worktree_are_distinguished(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            self._git(repository, "init")
            self._git(repository, "config", "user.email", "monitor@example.invalid")
            self._git(repository, "config", "user.name", "Closeout Monitor Test")
            self._git(repository, "config", "commit.gpgsign", "false")
            tracked = repository / "tracked.txt"
            tracked.write_text("clean\n", encoding="utf-8")
            self._git(repository, "add", "tracked.txt")
            self._git(repository, "commit", "-m", "Initial test state")

            clean = inspect_worktree(Runner(), repository, "codex/1-clean")
            self.assertEqual(clean.state, "clean")
            self.assertEqual(clean.changes, ())

            tracked.write_text("intentionally dirty\n", encoding="utf-8")
            dirty = inspect_worktree(Runner(), repository, "codex/1-dirty")
            self.assertEqual(dirty.state, "dirty")
            self.assertTrue(any("tracked.txt" in change for change in dirty.changes))

    def test_failed_ci_blocks_an_otherwise_completed_closeout(self) -> None:
        finding = classify(
            self._artifact(Worktree("/tmp/example", "codex/12-example", "clean")),
            {"state": "CLOSED", "title": "Example", "url": "https://example/issue"},
            {
                "number": 13,
                "state": "MERGED",
                "mergedAt": "2026-01-01T00:00:00Z",
                "reviewDecision": "APPROVED",
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            },
            0,
        )

        self.assertEqual(finding.ci_state, "failed")
        self.assertEqual(finding.result, "blocked_ci")

    def test_only_clean_completed_worktree_is_ready(self) -> None:
        issue = {"state": "CLOSED", "title": "Example"}
        pull_request = {
            "number": 13,
            "state": "MERGED",
            "mergedAt": "2026-01-01T00:00:00Z",
            "reviewDecision": "APPROVED",
            "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        }
        clean = classify(
            self._artifact(Worktree("/tmp/clean", "codex/12-example", "clean")),
            issue,
            pull_request,
            0,
        )
        dirty = classify(
            self._artifact(
                Worktree("/tmp/dirty", "codex/12-example", "dirty", (" M tracked.txt",))
            ),
            issue,
            pull_request,
            0,
        )

        self.assertEqual(clean.result, "ready")
        self.assertEqual(dirty.result, "blocked_worktree")
        self.assertEqual(dirty.changes, (" M tracked.txt",))

    def test_missing_worktree_and_remote_branch_are_reported(self) -> None:
        artifact = Artifact(
            "codex/12-example", 12, local_branch=True, remote_branch=False, worktree=None
        )
        finding = classify(
            artifact,
            {"state": "CLOSED", "title": "Example"},
            {
                "number": 13,
                "state": "MERGED",
                "mergedAt": "2026-01-01T00:00:00Z",
                "reviewDecision": "APPROVED",
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
            },
            0,
        )

        self.assertEqual(finding.result, "branches_only")
        self.assertEqual(finding.worktree_state, "missing")
        self.assertEqual(finding.remote_branch, "absent")

    def test_unknown_review_threads_block_closeout(self) -> None:
        finding = classify(
            self._artifact(Worktree("/tmp/example", "codex/12-example", "clean")),
            {"state": "CLOSED", "title": "Example"},
            {
                "number": 13,
                "state": "MERGED",
                "mergedAt": "2026-01-01T00:00:00Z",
                "reviewDecision": "APPROVED",
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
            },
            None,
        )

        self.assertEqual(finding.result, "blocked_review")

    def test_check_state_treats_pending_and_failure_conservatively(self) -> None:
        self.assertEqual(check_state([]), "missing")
        self.assertEqual(check_state([{"status": "IN_PROGRESS"}]), "pending")
        self.assertEqual(
            check_state([{"conclusion": "SUCCESS"}, {"conclusion": "TIMED_OUT"}]),
            "failed",
        )

    @staticmethod
    def _artifact(worktree: Worktree) -> Artifact:
        return Artifact(
            "codex/12-example", 12, local_branch=True, remote_branch=True, worktree=worktree
        )

    @staticmethod
    def _git(repository: Path, *arguments: str) -> None:
        subprocess.run(
            ("git", *arguments),
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
