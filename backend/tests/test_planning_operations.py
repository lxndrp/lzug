"""Planning post-commit orchestration contracts."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from backend.application.planning_operations import PlanningOperations


class PlanningOperationsTests(unittest.TestCase):
    def test_reports_calendar_failure_without_raising_after_plan_commit(self) -> None:
        calendar = Mock()
        calendar.sync_round.side_effect = RuntimeError("calendar unavailable")
        operations = PlanningOperations(calendar)

        synced = operations.sync_confirmed_plan_calendar(42)

        self.assertFalse(synced)
        calendar.sync_round.assert_called_once_with(42)
