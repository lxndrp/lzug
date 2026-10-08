"""Application-owned Calendar capabilities consumed by workflows and transport."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from backend.calendar.ports import (
        CalendarEventProjection,
        CalendarEventSnapshot,
        CalendarFeedActivation,
        CalendarFeedStatus,
        CalendarScope,
    )


class CalendarApplicationPort(Protocol):
    """Public Calendar capabilities consumed by Application use cases."""

    def status(self, scope: CalendarScope) -> CalendarFeedStatus: ...

    def list_events(self, scope: CalendarScope) -> Sequence[CalendarEventProjection]: ...

    def activate(self, scope: CalendarScope, *, rotate: bool = False) -> CalendarFeedActivation: ...

    def revoke(self, scope: CalendarScope) -> bool: ...

    def sync_person(self, person_id: int) -> int: ...

    def sync_round(self, round_id: int) -> int: ...

    def sync_assignment(
        self, assignment_id: int, *, future_from: date | None = None
    ) -> CalendarEventSnapshot | None: ...

    def event_for_assignment(
        self, assignment_id: int, recipient_member_id: int
    ) -> CalendarEventSnapshot | None: ...

    def cancel_assignment(self, round_id: int, assignment_id: int) -> int: ...

    def feed_ics(self, token: str) -> str | None: ...

    def event_ics(self, event_id: int, scope: CalendarScope) -> str | None: ...
