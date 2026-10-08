"""SQLite adapters for the consumer-owned Calendar ports."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

from sqlalchemy import select

from backend.calendar.ports import (
    CalendarAssignmentSnapshot,
    CalendarEventSnapshot,
    CalendarFeedSnapshot,
    CalendarMembership,
    CalendarRoundSnapshot,
    CalendarSlotSnapshot,
)
from backend.persistence.database import (
    DEFAULT_DB_PATH,
    read_session_scope,
    session_scope,
)
from backend.persistence.models import (
    CalendarEvent,
    CalendarFeed,
    CommitteeMember,
    ExamDay,
    ExamDayAssignment,
    ExamHalfYear,
    ExamRoom,
    ExamRound,
    ExamSlot,
    ExamVenue,
)


def _event_snapshot(event: CalendarEvent) -> CalendarEventSnapshot:
    return CalendarEventSnapshot(
        id=event.id,
        external_event_id=event.external_event_id,
        exam_half_year_id=event.exam_half_year_id,
        exam_round_id=event.exam_round_id,
        exam_day_id=event.exam_day_id,
        exam_day_assignment_id=event.exam_day_assignment_id,
        recipient_member_id=event.recipient_member_id,
        date=event.date,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        time_zone=event.time_zone,
        location=event.location,
        role=event.role,
        round_name=event.round_name,
        source_key=event.source_key,
        version=event.version,
        status=event.status,
        content_hash=event.content_hash,
        sent_at=event.sent_at,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


class SQLiteCalendarUnitOfWork:
    """Calendar storage operations bound to one SQLAlchemy transaction."""

    def __init__(self, session) -> None:
        self._session = session

    def feed_for_person(self, person_id: int) -> CalendarFeedSnapshot | None:
        feed = self._session.scalars(
            select(CalendarFeed).where(CalendarFeed.person_id == person_id)
        ).first()
        return self._feed_snapshot(feed) if feed else None

    def active_feed_for_token(self, token_hash: str) -> CalendarFeedSnapshot | None:
        feed = self._session.scalars(
            select(CalendarFeed).where(
                CalendarFeed.token_hash == token_hash,
                CalendarFeed.revoked_at.is_(None),
            )
        ).first()
        return self._feed_snapshot(feed) if feed else None

    def save_feed(self, feed: CalendarFeedSnapshot) -> None:
        current = self._session.scalars(
            select(CalendarFeed).where(CalendarFeed.person_id == feed.person_id)
        ).first()
        if current is None:
            current = CalendarFeed(person_id=feed.person_id)
            self._session.add(current)
        current.token_hash = feed.token_hash
        current.created_at = feed.created_at
        current.revoked_at = feed.revoked_at
        self._session.flush()

    def revoke_feed(self, person_id: int, revoked_at: str) -> bool:
        feed = self._session.scalars(
            select(CalendarFeed).where(CalendarFeed.person_id == person_id)
        ).first()
        if feed is None or feed.revoked_at is not None:
            return False
        feed.revoked_at = revoked_at
        return True

    def events_for_source(self, source_prefix: str) -> Sequence[CalendarEventSnapshot]:
        events = self._session.scalars(
            select(CalendarEvent)
            .where(
                (CalendarEvent.source_key == source_prefix)
                | CalendarEvent.source_key.like(f"{source_prefix}:%")
            )
            .order_by(CalendarEvent.id)
        ).all()
        return tuple(_event_snapshot(event) for event in events)

    def events_for_round(
        self,
        round_id: int,
        *,
        person_id: int | None = None,
    ) -> Sequence[CalendarEventSnapshot]:
        query = select(CalendarEvent).where(CalendarEvent.exam_round_id == round_id)
        if person_id is not None:
            query = query.join(
                CommitteeMember, CommitteeMember.id == CalendarEvent.recipient_member_id
            ).where(CommitteeMember.person_id == person_id)
        events = self._session.scalars(query.order_by(CalendarEvent.id)).all()
        return tuple(_event_snapshot(event) for event in events)

    def events_for_members_in_period(
        self, member_ids: frozenset[int], half_year_id: int
    ) -> Sequence[CalendarEventSnapshot]:
        if not member_ids:
            return ()
        events = self._session.scalars(
            select(CalendarEvent)
            .where(
                CalendarEvent.recipient_member_id.in_(member_ids),
                CalendarEvent.exam_half_year_id == half_year_id,
            )
            .order_by(CalendarEvent.date, CalendarEvent.starts_at, CalendarEvent.id)
        ).all()
        return tuple(_event_snapshot(event) for event in events)

    def event_for_members(
        self, event_id: int, member_ids: frozenset[int]
    ) -> CalendarEventSnapshot | None:
        if not member_ids:
            return None
        event = self._session.scalars(
            select(CalendarEvent).where(
                CalendarEvent.id == event_id,
                CalendarEvent.recipient_member_id.in_(member_ids),
            )
        ).first()
        return _event_snapshot(event) if event else None

    def save_event(self, event: CalendarEventSnapshot) -> CalendarEventSnapshot:
        model = self._session.get(CalendarEvent, event.id) if event.id is not None else None
        if model is None:
            model = CalendarEvent()
            self._session.add(model)
        for field in (
            "external_event_id",
            "exam_half_year_id",
            "exam_round_id",
            "exam_day_id",
            "exam_day_assignment_id",
            "recipient_member_id",
            "date",
            "starts_at",
            "ends_at",
            "time_zone",
            "location",
            "role",
            "round_name",
            "source_key",
            "version",
            "status",
            "content_hash",
            "sent_at",
            "created_at",
            "updated_at",
        ):
            setattr(model, field, getattr(event, field))
        if event.exam_day_id is not None:
            model.secure_reference = f"/api/confirmed-plan-days/{event.exam_day_id}"
        self._session.flush()
        return _event_snapshot(model)

    @staticmethod
    def _feed_snapshot(feed: CalendarFeed) -> CalendarFeedSnapshot:
        return CalendarFeedSnapshot(
            person_id=feed.person_id,
            token_hash=feed.token_hash,
            created_at=feed.created_at,
            revoked_at=feed.revoked_at,
        )


class SQLiteCalendarPersistence:
    """Implement Calendar-owned snapshots and unit-of-work factories over SQLite."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def __call__(self) -> AbstractContextManager[SQLiteCalendarUnitOfWork]:
        return self._unit_of_work()

    @contextmanager
    def _unit_of_work(self):
        with session_scope(self.db_path) as session:
            yield SQLiteCalendarUnitOfWork(session)

    def current_half_year_id(self) -> int | None:
        with read_session_scope(self.db_path) as session:
            return session.scalars(
                select(ExamHalfYear.id)
                .where(ExamHalfYear.status == "active")
                .order_by(ExamHalfYear.year.desc(), ExamHalfYear.id.desc())
            ).first()

    def confirmed_round_ids(self, half_year_id: int) -> Sequence[int]:
        with read_session_scope(self.db_path) as session:
            return tuple(
                session.scalars(
                    select(ExamRound.id)
                    .where(
                        ExamRound.exam_half_year_id == half_year_id,
                        ExamRound.status == "plan_confirmed",
                    )
                    .order_by(ExamRound.id)
                ).all()
            )

    def round_snapshot(
        self, round_id: int, *, member_ids: frozenset[int] | None = None
    ) -> CalendarRoundSnapshot | None:
        with read_session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, round_id)
            if exam_round is None:
                return None
            half_year = session.get(ExamHalfYear, exam_round.exam_half_year_id)
            if half_year is None:
                return None
            assignments = ()
            if member_ids is None or member_ids:
                query = (
                    select(ExamDayAssignment)
                    .join(ExamDay, ExamDay.id == ExamDayAssignment.exam_day_id)
                    .where(ExamDay.exam_round_id == exam_round.id)
                )
                if member_ids is not None:
                    query = query.where(ExamDayAssignment.committee_member_id.in_(member_ids))
                assignments = session.scalars(query.order_by(ExamDayAssignment.id)).all()
            return CalendarRoundSnapshot(
                id=exam_round.id,
                half_year_id=half_year.id,
                name=exam_round.name,
                status=exam_round.status,
                assignments=tuple(
                    snapshot
                    for assignment in assignments
                    if (
                        snapshot := self._assignment_snapshot(
                            session, exam_round, half_year, assignment
                        )
                    )
                    is not None
                ),
            )

    def assignment_snapshot(self, assignment_id: int) -> CalendarAssignmentSnapshot | None:
        with read_session_scope(self.db_path) as session:
            assignment = session.get(ExamDayAssignment, assignment_id)
            if assignment is None:
                return None
            day = session.get(ExamDay, assignment.exam_day_id)
            exam_round = session.get(ExamRound, day.exam_round_id) if day else None
            half_year = (
                session.get(ExamHalfYear, exam_round.exam_half_year_id) if exam_round else None
            )
            if day is None or exam_round is None or half_year is None:
                return None
            return self._assignment_snapshot(session, exam_round, half_year, assignment)

    def active_memberships(self, person_id: int) -> Sequence[CalendarMembership]:
        with read_session_scope(self.db_path) as session:
            rows = session.execute(
                select(CommitteeMember.id, CommitteeMember.committee_id)
                .where(
                    CommitteeMember.person_id == person_id,
                    CommitteeMember.is_active == 1,
                )
                .order_by(CommitteeMember.id)
            ).all()
            return tuple(
                CalendarMembership(member_id=row.id, committee_id=row.committee_id) for row in rows
            )

    @staticmethod
    def _assignment_snapshot(
        session, exam_round, half_year, assignment
    ) -> CalendarAssignmentSnapshot | None:
        day = session.get(ExamDay, assignment.exam_day_id)
        if day is None:
            return None
        room = session.get(ExamRoom, day.room_id)
        venue = session.get(ExamVenue, room.venue_id) if room else None
        slots = session.scalars(
            select(ExamSlot)
            .where(ExamSlot.exam_day_id == day.id)
            .order_by(ExamSlot.starts_at, ExamSlot.sequence_number)
        ).all()
        return CalendarAssignmentSnapshot(
            id=assignment.id,
            round_id=exam_round.id,
            half_year_id=half_year.id,
            round_name=exam_round.name,
            round_status=exam_round.status,
            day_id=day.id,
            day_date=day.date,
            day_status=day.status,
            member_id=assignment.committee_member_id,
            assignment_role=assignment.assignment_role,
            day_part=assignment.day_part,
            room_name=room.name if room else None,
            room_building=room.building if room else None,
            room_wing=room.wing if room else None,
            room_floor=room.floor if room else None,
            room_number=room.room_number if room else None,
            room_access_notes=room.access_notes if room else None,
            venue_name=venue.name if venue else None,
            venue_site_name=venue.site_name if venue else None,
            venue_street=venue.street if venue else None,
            venue_postal_code=venue.postal_code if venue else None,
            venue_city=venue.city if venue else None,
            venue_country=venue.country if venue else None,
            venue_entrance=venue.entrance if venue else None,
            venue_travel_directions=venue.travel_directions if venue else None,
            slots=tuple(
                CalendarSlotSnapshot(
                    id=slot.id,
                    starts_at=slot.starts_at,
                    ends_at=slot.ends_at,
                    status=slot.status,
                    sequence_number=slot.sequence_number,
                )
                for slot in slots
            ),
        )
