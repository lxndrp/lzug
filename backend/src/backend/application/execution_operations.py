"""Application orchestration for execution-owned post-commit effects."""

from __future__ import annotations

from backend.application.calendar_ports import CalendarApplicationPort


class ExecutionOperations:
    """Run Calendar follow-up work after an Execution command has committed."""

    def __init__(self, calendar: CalendarApplicationPort) -> None:
        self._calendar = calendar

    def sync_slot_status_calendar(self, round_id: int) -> bool:
        """Refresh a round after a slot status write; return whether it succeeded."""
        try:
            self._calendar.sync_round(round_id)
        except Exception:
            return False
        return True
