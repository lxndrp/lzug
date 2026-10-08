"""Calendar-owned use cases over consumer-defined identity, Planning, and storage ports."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import replace
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.calendar.ics import render_calendar
from backend.calendar.ports import (
    CalendarAssignmentSnapshot,
    CalendarEventProjection,
    CalendarEventSnapshot,
    CalendarFeedActivation,
    CalendarFeedSnapshot,
    CalendarFeedStatus,
    CalendarIdentitySnapshotPort,
    CalendarPlanningSnapshotPort,
    CalendarRoundSnapshot,
    CalendarScope,
    CalendarSlotSnapshot,
    CalendarUnitOfWorkFactory,
)
from backend.settings import RuntimeSettings

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


class CalendarService:
    """Own feed lifecycle, event projection, and calendar-read side effects."""

    def __init__(
        self,
        unit_of_work_factory: CalendarUnitOfWorkFactory,
        planning: CalendarPlanningSnapshotPort,
        identity: CalendarIdentitySnapshotPort,
        *,
        time_zone: str | None = None,
        settings: RuntimeSettings | None = None,
    ) -> None:
        configured = settings or RuntimeSettings.from_environment()
        configured_zone = (
            time_zone or configured.calendar.time_zone or configured.calendar.fallback_time_zone
        )
        try:
            self.time_zone = ZoneInfo(configured_zone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown calendar time zone: {configured_zone}") from error
        self._unit_of_work_factory = unit_of_work_factory
        self._planning = planning
        self._identity = identity

    def status(self, scope: CalendarScope) -> CalendarFeedStatus:
        """Return only non-secret state for the authenticated person's feed."""
        if scope.person_id is None:
            return CalendarFeedStatus(False, None, None, self.time_zone.key)
        with self._unit_of_work_factory() as work:
            feed = work.feed_for_person(scope.person_id)
        return CalendarFeedStatus(
            active=bool(feed and feed.revoked_at is None),
            activated_at=feed.created_at if feed else None,
            revoked_at=feed.revoked_at if feed else None,
            time_zone=self.time_zone.key,
        )

    def list_events(self, scope: CalendarScope) -> tuple[CalendarEventProjection, ...]:
        """Refresh before reading and return current-period events in active scope."""
        if scope.person_id is None or not scope.member_ids:
            return ()
        self.sync_person(scope.person_id)
        half_year_id = self._planning.current_half_year_id()
        if half_year_id is None:
            return ()
        active_members = self._active_member_ids(scope.person_id)
        with self._unit_of_work_factory() as work:
            events = work.events_for_members_in_period(active_members, half_year_id)
        return tuple(self._event_view(event) for event in events if event.id is not None)

    def activate(self, scope: CalendarScope, *, rotate: bool = False) -> CalendarFeedActivation:
        """Create or rotate a feed and return the token exactly once to its owner."""
        if scope.person_id is None or not scope.member_ids:
            raise ValueError("A personal membership is required")
        token = secrets.token_urlsafe(32)
        now = _timestamp()
        with self._unit_of_work_factory() as work:
            feed = work.feed_for_person(scope.person_id)
            if feed and feed.revoked_at is None and not rotate:
                raise ValueError("Calendar feed is already active; rotate it to create a new URL")
            work.save_feed(
                CalendarFeedSnapshot(
                    person_id=scope.person_id,
                    token_hash=_digest(token),
                    created_at=now,
                    revoked_at=None,
                )
            )
        self.sync_person(scope.person_id)
        return CalendarFeedActivation(status=self.status(scope), token=token)

    def revoke(self, scope: CalendarScope) -> bool:
        if scope.person_id is None:
            return False
        with self._unit_of_work_factory() as work:
            return work.revoke_feed(scope.person_id, _timestamp())

    def sync_person(self, person_id: int) -> int:
        """Refresh current-period events; this write side effect is used by reads."""
        half_year_id = self._planning.current_half_year_id()
        if half_year_id is None:
            return 0
        active_members = self._active_member_ids(person_id)
        rounds = tuple(
            snapshot
            for round_id in self._planning.confirmed_round_ids(half_year_id)
            if (snapshot := self._planning.round_snapshot(round_id, member_ids=active_members))
            is not None
            and snapshot.status == "plan_confirmed"
        )
        with self._unit_of_work_factory() as work:
            return sum(
                self._sync_round(work, item, person_id=person_id, member_ids=active_members)
                for item in rounds
            )

    def sync_round(self, round_id: int) -> int:
        """Materialize confirmed assignments within one all-or-nothing Calendar UoW."""
        snapshot = self._planning.round_snapshot(round_id)
        if snapshot is None or snapshot.status != "plan_confirmed":
            return 0
        with self._unit_of_work_factory() as work:
            return self._sync_round(work, snapshot)

    def sync_assignment(
        self, assignment_id: int, *, future_from: date | None = None
    ) -> CalendarEventSnapshot | None:
        """Refresh one assignment and return a detached event projection."""
        assignment_snapshot = self._planning.assignment_snapshot(assignment_id)
        if assignment_snapshot is None or (
            future_from is not None and assignment_snapshot.day_date < future_from.isoformat()
        ):
            return None
        round_snapshot = self._planning.round_snapshot(assignment_snapshot.round_id)
        if round_snapshot is None:
            return None
        assignment = next(
            (item for item in round_snapshot.assignments if item.id == assignment_id), None
        )
        if assignment is None:
            return None
        with self._unit_of_work_factory() as work:
            self._sync_assignments(work, round_snapshot, (assignment,))
            return self._latest_event(
                work.events_for_source(f"assignment:{assignment_id}"), assignment.member_id
            )

    def cancel_assignment(self, round_id: int, assignment_id: int) -> int:
        """Cancel all event generations for one affected assignment."""
        self.sync_round(round_id)
        with self._unit_of_work_factory() as work:
            events = work.events_for_source(f"assignment:{assignment_id}")
            changed = 0
            for event in events:
                if event.status == "cancelled":
                    continue
                work.save_event(
                    replace(
                        event,
                        status="cancelled",
                        version=event.version + 1,
                        updated_at=_timestamp(),
                    )
                )
                changed += 1
            return changed

    def feed_ics(self, token: str) -> str | None:
        """Return the current-period feed for a valid token and active identity scope."""
        with self._unit_of_work_factory() as work:
            feed = work.active_feed_for_token(_digest(token))
        if feed is None:
            return None
        initial_members = self._active_member_ids(feed.person_id)
        if not initial_members:
            return None
        self.sync_person(feed.person_id)
        half_year_id = self._planning.current_half_year_id()
        if half_year_id is None:
            return render_calendar((), "Persönlicher Prüfungskalender")
        current_members = self._active_member_ids(feed.person_id)
        if not current_members:
            return None
        with self._unit_of_work_factory() as work:
            events = work.events_for_members_in_period(current_members, half_year_id)
        if not initial_members.intersection(current_members):
            return None
        return render_calendar(events, "Persönlicher Prüfungskalender")

    def event_ics(self, event_id: int, scope: CalendarScope) -> str | None:
        if scope.person_id is None or not scope.member_ids:
            return None
        self.sync_person(scope.person_id)
        current_members = self._active_member_ids(scope.person_id)
        if not current_members:
            return None
        with self._unit_of_work_factory() as work:
            event = work.event_for_members(event_id, current_members)
        return render_calendar((event,), "Prüfungstermin") if event else None

    def _sync_round(
        self,
        work,
        snapshot: CalendarRoundSnapshot,
        *,
        person_id: int | None = None,
        member_ids: frozenset[int] | None = None,
        assignment_ids: frozenset[int] | None = None,
    ) -> int:
        assignments = tuple(
            item
            for item in snapshot.assignments
            if (member_ids is None or item.member_id in member_ids)
            and (assignment_ids is None or item.id in assignment_ids)
        )
        changed, touched = self._sync_assignments(work, snapshot, assignments)
        if assignment_ids is not None:
            return changed
        existing = work.events_for_round(snapshot.id, person_id=person_id)
        for event in existing:
            prefix = event.source_key.rsplit(":", 1)[0]
            if prefix not in touched and event.status != "cancelled":
                work.save_event(
                    replace(
                        event,
                        status="cancelled",
                        version=event.version + 1,
                        updated_at=_timestamp(),
                    )
                )
                changed += 1
        return changed

    def _sync_assignments(
        self,
        work,
        snapshot: CalendarRoundSnapshot,
        assignments: tuple[CalendarAssignmentSnapshot, ...],
    ) -> tuple[int, set[str]]:
        touched: set[str] = set()
        changed = 0
        for assignment in assignments:
            prefix, count = self._sync_assignment(work, snapshot, assignment)
            if prefix is not None:
                touched.add(prefix)
            changed += count
        return changed, touched

    def _sync_assignment(
        self,
        work,
        round_snapshot: CalendarRoundSnapshot,
        assignment: CalendarAssignmentSnapshot,
    ) -> tuple[str | None, int]:
        section_slots = self._section_slots(assignment.slots, assignment.day_part)
        if not section_slots:
            return None, 0
        active_slots = tuple(slot for slot in section_slots if slot.status != "cancelled")
        prefix = f"assignment:{assignment.id}"
        events = tuple(work.events_for_source(prefix))
        event = self._latest_event(events, assignment.member_id)
        cancelled = assignment.day_status == "cancelled" or not active_slots
        event_slots = active_slots or section_slots
        if event and event.status == "cancelled" and not cancelled:
            event = None
        changed = 0
        for previous in events:
            if (
                previous.recipient_member_id != assignment.member_id
                and previous.status != "cancelled"
            ):
                work.save_event(
                    replace(
                        previous,
                        status="cancelled",
                        version=previous.version + 1,
                        updated_at=_timestamp(),
                    )
                )
                changed += 1
        generation = len(events) + 1 if event is None else None
        source_key = f"{prefix}:{generation}" if generation is not None else event.source_key
        payload = self._event_payload(
            round_snapshot,
            assignment,
            event_slots,
            cancelled,
            source_key,
            event.sent_at if event else _timestamp(),
        )
        changed += self._store_event(work, event, payload, assignment.id, generation, cancelled)
        return prefix, changed

    def _store_event(
        self,
        work,
        event: CalendarEventSnapshot | None,
        payload: dict[str, Any],
        assignment_id: int,
        generation: int | None,
        cancelled: bool,
    ) -> int:
        digest = hashlib.sha256(
            repr(sorted((key, value) for key, value in payload.items() if key != "sent_at")).encode(
                "utf-8"
            )
        ).hexdigest()
        now = _timestamp()
        if event is None:
            created = CalendarEventSnapshot(
                id=None,
                external_event_id=f"lzug-{assignment_id}-{generation}",
                exam_half_year_id=payload["exam_half_year_id"],
                exam_round_id=payload["exam_round_id"],
                exam_day_id=payload["exam_day_id"],
                exam_day_assignment_id=assignment_id,
                recipient_member_id=payload["recipient_member_id"],
                date=payload["date"],
                starts_at=payload["starts_at"],
                ends_at=payload["ends_at"],
                time_zone=payload["time_zone"],
                location=payload["location"],
                role=payload["role"],
                round_name=payload["round_name"],
                source_key=payload["source_key"],
                version=1,
                status="cancelled" if cancelled else "sent",
                content_hash=digest,
                sent_at=payload["sent_at"],
                created_at=now,
                updated_at=now,
            )
            work.save_event(created)
            return 1
        content_changed = event.content_hash != digest or (
            (event.status == "cancelled") != cancelled
        )
        status = event.status
        version = event.version
        if content_changed:
            version += 1
            status = "cancelled" if cancelled else "updated"
        updated = replace(
            event,
            external_event_id=event.external_event_id,
            exam_half_year_id=payload["exam_half_year_id"],
            exam_round_id=payload["exam_round_id"],
            exam_day_id=payload["exam_day_id"],
            exam_day_assignment_id=assignment_id,
            recipient_member_id=payload["recipient_member_id"],
            date=payload["date"],
            starts_at=payload["starts_at"],
            ends_at=payload["ends_at"],
            time_zone=payload["time_zone"],
            location=payload["location"],
            role=payload["role"],
            round_name=payload["round_name"],
            source_key=payload["source_key"],
            version=version,
            status=status,
            content_hash=digest,
            sent_at=payload["sent_at"],
            updated_at=now,
        )
        work.save_event(updated)
        return int(content_changed)

    def _event_payload(
        self,
        round_snapshot: CalendarRoundSnapshot,
        assignment: CalendarAssignmentSnapshot,
        slots: tuple[CalendarSlotSnapshot, ...],
        cancelled: bool,
        source_key: str,
        sent_at: str,
    ) -> dict[str, Any]:
        location = ", ".join(
            part
            for part in (
                assignment.venue_name,
                assignment.venue_site_name,
                assignment.room_name,
                assignment.room_building,
                assignment.room_wing,
                assignment.room_floor,
                assignment.room_number,
                assignment.venue_street,
                " ".join(
                    part for part in (assignment.venue_postal_code, assignment.venue_city) if part
                ),
                assignment.venue_country,
                assignment.venue_entrance,
                assignment.venue_travel_directions,
                assignment.room_access_notes,
            )
            if part
        )
        starts_at = min(slot.starts_at for slot in slots)
        ends_at = max(slot.ends_at for slot in slots)
        return {
            "exam_half_year_id": round_snapshot.half_year_id,
            "exam_round_id": round_snapshot.id,
            "exam_day_id": assignment.day_id,
            # These legacy hash inputs preserve idempotence for already stored events.
            # They remain private to the digest and do not cross a Calendar port.
            "exam_day_assignment_id": assignment.id,
            "secure_reference": f"/api/confirmed-plan-days/{assignment.day_id}",
            "recipient_member_id": assignment.member_id,
            "date": assignment.day_date,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "time_zone": self.time_zone.key,
            "location": location,
            "role": "Fallback" if assignment.assignment_role == "fallback" else "Regulärer Prüfer",
            "round_name": round_snapshot.name,
            "source_key": source_key,
            "status": "cancelled" if cancelled else "sent",
            "sent_at": sent_at,
        }

    @staticmethod
    def _latest_event(
        events: tuple[CalendarEventSnapshot, ...] | Any, member_id: int
    ) -> CalendarEventSnapshot | None:
        matching = (event for event in events if event.recipient_member_id == member_id)
        return max(matching, key=lambda event: event.id or 0, default=None)

    def _section_slots(
        self, slots: tuple[CalendarSlotSnapshot, ...], day_part: str
    ) -> tuple[CalendarSlotSnapshot, ...]:
        if day_part == "full_day":
            return slots
        boundary = time(12, 0)
        return tuple(
            slot
            for slot in slots
            if (_parse_local(slot.starts_at, self.time_zone).time() < boundary)
            == (day_part == "morning")
        )

    @staticmethod
    def _event_view(event: CalendarEventSnapshot) -> CalendarEventProjection:
        if event.id is None:
            raise ValueError("Persisted Calendar events must have an identifier")
        return CalendarEventProjection(
            id=event.id,
            external_event_id=event.external_event_id,
            date=event.date,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            time_zone=event.time_zone,
            location=event.location,
            role=event.role,
            round_name=event.round_name,
            status=event.status,
            version=event.version,
        )

    def _active_member_ids(self, person_id: int) -> frozenset[int]:
        return frozenset(
            membership.member_id for membership in self._identity.active_memberships(person_id)
        )

    def _calendar(self, events, name: str) -> str:
        """Compatibility helper for callers constructing a preview calendar."""
        return render_calendar(events, name)
