from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class PullRequestCreationTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.arguments_file = self.directory / "gh-arguments"
        fake_gh = self.directory / "gh"
        fake_gh.write_text(
            '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$GH_ARGUMENTS_FILE"\n',
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)
        self.environment = os.environ.copy()
        self.environment["PATH"] = f"{self.directory}{os.pathsep}{self.environment['PATH']}"
        self.environment["GH_ARGUMENTS_FILE"] = str(self.arguments_file)

    def run_task(self, body: str, *variables: str) -> subprocess.CompletedProcess[str]:
        body_file = self.directory / "body.md"
        body_file.write_text(body, encoding="utf-8")
        return subprocess.run(
            [
                "task",
                "--silent",
                "pr:create",
                "ISSUE=329",
                "TITLE=Standardize pull request creation",
                f"BODY_FILE={body_file}",
                *variables,
            ],
            check=False,
            capture_output=True,
            encoding="utf-8",
            env=self.environment,
        )

    def test_passes_complete_issue_metadata_to_github_cli(self) -> None:
        result = self.run_task(
            "## Summary\n\nCloses #329\n",
            "ASSIGNEES=alice,bob",
            "MILESTONE=v0.2.0",
            "DRAFT=true",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.arguments_file.read_text(encoding="utf-8").splitlines(),
            [
                "pr",
                "create",
                "--base",
                "master",
                "--title",
                "Standardize pull request creation",
                "--body-file",
                str(self.directory / "body.md"),
                "--project",
                "lzug Roadmap",
                "--assignee",
                "alice,bob",
                "--milestone",
                "v0.2.0",
                "--draft",
            ],
        )

    def test_rejects_body_without_exact_closing_reference(self) -> None:
        result = self.run_task("## Summary\n\nRelated to #329\n")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BODY_FILE must contain an exact 'Closes #329' line", result.stderr)
        self.assertFalse(self.arguments_file.exists())

    def test_accepts_exact_tracking_reference_for_external_activation_gates(self) -> None:
        result = self.run_task("## Summary\n\nTracks #329\n", "LINK_MODE=tracks")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.arguments_file.exists())

    def test_tracking_mode_rejects_a_closing_reference(self) -> None:
        result = self.run_task("## Summary\n\nCloses #329\n", "LINK_MODE=tracks")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BODY_FILE must contain an exact 'Tracks #329' line", result.stderr)
        self.assertFalse(self.arguments_file.exists())

    def test_omits_issue_metadata_that_is_not_set(self) -> None:
        result = self.run_task("## Summary\n\nCloses #329\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.arguments_file.read_text(encoding="utf-8").splitlines(),
            [
                "pr",
                "create",
                "--base",
                "master",
                "--title",
                "Standardize pull request creation",
                "--body-file",
                str(self.directory / "body.md"),
                "--project",
                "lzug Roadmap",
            ],
        )


if __name__ == "__main__":
    unittest.main()
