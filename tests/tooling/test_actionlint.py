from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class ActionlintContractTests(unittest.TestCase):
    def test_actionlint_accepts_repository_workflows_and_rejects_invalid_context(self) -> None:
        executable = shutil.which("actionlint")
        if executable is None:
            self.skipTest("actionlint is not installed")

        repository = Path(__file__).resolve().parents[2]
        valid = subprocess.run(
            [executable], cwd=repository, check=False, capture_output=True, text=True
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)

        with tempfile.TemporaryDirectory() as directory:
            workflow = Path(directory) / "invalid.yml"
            workflow.write_text(
                "\n".join(
                    (
                        "name: invalid",
                        "",
                        "on: push",
                        "",
                        "jobs:",
                        "  check:",
                        "    runs-on: ubuntu-24.04",
                        "    steps:",
                        "      - run: echo '${{ needs.missing.result }}'",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            invalid = subprocess.run(
                [executable, str(workflow)], check=False, capture_output=True, text=True
            )
            self.assertNotEqual(invalid.returncode, 0)


if __name__ == "__main__":
    unittest.main()
