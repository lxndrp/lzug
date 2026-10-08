"""Execution-owned Calendar operations used by lifecycle workflows."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from backend.calendar.ports import CalendarEventSnapshot


class ExecutionCalendarPort(Protocol):
    """Small Calendar capability set required by execution lifecycle use cases."""

    def sync_round(self, round_id: int) -> int: ...

    def sync_assignment(
        self, assignment_id: int, *, future_from: date | None = None
    ) -> CalendarEventSnapshot | None: ...
