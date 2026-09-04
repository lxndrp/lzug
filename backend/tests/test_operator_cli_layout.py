from __future__ import annotations

import unittest
from pathlib import Path


class OperatorCliLayoutTests(unittest.TestCase):
    def test_go_module_and_sources_are_owned_by_operator_cli(self) -> None:
        for legacy_path in ("cmd", "internal", "go.mod", "go.sum", ".goreleaser.yml"):
            with self.subTest(path=legacy_path):
                self.assertFalse(Path(legacy_path).exists())

        module_root = Path("operator-cli")
        self.assertIn(
            "module github.com/lxndrp/lzug/operator-cli",
            (module_root / "go.mod").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            ["lzug-admin"],
            sorted(path.name for path in (module_root / "cmd").iterdir()),
        )
        self.assertTrue((module_root / "internal/admincli").is_dir())
        self.assertTrue((module_root / "internal/tools/cli-reference").is_dir())
        self.assertTrue((module_root / ".goreleaser.yml").is_file())


if __name__ == "__main__":
    unittest.main()
