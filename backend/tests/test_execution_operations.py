"""Application orchestration for Execution post-commit effects."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from backend.application.execution_operations import ExecutionOperations


class ExecutionOperationsTests(unittest.TestCase):
    def test_syncs_calendar_round_after_execution_write(self) -> None:
        calendar = Mock()
        operations = ExecutionOperations(calendar)

        synced = operations.sync_slot_status_calendar(42)

        self.assertTrue(synced)
        calendar.sync_round.assert_called_once_with(42)

    def test_reports_post_commit_calendar_failure_without_raising(self) -> None:
        calendar = Mock()
        calendar.sync_round.side_effect = RuntimeError("calendar unavailable")
        operations = ExecutionOperations(calendar)

        synced = operations.sync_slot_status_calendar(42)

        self.assertFalse(synced)
        calendar.sync_round.assert_called_once_with(42)
