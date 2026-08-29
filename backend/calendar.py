"""Personal, provider-neutral calendar feeds and dataminimized ICS output."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from .authorization import AuthorizationScope
from .database import DEFAULT_DB_PATH, session_scope
from .models import (
    CalendarEvent,
    CalendarFeed,
    CommitteeMember,
    ExamDay,
    ExamDayAssignment,
    ExamHalfYear,
    ExamRound,
    ExamSlot,
    Location,
)

DEFAULT_TIME_ZONE = "Europe/Berlin"


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _now()).astimezone(UTC).isoformat(timespec="seconds")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_local(value: str, time_zone: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(value.replace(" ", "T"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=time_zone)
    return parsed.astimezone(time_zone)


def _ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


class CalendarService:
    """Own feed credential lifecycle, synchronization, and ICS serialization."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        time_zone: str | None = None,
        external_url: str | None = None,
    ):
        self.db_path = Path(db_path)
        configured_zone = (
            time_zone
            or os.environ.get("LZUG_CALENDAR_TIMEZONE")
            or os.environ.get("LZUG_TIMEZONE", DEFAULT_TIME_ZONE)
        )
        try:
            self.time_zone = ZoneInfo(configured_zone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown calendar time zone: {configured_zone}") from error
        self.external_url = (external_url or os.environ.get("LZUG_EXTERNAL_URL", "")).rstrip("/")

    def status(self, scope: AuthorizationScope) -> dict[str, Any]:
        """Return only non-secret state for the authenticated person's feed."""
        if scope.person_id is None:
            return {
                "active": False,
                "activated_at": None,
                "revoked_at": None,
                "time_zone": self.time_zone.key,
            }
        with session_scope(self.db_path) as session:
            feed = session.scalars(
                select(CalendarFeed).where(CalendarFeed.person_id == scope.person_id)
            ).first()
            return {
                "active": bool(feed and feed.revoked_at is None),
                "activated_at": feed.created_at if feed else None,
                "revoked_at": feed.revoked_at if feed else None,
                "time_zone": self.time_zone.key,
            }

    def list_events(self, scope: AuthorizationScope) -> list[dict[str, Any]]:
        """List only the authenticated person's current-half-year events."""
        if scope.person_id is None:
            return []
        self.sync_person(scope.person_id)
        with session_scope(self.db_path) as session:
            half_year = self._current_half_year(session)
            if half_year is None:
                return []
            events = session.scalars(
                select(CalendarEvent)
                .join(CommitteeMember, CommitteeMember.id == CalendarEvent.recipient_member_id)
                .where(
                    CommitteeMember.person_id == scope.person_id,
                    CalendarEvent.exam_half_year_id == half_year.id,
                )
                .order_by(CalendarEvent.date, CalendarEvent.starts_at, CalendarEvent.id)
            ).all()
            return [self._event_view(event) for event in events]

    def activate(self, scope: AuthorizationScope, *, rotate: bool = False) -> dict[str, Any]:
        """Create or rotate a feed and return the token exactly once to its owner."""
        if scope.person_id is None:
            raise ValueError("A personal membership is required")
        token = secrets.token_urlsafe(32)
        with session_scope(self.db_path) as session:
            feed = session.scalars(
                select(CalendarFeed).where(CalendarFeed.person_id == scope.person_id)
            ).first()
            if feed and feed.revoked_at is None and not rotate:
                raise ValueError("Calendar feed is already active; rotate it to create a new URL")
            if feed is None:
                feed = CalendarFeed(
                    person_id=scope.person_id,
                    token_hash=_digest(token),
                    created_at=_timestamp(),
                    revoked_at=None,
                )
                session.add(feed)
            else:
                feed.token_hash = _digest(token)
                feed.created_at = _timestamp()
                feed.revoked_at = None
            session.flush()
        self.sync_person(scope.person_id)
        return {**self.status(scope), "feed_url": self._feed_url(token)}

    def revoke(self, scope: AuthorizationScope) -> bool:
        if scope.person_id is None:
            return False
        with session_scope(self.db_path) as session:
            feed = session.scalars(
                select(CalendarFeed).where(CalendarFeed.person_id == scope.person_id)
            ).first()
            if feed is None or feed.revoked_at is not None:
                return False
            feed.revoked_at = _timestamp()
            return True

    def sync_person(self, person_id: int) -> int:
        """Refresh this person's current-half-year events without reading other people."""
        with session_scope(self.db_path) as session:
            half_year = self._current_half_year(session)
            if half_year is None:
                return 0
            rounds = session.scalars(
                select(ExamRound).where(
                    ExamRound.exam_half_year_id == half_year.id,
                    ExamRound.status == "plan_confirmed",
                )
            ).all()
            return sum(self._sync_round(session, item, person_id=person_id) for item in rounds)

    def sync_round(self, round_id: int) -> int:
        """Materialize all own-assignment events for a newly confirmed round."""
        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, round_id)
            if exam_round is None or exam_round.status != "plan_confirmed":
                return 0
            return self._sync_round(session, exam_round)

    def cancel_assignment(self, round_id: int, assignment_id: int) -> int:
        """Cancel only the calendar event for one affected assignment."""
        self.sync_round(round_id)
        prefix = f"assignment:{assignment_id}"
        with session_scope(self.db_path) as session:
            events = session.scalars(
                select(CalendarEvent).where(
                    (CalendarEvent.source_key == prefix)
                    | CalendarEvent.source_key.like(f"{prefix}:%")
                )
            ).all()
            changed = 0
            for event in events:
                if event.status == "cancelled":
                    continue
                event.status = "cancelled"
                event.version += 1
                event.updated_at = _timestamp()
                changed += 1
            return changed

    def feed_ics(self, token: str) -> str | None:
        """Return the current-half-year feed for a valid, active opaque token."""
        with session_scope(self.db_path) as session:
            feed = session.scalars(
                select(CalendarFeed).where(
                    CalendarFeed.token_hash == _digest(token), CalendarFeed.revoked_at.is_(None)
                )
            ).first()
            if feed is None or not self._person_is_active(session, feed.person_id):
                return None
            person_id = feed.person_id
        self.sync_person(person_id)
        with session_scope(self.db_path) as session:
            half_year = self._current_half_year(session)
            if half_year is None:
                return self._calendar([], "Persönlicher Prüfungskalender")
            events = session.scalars(
                select(CalendarEvent)
                .join(CommitteeMember, CommitteeMember.id == CalendarEvent.recipient_member_id)
                .where(
                    CommitteeMember.person_id == person_id,
                    CalendarEvent.exam_half_year_id == half_year.id,
                )
                .order_by(CalendarEvent.date, CalendarEvent.starts_at, CalendarEvent.id)
            ).all()
            return self._calendar(events, "Persönlicher Prüfungskalender")

    def event_ics(self, event_id: int, scope: AuthorizationScope) -> str | None:
        if not scope.member_ids:
            return None
        person_id = scope.person_id
        if person_id is None:
            return None
        self.sync_person(person_id)
        with session_scope(self.db_path) as session:
            event = session.scalars(
                select(CalendarEvent)
                .join(CommitteeMember, CommitteeMember.id == CalendarEvent.recipient_member_id)
                .where(CalendarEvent.id == event_id, CommitteeMember.person_id == person_id)
            ).first()
            return self._calendar([event], "Prüfungstermin") if event else None

    def _sync_round(
        self,
        session,
        exam_round: ExamRound,
        *,
        person_id: int | None = None,
    ) -> int:
        half_year = session.get(ExamHalfYear, exam_round.exam_half_year_id)
        if half_year is None:
            return 0
        assignments = session.scalars(
            select(ExamDayAssignment)
            .join(ExamDay, ExamDay.id == ExamDayAssignment.exam_day_id)
            .join(CommitteeMember, CommitteeMember.id == ExamDayAssignment.committee_member_id)
            .where(
                ExamDay.exam_round_id == exam_round.id,
                *([CommitteeMember.person_id == person_id] if person_id is not None else []),
            )
        ).all()
        touched: set[str] = set()
        changed = 0
        for assignment in assignments:
            day = session.get(ExamDay, assignment.exam_day_id)
            member = session.get(CommitteeMember, assignment.committee_member_id)
            if day is None or member is None:
                continue
            slots = session.scalars(
                select(ExamSlot)
                .where(ExamSlot.exam_day_id == day.id)
                .order_by(ExamSlot.starts_at, ExamSlot.sequence_number)
            ).all()
            section_slots = self._section_slots(slots, assignment.day_part)
            if not section_slots:
                continue
            active_section_slots = [slot for slot in section_slots if slot.status != "cancelled"]
            source_prefix = f"assignment:{assignment.id}"
            touched.add(source_prefix)
            event = self._latest_event(session, source_prefix, member.id)
            cancelled = day.status == "cancelled" or not active_section_slots
            event_slots = active_section_slots or section_slots
            if event and event.status == "cancelled" and not cancelled:
                event = None
            for previous in self._events_for_source(session, source_prefix):
                if previous.recipient_member_id != member.id and previous.status != "cancelled":
                    previous.status = "cancelled"
                    previous.version += 1
                    previous.updated_at = _timestamp()
                    changed += 1
            generation = self._next_generation(session, source_prefix) if event is None else None
            source_key = (
                f"{source_prefix}:{generation}" if generation is not None else event.source_key
            )
            payload = self._event_payload(
                session,
                exam_round,
                half_year,
                day,
                assignment,
                member,
                event_slots,
                cancelled,
                source_key,
                event.sent_at if event else _timestamp(),
            )
            digest_payload = {key: value for key, value in payload.items() if key != "sent_at"}
            digest = hashlib.sha256(
                repr(sorted(digest_payload.items())).encode("utf-8")
            ).hexdigest()
            if event is None:
                event = CalendarEvent(
                    **payload,
                    external_event_id=f"lzug-{assignment.id}-{generation}",
                    version=1,
                    content_hash=digest,
                    created_at=_timestamp(),
                )
                session.add(event)
                session.flush()
                changed += 1
            else:
                content_changed = event.content_hash != digest or (
                    (event.status == "cancelled") != cancelled
                )
                if content_changed:
                    event.version += 1
                    event.status = "cancelled" if cancelled else "updated"
                    changed += 1
                for key, value in payload.items():
                    if key == "status" and not content_changed:
                        continue
                    setattr(event, key, value)
                if content_changed and not cancelled:
                    event.status = "updated"
                event.content_hash = digest
                event.updated_at = _timestamp()

        existing = session.scalars(
            select(CalendarEvent).where(
                CalendarEvent.exam_round_id == exam_round.id,
                *(
                    [
                        CalendarEvent.recipient_member_id.in_(
                            select(CommitteeMember.id).where(CommitteeMember.person_id == person_id)
                        )
                    ]
                    if person_id is not None
                    else []
                ),
            )
        ).all()
        for event in existing:
            prefix = event.source_key.rsplit(":", 1)[0]
            if prefix not in touched and event.status != "cancelled":
                event.status = "cancelled"
                event.version += 1
                event.updated_at = _timestamp()
                changed += 1
        return changed

    def _event_payload(
        self,
        session,
        exam_round,
        half_year,
        day,
        assignment,
        member,
        slots,
        cancelled,
        source_key,
        sent_at,
    ):
        location = session.get(Location, day.location_id)
        location_text = ""
        if location:
            location_text = ", ".join(
                part
                for part in (
                    location.name,
                    location.room,
                    " ".join(part for part in (location.postal_code, location.city) if part),
                )
                if part
            )
        role = "Fallback" if assignment.assignment_role == "fallback" else "Regulärer Prüfer"
        starts_at = min(slot.starts_at for slot in slots)
        ends_at = max(slot.ends_at for slot in slots)
        return {
            "exam_half_year_id": half_year.id,
            "exam_round_id": exam_round.id,
            "exam_day_id": day.id,
            "exam_day_assignment_id": assignment.id,
            "recipient_member_id": member.id,
            "date": day.date,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "time_zone": self.time_zone.key,
            "location": location_text,
            "role": role,
            "round_name": exam_round.name,
            "secure_reference": f"/api/confirmed-plan-days/{day.id}",
            "source_key": source_key,
            "status": "cancelled" if cancelled else "sent",
            "sent_at": sent_at,
        }

    def _event_view(self, event: CalendarEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "external_event_id": event.external_event_id,
            "date": event.date,
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "time_zone": event.time_zone,
            "location": event.location,
            "role": event.role,
            "round_name": event.round_name,
            "status": event.status,
            "version": event.version,
            "download_url": f"/api/calendar/events/{event.id}.ics",
        }

    def _latest_event(self, session, prefix: str, member_id: int):
        return session.scalars(
            select(CalendarEvent)
            .where(
                CalendarEvent.recipient_member_id == member_id,
                (CalendarEvent.source_key == prefix) | CalendarEvent.source_key.like(f"{prefix}:%"),
            )
            .order_by(CalendarEvent.id.desc())
        ).first()

    @staticmethod
    def _events_for_source(session, prefix: str):
        return session.scalars(
            select(CalendarEvent).where(
                (CalendarEvent.source_key == prefix) | CalendarEvent.source_key.like(f"{prefix}:%")
            )
        ).all()

    def _next_generation(self, session, prefix: str) -> int:
        return len(self._events_for_source(session, prefix)) + 1

    def _section_slots(self, slots: list[ExamSlot], day_part: str) -> list[ExamSlot]:
        if day_part == "full_day":
            return slots
        boundary = time(12, 0)
        return [
            slot
            for slot in slots
            if (_parse_local(slot.starts_at, self.time_zone).time() < boundary)
            == (day_part == "morning")
        ]

    @staticmethod
    def _current_half_year(session) -> ExamHalfYear | None:
        return session.scalars(
            select(ExamHalfYear)
            .where(ExamHalfYear.status == "active")
            .order_by(ExamHalfYear.year.desc(), ExamHalfYear.id.desc())
        ).first()

    @staticmethod
    def _person_is_active(session, person_id: int) -> bool:
        return bool(
            session.scalars(
                select(CommitteeMember.id).where(
                    CommitteeMember.person_id == person_id, CommitteeMember.is_active == 1
                )
            ).first()
        )

    def _feed_url(self, token: str) -> str:
        path = f"/api/calendar/feed/{token}.ics"
        return f"{self.external_url}{path}" if self.external_url else path

    def _calendar(self, events: list[CalendarEvent], name: str) -> str:
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//lzug//Personal Calendar//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{_ics_escape(name)}",
        ]
        for event in events:
            zone = ZoneInfo(event.time_zone)
            start = _parse_local(event.starts_at, zone)
            end = _parse_local(event.ends_at, zone)
            description = f"Rolle: {event.role}\nDetails: {event.secure_reference}"
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{_ics_escape(event.external_event_id)}@lzug",
                    f"SEQUENCE:{event.version}",
                    f"DTSTAMP:{_now().strftime('%Y%m%dT%H%M%SZ')}",
                    f"DTSTART;TZID={event.time_zone}:{start.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND;TZID={event.time_zone}:{end.strftime('%Y%m%dT%H%M%S')}",
                    f"SUMMARY:{_ics_escape(event.round_name + ' – ' + event.role)}",
                    f"LOCATION:{_ics_escape(event.location)}",
                    f"DESCRIPTION:{_ics_escape(description)}",
                    f"STATUS:{'CANCELLED' if event.status == 'cancelled' else 'CONFIRMED'}",
                    "END:VEVENT",
                ]
            )
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"
