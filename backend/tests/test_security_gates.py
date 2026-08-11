from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from scripts.enforce_sarif_security import findings, sarif_paths


def sarif(severity: str | None) -> dict:
    properties = {} if severity is None else {"security-severity": severity}
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "test",
                        "rules": [{"id": "test/rule", "properties": properties}],
                    }
                },
                "results": [
                    {
                        "ruleId": "test/rule",
                        "ruleIndex": 0,
                        "message": {"text": "Synthetic finding"},
                    }
                ],
            }
        ],
    }


class SarifSecurityGateTests(unittest.TestCase):
    def test_high_findings_block_and_lower_findings_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.sarif"
            target.write_text(json.dumps(sarif("9.8")), encoding="utf-8")
            self.assertEqual([("result.sarif", "Synthetic finding", 9.8)], findings([target], 7.0))

            target.write_text(json.dumps(sarif("6.9")), encoding="utf-8")
            self.assertEqual([], findings([target], 7.0))

    def test_missing_security_severity_is_not_misclassified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.sarif"
            target.write_text(json.dumps(sarif(None)), encoding="utf-8")

            self.assertEqual([target], sarif_paths(Path(directory)))
            self.assertEqual([], findings([target], 7.0))

    def test_security_workflow_uses_blocking_gates_and_full_action_shas(self) -> None:
        workflow = Path(".github/workflows/security.yml").read_text(encoding="utf-8")
        action_refs = re.findall(r"^\s*uses:\s*[^@\s]+@([^\s]+)", workflow, re.MULTILINE)

        self.assertTrue(action_refs)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))
        self.assertIn('exit-code: "1"', workflow)
        self.assertIn("scanners: secret,misconfig", workflow)
        self.assertIn("scanners: vuln,secret,misconfig", workflow)
        self.assertIn("format: cyclonedx", workflow)
        self.assertIn("security-events: write", workflow)
        self.assertIn('python-version: "3.14.6"', workflow)
        self.assertIn('scripts/container-smoke.sh "$IMAGE_REF"', workflow)

        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("LZUG_AUTH_RATE_LIMIT=", dockerfile)
        self.assertNotIn("LZUG_AUTH_RATE_WINDOW_SECONDS=", dockerfile)


if __name__ == "__main__":
    unittest.main()
