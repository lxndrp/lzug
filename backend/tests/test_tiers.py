"""Keep backend test-tier selection complete, exclusive, and explicit."""

from __future__ import annotations

import ast
import contextlib
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from backend.tests.runner import (
    TimedTextTestRunner,
    _recorded_http_module_seconds,
    _timings_path,
    _write_timings,
    main,
    partition_measured_modules,
    partition_test_modules,
    partition_weighted_modules,
)
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
        shards = partition_weighted_modules([(1, module) for module in modules], 3)

        self.assertEqual(set().union(*map(set, shards)), modules)
        for index, shard in enumerate(shards):
            remaining = set().union(*(set(other) for other in shards[index + 1 :]))
            self.assertFalse(set(shard) & remaining)

    def test_weighted_sharding_balances_and_deterministically_assigns_modules(self) -> None:
        weights = [(7, "a"), (6, "b"), (5, "c"), (4, "d"), (3, "e"), (2, "f"), (1, "g")]

        first = partition_weighted_modules(weights, 3)
        second = partition_weighted_modules(weights, 3)
        totals = [sum(weight for weight, module in weights if module in shard) for shard in first]

        self.assertEqual(first, second)
        self.assertEqual(set().union(*map(set, first)), {module for _, module in weights})
        self.assertLessEqual(max(totals) - min(totals), 1)

    def test_measured_sharding_uses_duration_and_test_count_for_unmeasured_modules(self) -> None:
        modules = [(10, "slow"), (1, "small"), (1, "new")]

        first = partition_measured_modules(modules, {"slow": 20, "small": 1}, 2)
        second = partition_measured_modules(modules, {"slow": 20, "small": 1}, 2)

        self.assertEqual((("slow",), ("new", "small")), first)
        self.assertEqual(first, second)

    def test_http_shard_weights_reduce_the_measured_tail(self) -> None:
        modules = sorted(TEST_MODULES_BY_TIER["http"])
        loader = unittest.TestLoader()
        counts = {
            module: loader.loadTestsFromName(f"backend.tests.{module}").countTestCases()
            for module in modules
        }
        timings = _recorded_http_module_seconds()

        measured = partition_test_modules(modules, 3)
        count_only = partition_weighted_modules([(counts[module], module) for module in modules], 3)
        measured_loads = [sum(timings[module] for module in shard) for shard in measured]
        count_only_loads = [sum(timings[module] for module in shard) for shard in count_only]

        self.assertEqual(set(modules), set().union(*map(set, measured)))
        self.assertLess(max(measured_loads) - min(measured_loads), 0.2)
        self.assertGreater(max(count_only_loads) - min(count_only_loads), 8)

    def test_machine_readable_test_timings_include_module_and_runner_metadata(self) -> None:
        class TimedExample(unittest.TestCase):
            def test_example(self) -> None:
                self.assertTrue(True)

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(TimedExample)
        result = TimedTextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        args = Namespace(suite="http", shard_index=0, shard_count=3)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timings.json"
            with patch.dict("os.environ", {"GITHUB_SHA": "test-revision"}, clear=True):
                _write_timings(path, result, 0.01, args)
            report = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(1, report["schema_version"])
        self.assertEqual("test-revision", report["revision"])
        self.assertIsNone(report["pull_request_head"])
        self.assertEqual("http", report["suite"])
        self.assertEqual({"index": 0, "count": 3}, report["shard"])
        self.assertEqual(1, report["test_count"])
        module = __name__
        self.assertEqual(1, report["modules"][module]["test_count"])
        self.assertEqual(1, len(report["modules"][module]["tests"]))
        self.assertEqual("passed", report["modules"][module]["tests"][0]["status"])
        self.assertIn("python", report["runner"])

    def test_timing_directory_uses_unique_filename_for_each_http_shard(self) -> None:
        args = type("Args", (), {"suite": "http", "shard_index": 2, "shard_count": 3})()
        with patch.dict("os.environ", {"LZUG_TEST_TIMINGS_DIR": "/tmp/timings"}):
            self.assertEqual(
                Path("/tmp/timings/backend-http-shard-3-of-3.json"), _timings_path(args)
            )

    def test_shard_count_cannot_exceed_selected_suite_modules(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main(["--suite", "unit", "--shard-index", "0", "--shard-count", "20"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("shard-count cannot exceed", stderr.getvalue())

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
