"""Application orchestration for Planning post-commit effects."""

from __future__ import annotations

from backend.application.calendar_ports import CalendarApplicationPort


class PlanningOperations:
    """Run Calendar follow-up work after a Planning command has committed."""

    def __init__(self, calendar: CalendarApplicationPort) -> None:
        self._calendar = calendar

    def sync_confirmed_plan_calendar(self, round_id: int) -> bool:
        """Refresh confirmed plan projections; return whether refresh succeeded."""
        try:
            self._calendar.sync_round(round_id)
        except Exception:
            return False
        return True
