from __future__ import annotations

import unittest
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace

from backend.calendar.ports import (
    CalendarAssignmentSnapshot,
    CalendarEventSnapshot,
    CalendarFeedSnapshot,
    CalendarMembership,
    CalendarRoundSnapshot,
    CalendarScope,
    CalendarSlotSnapshot,
)
from backend.calendar.service import CalendarService


class _FakeCalendarStore:
    def __init__(self) -> None:
        self.feeds: dict[int, CalendarFeedSnapshot] = {}
        self.events: dict[int, CalendarEventSnapshot] = {}
        self.member_ids_by_person: dict[int, frozenset[int]] = {8: frozenset({12})}
        self._next_event_id = 1

    @contextmanager
    def __call__(self):
        before = deepcopy((self.feeds, self.events, self._next_event_id))
        try:
            yield self
        except Exception:
            self.feeds, self.events, self._next_event_id = before
            raise

    def feed_for_person(self, person_id: int):
        return self.feeds.get(person_id)

    def active_feed_for_token(self, token_hash: str):
        return next(
            (
                feed
                for feed in self.feeds.values()
                if feed.token_hash == token_hash and not feed.revoked_at
            ),
            None,
        )

    def save_feed(self, feed: CalendarFeedSnapshot) -> None:
        self.feeds[feed.person_id] = feed

    def revoke_feed(self, person_id: int, revoked_at: str) -> bool:
        feed = self.feeds.get(person_id)
        if feed is None or feed.revoked_at is not None:
            return False
        self.feeds[person_id] = replace(feed, revoked_at=revoked_at)
        return True

    def events_for_source(self, source_prefix: str):
        return tuple(
            event
            for event in self.events.values()
            if event.source_key == source_prefix or event.source_key.startswith(f"{source_prefix}:")
        )

    def events_for_round(self, round_id: int, *, person_id: int | None = None):
        member_ids = (
            self.member_ids_by_person.get(person_id, frozenset()) if person_id is not None else None
        )
        return tuple(
            event
            for event in self.events.values()
            if event.exam_round_id == round_id
            and (member_ids is None or event.recipient_member_id in member_ids)
        )

    def events_for_members_in_period(self, member_ids: frozenset[int], half_year_id: int):
        return tuple(
            event
            for event in self.events.values()
            if event.recipient_member_id in member_ids and event.exam_half_year_id == half_year_id
        )

    def event_for_members(self, event_id: int, member_ids: frozenset[int]):
        event = self.events.get(event_id)
        return event if event and event.recipient_member_id in member_ids else None

    def save_event(self, event: CalendarEventSnapshot):
        if event.id is None:
            event = replace(event, id=self._next_event_id)
            self._next_event_id += 1
        self.events[event.id] = event
        return event


class _FakePlanning:
    def __init__(self, snapshot: CalendarRoundSnapshot) -> None:
        self.snapshot = snapshot
        self.round_snapshot_calls: list[tuple[int, frozenset[int] | None]] = []

    def current_half_year_id(self):
        return self.snapshot.half_year_id

    def confirmed_round_ids(self, half_year_id: int):
        return (self.snapshot.id,) if half_year_id == self.snapshot.half_year_id else ()

    def round_snapshot(self, round_id: int, *, member_ids: frozenset[int] | None = None):
        self.round_snapshot_calls.append((round_id, member_ids))
        if round_id != self.snapshot.id:
            return None
        if member_ids is None:
            return self.snapshot
        return replace(
            self.snapshot,
            assignments=tuple(
                item for item in self.snapshot.assignments if item.member_id in member_ids
            ),
        )

    def assignment_snapshot(self, assignment_id: int):
        return next(
            (item for item in self.snapshot.assignments if item.id == assignment_id),
            None,
        )


class _FakeIdentity:
    def active_memberships(self, person_id: int):
        return (CalendarMembership(member_id=12, committee_id=3),) if person_id == 8 else ()

    def is_active(self, person_id: int):
        return bool(self.active_memberships(person_id))


