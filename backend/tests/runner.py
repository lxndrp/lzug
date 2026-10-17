"""Buffered unittest runner with compact slow-test diagnostics."""

from __future__ import annotations

import argparse
import sys
import time
import unittest
from collections.abc import Iterable
from typing import override

from backend.tests.suites import TEST_MODULES_BY_TIER, TEST_TIERS

SLOW_TEST_SECONDS = 1.0


def partition_test_modules(modules: Iterable[str], shard_count: int) -> tuple[tuple[str, ...], ...]:
    """Balance independent test modules across deterministic test-count shards."""
    if shard_count < 2:
        raise ValueError("shard_count must be at least 2")

    loader = unittest.TestLoader()
    weighted_modules = [
        (loader.loadTestsFromName(f"backend.tests.{module}").countTestCases(), module)
        for module in modules
    ]
    if shard_count > len(weighted_modules):
        raise ValueError("shard_count cannot exceed the number of test modules")

    partitions: list[list[str]] = [[] for _ in range(shard_count)]
    weights = [0] * shard_count
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
        if elapsed >= SLOW_TEST_SECONDS:
            self.slow_tests.append((elapsed, test.id()))
        super().stopTest(test)

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.slow_tests: list[tuple[float, str]] = []


class TimedTextTestRunner(unittest.TextTestRunner):
    resultclass = TimedTextTestResult

    def run(self, test: unittest.suite.TestSuite):
        result = super().run(test)
        for elapsed, test_id in sorted(result.slow_tests, reverse=True):
            self.stream.writeln(f"slow {elapsed:.2f}s {test_id}")
        return result


def main(argv: Iterable[str] | None = None) -> int:
    """Run all tests, one declared tier, or explicitly named unittest targets."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=(*sorted(TEST_TIERS), "all"))
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int)
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
            partitions = partition_test_modules(modules, args.shard_count)
            modules = list(partitions[args.shard_index])
        targets = [f"backend.tests.{module}" for module in modules]
        suite = loader.loadTestsFromNames(targets)
    elif args.tests:
        suite = loader.loadTestsFromNames(args.tests)
    else:
        suite = loader.discover("backend/tests")
    result = TimedTextTestRunner(verbosity=1, buffer=True).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
