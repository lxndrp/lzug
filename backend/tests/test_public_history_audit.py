from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
AUDIT_SCRIPT = ROOT / "scripts" / "audit-public-history.py"


class PublicHistoryAuditTest(unittest.TestCase):
    def git(self, repository: Path, *args: str, env: dict[str, str] | None = None) -> None:
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "-C", repository, *args],
            check=True,
            capture_output=True,
            env=env,
        )

    def test_report_detects_history_without_disclosing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            self.git(repository, "init", "--initial-branch=master")

            env = os.environ.copy()
            env.update(
                {
                    "GIT_AUTHOR_NAME": "Audit Test",
                    "GIT_AUTHOR_EMAIL": "audit@example.invalid",
                    "GIT_COMMITTER_NAME": "Audit Test",
                    "GIT_COMMITTER_EMAIL": "audit@example.invalid",
                }
            )
            sensitive_value = "Known Readiness Person"
            historical = repository / "historical.txt"
            historical.write_text(
                f"{sensitive_value}\nknown.person@example.invalid\nTeststraße 12\n"
            )
            (repository / "historical.sqlite3").write_bytes(
                b"SQLite format 3\0" + sensitive_value.encode()
            )
            self.git(repository, "add", "historical.txt", "historical.sqlite3", env=env)
            self.git(repository, "commit", "-m", "Add historical fixture", env=env)
            self.git(repository, "branch", "audit/ref", env=env)
            historical.unlink()
            self.git(repository, "add", "historical.txt", env=env)
            self.git(repository, "commit", "-m", "Delete historical fixture", env=env)

            known_values = root / "known-values.txt"
            known_values.write_text(sensitive_value + "\n")
            report_path = root / "report.json"
            subprocess.run(
                [
                    sys.executable,
                    AUDIT_SCRIPT,
                    "--git-dir",
                    repository / ".git",
                    "--known-values",
                    known_values,
                    "--output",
                    report_path,
                ],
                check=True,
                capture_output=True,
            )

            serialized = report_path.read_text()
            report = json.loads(serialized)
            self.assertNotIn(sensitive_value, serialized)
            self.assertNotIn("known.person@example.invalid", serialized)
            self.assertEqual(1, report["known_readiness_values_matched"])
            self.assertGreater(
                report["binary_content_findings"]["known_readiness_value"]["occurrences"], 0
            )
            self.assertGreater(report["deleted_files"]["unique_paths"], 0)
            self.assertEqual(2, report["refs"]["counts"]["heads"])
            self.assertEqual(2, report["affected_refs"]["known_readiness_value"]["heads"])
            self.assertEqual(1, report["commit_identities"]["unique_email_domains"])
            self.assertGreater(report["diff_scan"]["findings"]["known_readiness_value"], 0)


if __name__ == "__main__":
    unittest.main()
