"""Calendar projection commands used by the shared round lifecycle UoW."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models import CalendarEvent


class SQLiteCalendarLifecycleWork:
    """Apply Calendar-owned event changes in a caller-owned transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def cancel_future_round_events(self, round_id: int, cutoff_date: str, now: str) -> set[int]:
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

    def assignment_before_image(self, assignment_id: int) -> tuple[dict[str, object], ...]:
        """Materialize active generations before an assignment mutation.

        Cancelled generations are already durable Calendar state and cannot
        affect a later projection. Excluding them keeps immutable replay sources
        bounded across repeated cancellation and reopen cycles.
        """
        return tuple(
            {
                "id": event.id,
                "external_event_id": event.external_event_id,
                "exam_half_year_id": event.exam_half_year_id,
                "exam_round_id": event.exam_round_id,
                "exam_day_id": event.exam_day_id,
                "exam_day_assignment_id": event.exam_day_assignment_id,
                "recipient_member_id": event.recipient_member_id,
                "date": event.date,
                "starts_at": event.starts_at,
                "ends_at": event.ends_at,
                "time_zone": event.time_zone,
                "location": event.location,
                "role": event.role,
                "round_name": event.round_name,
                "secure_reference": event.secure_reference,
                "source_key": event.source_key,
                "version": event.version,
                "status": event.status,
                "content_hash": event.content_hash,
                "sent_at": event.sent_at,
            }
            for event in self._session.scalars(
                select(CalendarEvent)
                .where(
                    CalendarEvent.exam_day_assignment_id == assignment_id,
                    CalendarEvent.status != "cancelled",
                )
                .order_by(CalendarEvent.id)
            )
        )