def _round_snapshot() -> CalendarRoundSnapshot:
    slot = CalendarSlotSnapshot(
        id=31,
        starts_at="2026-11-16 09:00:00",
        ends_at="2026-11-16 10:00:00",
        status="confirmed",
        sequence_number=1,
    )
    assignment = CalendarAssignmentSnapshot(
        id=41,
        round_id=4,
        half_year_id=2,
        round_name="Winterprüfung",
        round_status="plan_confirmed",
        day_id=51,
        day_date="2026-11-16",
        day_status="confirmed",
        member_id=12,
        assignment_role="examiner",
        day_part="morning",
        room_name="Raum 1",
        room_building=None,
        room_wing=None,
        room_floor=None,
        room_number=None,
        room_access_notes=None,
        venue_name="Prüfungszentrum",
        venue_site_name=None,
        venue_street="Musterstraße 1",
        venue_postal_code="12345",
        venue_city="Musterstadt",
        venue_country="Deutschland",
        venue_entrance=None,
        venue_travel_directions=None,
        slots=(slot,),
    )
    return CalendarRoundSnapshot(
        id=4,
        half_year_id=2,
        name="Winterprüfung",
        status="plan_confirmed",
        assignments=(assignment,),
    )


class CalendarPortTests(unittest.TestCase):
    def test_calendar_use_case_uses_detached_ports_and_preserves_event_identity(self) -> None:
        planning = _FakePlanning(_round_snapshot())
        store = _FakeCalendarStore()
        identity = _FakeIdentity()
        service = CalendarService(store, planning, identity)

        self.assertEqual(1, service.sync_round(4))
        first = next(iter(store.events.values()))
        self.assertEqual(0, service.sync_round(4))
        self.assertEqual(
            first.external_event_id, next(iter(store.events.values())).external_event_id
        )

        assignment = planning.snapshot.assignments[0]
        planning.snapshot = replace(
            planning.snapshot,
            assignments=(
                replace(
                    assignment,
                    slots=(replace(assignment.slots[0], starts_at="2026-11-16 09:30:00"),),
                ),
            ),
        )
        self.assertEqual(1, service.sync_round(4))
        changed = next(iter(store.events.values()))
        self.assertEqual(first.id, changed.id)
        self.assertEqual(first.external_event_id, changed.external_event_id)
        self.assertEqual(first.version + 1, changed.version)
        self.assertEqual("updated", changed.status)

    def test_reads_use_only_currently_active_membership_ids(self) -> None:
        planning = _FakePlanning(_round_snapshot())
        store = _FakeCalendarStore()
        identity = _FakeIdentity()
        service = CalendarService(store, planning, identity)
        service.sync_round(4)
        active_event = next(iter(store.events.values()))
        withdrawn_event = replace(
            active_event,
            id=99,
            external_event_id="lzug-41-2",
            recipient_member_id=13,
            source_key="assignment:42:1",
        )
        store.events[withdrawn_event.id] = withdrawn_event

        events = service.list_events(CalendarScope(person_id=8, member_ids=frozenset({12})))

        self.assertEqual([active_event.id], [event.id for event in events])
        self.assertIsNone(
            service.event_ics(99, CalendarScope(person_id=8, member_ids=frozenset({12})))
        )

    def test_person_sync_requests_planning_snapshots_for_active_members_only(self) -> None:
        snapshot = _round_snapshot()
        other_assignment = replace(snapshot.assignments[0], id=42, member_id=13)
        planning = _FakePlanning(
            replace(snapshot, assignments=(*snapshot.assignments, other_assignment))
        )
        store = _FakeCalendarStore()
        service = CalendarService(store, planning, _FakeIdentity())

        self.assertEqual(1, service.sync_person(8))

        self.assertEqual([(4, frozenset({12}))], planning.round_snapshot_calls)
        self.assertEqual({12}, {event.recipient_member_id for event in store.events.values()})

    def test_person_sync_with_no_active_members_still_cancels_old_events(self) -> None:
        planning = _FakePlanning(_round_snapshot())
        store = _FakeCalendarStore()
        service = CalendarService(store, planning, _FakeIdentity())
        service.sync_round(4)
        store.member_ids_by_person[9] = frozenset({12})
        planning.round_snapshot_calls.clear()

        self.assertEqual(1, service.sync_person(9))

        self.assertEqual([(4, frozenset())], planning.round_snapshot_calls)
        self.assertEqual("cancelled", next(iter(store.events.values())).status)
