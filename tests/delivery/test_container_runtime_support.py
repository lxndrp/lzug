from __future__ import annotations

import unittest
from pathlib import Path


class ContainerRuntimeSupportTests(unittest.TestCase):
    def test_current_runtime_contract_is_docker_only(self) -> None:
        roots = (
            Path(".github/workflows"),
            Path("docs"),
            Path("operator-cli"),
            Path("scripts"),
            Path("tests/compatibility"),
            Path("tests/oci"),
        )
        files = [Path("Taskfile.yml"), Path("compose.yaml"), Path(".env.example")]
        for root in roots:
            files.extend(path for path in root.rglob("*") if path.is_file())

        findings = []
        for path in files:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "pod" + "man" in content.lower():
                findings.append(str(path))

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
