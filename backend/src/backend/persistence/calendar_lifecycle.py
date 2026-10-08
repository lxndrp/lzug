"""Calendar projection commands used by the shared round lifecycle UoW."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models import CalendarEvent


class SQLiteCalendarLifecycleWork:
    """Apply Calendar-owned event changes in a caller-owned transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def cancel_future_round_events(
        self, round_id: int, cutoff_date: str, now: str
    ) -> set[int]:
        recipients: set[int] = set()
        for event in self._session.scalars(
            select(CalendarEvent).where(
                CalendarEvent.exam_round_id == round_id,
                CalendarEvent.date >= cutoff_date,
                CalendarEvent.status != "cancelled",
            )
        ):
            event.status = "cancelled"
            event.version += 1
            event.updated_at = now
            recipients.add(event.recipient_member_id)
        return recipients
