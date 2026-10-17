"""Keep backend test-tier selection complete, exclusive, and explicit."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from backend.tests.suites import TEST_MODULES_BY_TIER

TEST_ROOT = Path(__file__).resolve().parent


class BackendTestTierTests(unittest.TestCase):
    def test_every_test_module_belongs_to_exactly_one_tier(self) -> None:
        configured = [module for modules in TEST_MODULES_BY_TIER.values() for module in modules]
        discovered = {path.stem for path in TEST_ROOT.glob("test_*.py") if path.is_file()}

        self.assertEqual(len(configured), len(set(configured)))
        self.assertEqual(discovered, set(configured))

    def test_unit_tier_does_not_include_modules_using_runtime_adapters(self) -> None:
        forbidden_modules = {
            "fastapi.testclient",
            "sqlite3",
            "sqlalchemy",
            "subprocess",
            "socket",
        }
        forbidden_helpers = {"ApiServer", "FastAPIAdapter", "TempDatabase"}

        for module in sorted(TEST_MODULES_BY_TIER["unit"]):
            path = TEST_ROOT / f"{module}.py"
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports: set[str] = set()
            helpers: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.add(node.module or "")
                    if node.module == "backend.tests.helpers":
                        helpers.update(alias.name for alias in node.names)

            with self.subTest(module=module):
                self.assertFalse(forbidden_modules & imports)
                self.assertFalse(forbidden_helpers & helpers)
