from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[2]
GUARD = ROOT / "scripts" / "check_ci_artifacts.py"


class CiArtifactGuardTest(unittest.TestCase):
    def run_guard(self, artifact_root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GUARD), str(artifact_root)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_rejects_sensitive_report_content(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact_root = Path(directory)
            (artifact_root / "report.html").write_text(
                "Authorization: Bearer example-token\n", encoding="utf-8"
            )

            result = self.run_guard(artifact_root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sensitive CI artifact content detected", result.stdout)

    def test_rejects_sensitive_trace_zip_content(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact_root = Path(directory)
            with zipfile.ZipFile(artifact_root / "trace.zip", "w") as archive:
                archive.writestr("trace.network", '"set-cookie": "session=example"')

            result = self.run_guard(artifact_root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sensitive CI artifact content detected", result.stdout)


if __name__ == "__main__":
    unittest.main()
