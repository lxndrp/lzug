"""Buffered unittest runner with compact slow-test diagnostics."""

from __future__ import annotations

import sys
import time
import unittest
from collections.abc import Iterable
from typing import override

SLOW_TEST_SECONDS = 1.0


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
    """Run the requested unittest discovery arguments with output buffering."""
    args = list(argv if argv is not None else sys.argv[1:])
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(args) if args else loader.discover("backend/tests")
    result = TimedTextTestRunner(verbosity=1, buffer=True).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
