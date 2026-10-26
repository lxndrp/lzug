"""Buffered unittest runner with compact slow-test diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
import unittest
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import override

from backend.tests.suites import TEST_MODULES_BY_TIER, TEST_TIERS

SLOW_TEST_SECONDS = 1.0
HTTP_MODULE_TIMINGS = Path(__file__).with_name("http-module-timings.json")


def _recorded_http_module_seconds() -> dict[str, float]:
    """Read the committed Linux timings used to balance HTTP test modules."""
    try:
        payload = json.loads(HTTP_MODULE_TIMINGS.read_text(encoding="utf-8"))
        timings = payload["module_seconds"]
    except OSError, json.JSONDecodeError, KeyError, TypeError:
        return {}
    if not isinstance(timings, dict):
        return {}
    return {
        name: seconds
        for name, seconds in timings.items()
        if isinstance(name, str) and isinstance(seconds, (int, float)) and seconds > 0
    }


def partition_test_modules(modules: Iterable[str], shard_count: int) -> tuple[tuple[str, ...], ...]:
    """Balance HTTP modules by measured duration, estimating new modules by size."""
    loader = unittest.TestLoader()
    timings = _recorded_http_module_seconds()
    weighted_modules = [
        (
            loader.loadTestsFromName(f"backend.tests.{module}").countTestCases(),
            module,
        )
        for module in modules
    ]
    return partition_measured_modules(weighted_modules, timings, shard_count)


def partition_measured_modules(
    modules: Iterable[tuple[int, str]],
    module_seconds: dict[str, float],
    shard_count: int,
) -> tuple[tuple[str, ...], ...]:
    """Use measured module runtimes and estimate unseen modules from test counts."""
    modules = list(modules)
    measured_seconds_per_test = [
        module_seconds[module] / count
        for count, module in modules
        if module in module_seconds and count > 0
    ]
    fallback_seconds_per_test = (
        statistics.median(measured_seconds_per_test) if measured_seconds_per_test else 1.0
    )
    weights = [
        (module_seconds.get(module, count * fallback_seconds_per_test), module)
        for count, module in modules
    ]
    return partition_weighted_modules(weights, shard_count)


def partition_weighted_modules(
    weighted_modules: Iterable[tuple[float, str]], shard_count: int
) -> tuple[tuple[str, ...], ...]:
    """Partition named work items without importing the work being balanced."""
    weighted_modules = list(weighted_modules)
    if shard_count < 2:
        raise ValueError("shard_count must be at least 2")
    if shard_count > len(weighted_modules):
        raise ValueError("shard_count cannot exceed the number of test modules")

    partitions: list[list[str]] = [[] for _ in range(shard_count)]
    weights = [0.0] * shard_count
    for test_count, module in sorted(weighted_modules, key=lambda item: (-item[0], item[1])):
        shard = min(range(shard_count), key=lambda index: (weights[index], index))
        partitions[shard].append(module)
        weights[shard] += test_count

    return tuple(tuple(sorted(partition)) for partition in partitions)


class TimedTextTestResult(unittest.TextTestResult):
    """Retain unittest buffering while reporting only meaningfully slow tests."""

    @override
    def startTest(self, test: unittest.case.TestCase) -> None:
        self._started_at = time.perf_counter()
        super().startTest(test)

    @override
    def stopTest(self, test: unittest.case.TestCase) -> None:
        elapsed = time.perf_counter() - self._started_at
        self.test_timings.append(
            {"test": test.id(), "module": test.__class__.__module__, "seconds": elapsed}
        )
        if elapsed >= SLOW_TEST_SECONDS:
            self.slow_tests.append((elapsed, test.id()))
        super().stopTest(test)

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.slow_tests: list[tuple[float, str]] = []
        self.test_timings: list[dict[str, float | str]] = []


class TimedTextTestRunner(unittest.TextTestRunner):
    resultclass = TimedTextTestResult

    def run(self, test: unittest.suite.TestSuite):
        result = super().run(test)
        for elapsed, test_id in sorted(result.slow_tests, reverse=True):
            self.stream.writeln(f"slow {elapsed:.2f}s {test_id}")
        return result


def _timings_path(args: argparse.Namespace) -> Path | None:
    directory = os.environ.get("LZUG_TEST_TIMINGS_DIR")
    if not directory:
        return None
    suite = args.suite or "targets"
    shard = (
        f"-shard-{args.shard_index + 1}-of-{args.shard_count}"
        if args.shard_count is not None
        else ""
    )
    return Path(directory) / f"backend-{suite}{shard}.json"


def _write_timings(
    path: Path,
    result: TimedTextTestResult,
    elapsed: float,
    args: argparse.Namespace,
    started_at: datetime | None = None,
) -> None:
    modules: dict[str, list[float]] = defaultdict(list)
    for timing in result.test_timings:
        modules[str(timing["module"])].append(float(timing["seconds"]))
    failures = {test.id() for test, _ in result.failures}
    errors = {test.id() for test, _ in result.errors}
    skipped = {test.id() for test, _ in result.skipped}
    try:
        revision = os.environ.get("GITHUB_SHA")
        if not revision:
            import subprocess

            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
            ).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        revision = None
    payload = {
        "schema_version": 1,
        "revision": revision,
        "pull_request_head": os.environ.get("LZUG_TEST_TIMINGS_PR_HEAD"),
        "suite": args.suite or "targets",
        "shard": {"index": args.shard_index, "count": args.shard_count},
        "runner": {"platform": platform.platform(), "python": platform.python_version()},
        "started_at": (started_at or datetime.now(UTC)).isoformat(),
        "elapsed_seconds": elapsed,
        "test_count": result.testsRun,
        "modules": {
            name: {
                "test_count": len(seconds),
                "elapsed_seconds": sum(seconds),
                "tests": sorted(
                    (
                        {
                            "test": str(test["test"]),
                            "seconds": float(test["seconds"]),
                            "status": (
                                "failure"
                                if test["test"] in failures
                                else (
                                    "error"
                                    if test["test"] in errors
                                    else "skipped" if test["test"] in skipped else "passed"
                                )
                            ),
                        }
                        for test in result.test_timings
                        if test["module"] == name
                    ),
                    key=lambda item: item["test"],
                ),
            }
            for name, seconds in sorted(modules.items())
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: Iterable[str] | None = None) -> int:
    """Run all tests, one declared tier, or explicitly named unittest targets."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=(*sorted(TEST_TIERS), "all"))
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int)
    parser.add_argument("--timings-json", type=Path, help="Write machine-readable test timings")
    parser.add_argument("tests", nargs="*")
    args = parser.parse_args(list(argv if argv is not None else sys.argv[1:]))
    if args.suite and args.tests:
        parser.error("--suite cannot be combined with explicit test targets")
    if (args.shard_index is None) != (args.shard_count is None):
        parser.error("--shard-index and --shard-count must be supplied together")
    if args.shard_count is not None:
        if not args.suite or args.suite == "all":
            parser.error("shards require an explicit suite")
        if args.shard_count < 2 or args.shard_index not in range(args.shard_count):
            parser.error(
                "shard index must be within shard-count, and shard-count must be at least 2"
            )

    loader = unittest.TestLoader()
    if args.suite and args.suite != "all":
        modules = sorted(TEST_MODULES_BY_TIER[args.suite])
        if args.shard_count is not None:
            if args.shard_count > len(modules):
                parser.error(
                    f"shard-count cannot exceed the {len(modules)} modules in "
                    f"the {args.suite!r} suite"
                )
            partitions = partition_test_modules(modules, args.shard_count)
            modules = list(partitions[args.shard_index])
        targets = [f"backend.tests.{module}" for module in modules]
        suite = loader.loadTestsFromNames(targets)
    elif args.tests:
        suite = loader.loadTestsFromNames(args.tests)
    else:
        suite = loader.discover("backend/tests")
    runner = TimedTextTestRunner(verbosity=1, buffer=True)
    wall_started_at = datetime.now(UTC)
    started_at = time.perf_counter()
    result = runner.run(suite)
    elapsed = time.perf_counter() - started_at
    timings_path = args.timings_json or _timings_path(args)
    if timings_path is not None:
        _write_timings(timings_path, result, elapsed, args, wall_started_at)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
