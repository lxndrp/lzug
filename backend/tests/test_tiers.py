"""Keep backend test-tier selection complete, exclusive, and explicit."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from backend.tests.runner import partition_test_modules
from backend.tests.suites import TEST_MODULES_BY_TIER

TEST_ROOT = Path(__file__).resolve().parent


class BackendTestTierTests(unittest.TestCase):
    def test_every_test_module_belongs_to_exactly_one_tier(self) -> None:
        configured = [module for modules in TEST_MODULES_BY_TIER.values() for module in modules]
        discovered = {path.stem for path in TEST_ROOT.glob("test_*.py") if path.is_file()}

        self.assertEqual(len(configured), len(set(configured)))
        self.assertEqual(discovered, set(configured))

    def test_http_contract_parity_belongs_to_http_tier(self) -> None:
        self.assertIn("test_http_contract_parity", TEST_MODULES_BY_TIER["http"])
        self.assertNotIn("test_http_contract_parity", TEST_MODULES_BY_TIER["component"])

    def test_http_tier_shards_are_complete_and_non_overlapping(self) -> None:
        modules = TEST_MODULES_BY_TIER["http"]
        shards = partition_test_modules(modules, 2)

        self.assertEqual(set().union(*map(set, shards)), modules)
        self.assertFalse(set(shards[0]) & set(shards[1]))

    def test_unit_tier_does_not_include_modules_using_runtime_adapters(self) -> None:
        forbidden_modules = {
            "backend.tests.helpers",
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
                    if node.module == "backend.tests" and any(
                        alias.name == "helpers" for alias in node.names
                    ):
                        imports.add("backend.tests.helpers")
                    if node.module == "backend.tests.helpers":
                        helpers.update(alias.name for alias in node.names)

            with self.subTest(module=module):
                self.assertFalse(forbidden_modules & imports)
                self.assertFalse(forbidden_helpers & helpers)
