from __future__ import annotations

import unittest
from http import HTTPStatus
from unittest.mock import patch

from sqlalchemy import func, select

from backend.auth import AuthenticationRepository
from backend.authorization import AuthorizationScope
from backend.calendar import CalendarService
from backend.database import session_scope
from backend.exam_venue_api import ExamVenueApi
from backend.exam_venues import ExamVenueConfirmationRequiredError, ExamVenueService
from backend.models import (
    CalendarEvent,
    ConfirmedPlanRevision,
    ExamDay,
    ExamVenue,
    Notification,
    PlanConsequence,
    PlanConsequenceBatch,
)
from backend.planning import PlanningService
from backend.tests.fixture_data import FIXTURE_IDS, FIXTURE_ROOT
from backend.tests.helpers import ApiServer, TempDatabase, assert_status
from backend.venue_consequences import VenueConsequenceService


class VenueConsequenceTests(unittest.TestCase):
    @staticmethod
    def _confirmed_database():
        database = TempDatabase()
        db_path = database.__enter__()
        PlanningService(db_path).generate_proposal(1)
        PlanningService(db_path).confirm_plan(1)
        CalendarService(db_path).sync_round(1)
        return database, db_path

    def test_preview_and_meaningful_update_refresh_calendar_and_notify_members(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = ExamVenueService(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            payload = {
                "expected_revision": venue["revision"],
                "street": "Neue Straße 7",
                "entrance": "Treffpunkt Nord",
                "confirm_future_assignments": True,
            }
            impact = venues.future_impact(1, payload=payload)
            with session_scope(db_path) as session:
                before_events = {
                    event.id: (event.external_event_id, event.version)
                    for event in session.scalars(select(CalendarEvent))
                }
                plan_revision_count = session.scalar(
                    select(func.count()).select_from(ConfirmedPlanRevision)
                )

            result = venues.update_venue(1, payload, actor_member_id=1)
            assert result is not None

            with session_scope(db_path) as session:
                after_events = {
                    event.id: (event.external_event_id, event.version, event.location)
                    for event in session.scalars(select(CalendarEvent))
                }
                notices = session.scalars(
                    select(Notification).where(Notification.event_type == "exam_venue_changed")
                ).all()
                current_plan_revision_count = session.scalar(
                    select(func.count()).select_from(ConfirmedPlanRevision)
                )

            self.assertGreater(impact["count"], 0)
            self.assertEqual(impact["count"], impact["calendar"]["event_count"])
            self.assertGreater(impact["notifications"]["recipient_count"], 0)
            self.assertEqual(set(before_events), set(after_events))
            for event_id, (external_id, version) in before_events.items():
                self.assertEqual(external_id, after_events[event_id][0])
                self.assertEqual(version + 1, after_events[event_id][1])
                self.assertIn("Neue Straße 7", after_events[event_id][2])
                self.assertIn("Treffpunkt Nord", after_events[event_id][2])
            self.assertEqual(impact["notifications"]["recipient_count"], len(notices))
            self.assertEqual(plan_revision_count, current_plan_revision_count)
            self.assertNotIn("consequence_warning", result)
        finally:
            database.__exit__(None, None, None)

    def test_non_triggers_and_spelling_correction_do_not_notify(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = ExamVenueService(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            coordinate_impact = venues.future_impact(
                1,
                payload={
                    "expected_revision": venue["revision"],
                    "latitude": 53.5,
                    "longitude": 10.0,
                    "coordinate_status": "confirmed",
                    "coordinate_source": "manual",
                },
            )
            self.assertEqual(0, coordinate_impact["calendar"]["event_count"])
            self.assertEqual(0, coordinate_impact["notifications"]["recipient_count"])

            corrected = venues.future_impact(
                1,
                payload={
                    "expected_revision": venue["revision"],
                    "name": "Hof Athen synthetisch",
                    "meaningful_change": False,
                },
            )
            self.assertGreater(corrected["calendar"]["event_count"], 0)
            self.assertEqual(0, corrected["notifications"]["recipient_count"])
        finally:
            database.__exit__(None, None, None)

    def test_every_documented_trigger_and_non_trigger_is_classified(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = VenueConsequenceService(db_path)
            venue = ExamVenueService(db_path).get_venue(1)
            assert venue is not None
            room_id = FIXTURE_IDS[f"{FIXTURE_ROOT}.room.zappeion.theseus"]["id"]
            room = next(item for item in venue["rooms"] if item["id"] == room_id)
            cases = (
                (
                    "venue",
                    venue["id"],
                    venue,
                    {
                        "name",
                        "street",
                        "postal_code",
                        "city",
                        "country",
                        "site_name",
                        "entrance",
                        "travel_directions",
                    },
                    {
                        "street",
                        "postal_code",
                        "city",
                        "country",
                        "site_name",
                        "entrance",
                        "travel_directions",
                        "is_accessible",
                        "accessibility_status",
                        "accessibility_notes",
                    },
                    {
                        "latitude",
                        "longitude",
                        "coordinate_status",
                        "coordinate_source",
                        "is_active",
                    },
                ),
                (
                    "room",
                    room["id"],
                    room,
                    {"name", "building", "wing", "floor", "room_number", "access_notes"},
                    {"name", "building", "wing", "floor", "room_number", "access_notes"},
                    {"capacity", "is_active"},
                ),
            )
            for entity_type, entity_id, before, calendar_fields, notice_fields, non_fields in cases:
                for field in sorted(calendar_fields | notice_fields | non_fields):
                    after = dict(before)
                    after[field] = self._different(after.get(field))
                    impact = service.preview(
                        venue_id=venue["id"],
                        entity_type=entity_type,
                        entity_id=entity_id,
                        before=before,
                        after=after,
                        meaningful_change=True,
                    )
                    self.assertEqual(
                        field in calendar_fields,
                        impact["calendar"]["event_count"] > 0,
                        field,
                    )
                    self.assertEqual(
                        field in notice_fields,
                        impact["notifications"]["recipient_count"] > 0,
                        field,
                    )
        finally:
            database.__exit__(None, None, None)

    @staticmethod
    def _different(value):
        if isinstance(value, int):
            return 0 if value else 1
        if isinstance(value, float):
            return value + 1
        if value is None:
            return "changed"
        return f"{value} changed"

    def test_past_events_remain_unchanged(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            with session_scope(db_path) as session:
                event = session.scalars(select(CalendarEvent).order_by(CalendarEvent.id)).first()
                assert event is not None
                day = session.get(ExamDay, event.exam_day_id)
                assert day is not None
                day.date = "2020-01-01"
                event.date = day.date
                past_event_id = event.id
                past_version = event.version

            venues = ExamVenueService(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            venues.update_venue(
                1,
                {
                    "expected_revision": venue["revision"],
                    "site_name": "Neuer Gebäudeteil",
                    "confirm_future_assignments": True,
                },
                actor_member_id=1,
            )
            with session_scope(db_path) as session:
                past = session.get(CalendarEvent, past_event_id)
                assert past is not None
                self.assertEqual(past_version, past.version)
                self.assertNotIn("Neuer Gebäudeteil", past.location)
        finally:
            database.__exit__(None, None, None)

    def test_failed_effect_does_not_roll_back_master_data_and_retry_is_current(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = ExamVenueService(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            with patch(
                "backend.venue_consequences.CalendarService.sync_assignment",
                side_effect=RuntimeError("simulated calendar failure"),
            ):
                result = venues.update_venue(
                    1,
                    {
                        "expected_revision": venue["revision"],
                        "site_name": "Gebäude B",
                        "confirm_future_assignments": True,
                    },
                    actor_member_id=1,
                )
            assert result is not None
            self.assertEqual("Gebäude B", result["site_name"])
            self.assertIn("consequence_warning", result)
            audit_id = result["consequence_audit_id"]
            self.assertTrue(VenueConsequenceService(db_path).problems_for_venue(1))

            with session_scope(db_path) as session:
                stored_venue = session.get(ExamVenue, 1)
                assert stored_venue is not None
                stored_venue.scope = "global"
                stored_venue.committee_id = None
            chair_scope = AuthorizationScope(
                person_id=1,
                person_ids=frozenset({1}),
                committee_ids=frozenset({1}),
                member_ids=frozenset({1}),
                management_committee_ids=frozenset({1}),
                member_by_committee={1: 1},
            )
            chair_view = ExamVenueApi(db_path).get_venue(1, chair_scope)
            assert chair_view is not None
            self.assertTrue(chair_view["consequence_problems"])
            self.assertFalse(chair_view["capabilities"]["retry_consequences"])
            member_scope = AuthorizationScope(
                person_id=1,
                person_ids=frozenset({1}),
                committee_ids=frozenset({1}),
                member_ids=frozenset({1}),
                management_committee_ids=frozenset(),
                member_by_committee={1: 1},
            )
            member_view = ExamVenueApi(db_path).get_venue(1, member_scope)
            assert member_view is not None
            self.assertEqual([], member_view["consequence_problems"])

            retried = VenueConsequenceService(db_path).retry_audit(audit_id)
            repeated = VenueConsequenceService(db_path).retry_audit(audit_id)
            with session_scope(db_path) as session:
                batch = session.scalar(
                    select(PlanConsequenceBatch).where(
                        PlanConsequenceBatch.origin_type == "exam_venue_audit_event",
                        PlanConsequenceBatch.origin_key == str(audit_id),
                    )
                )
                assert batch is not None
                task_count = session.scalar(
                    select(func.count())
                    .select_from(PlanConsequence)
                    .where(PlanConsequence.batch_id == batch.id)
                )

            self.assertEqual(0, retried["problems"])
            self.assertEqual(retried["processed"], repeated["processed"])
            self.assertEqual(retried["processed"], task_count)
        finally:
            database.__exit__(None, None, None)

    def test_retry_supersedes_an_effect_after_a_newer_relevant_change(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = ExamVenueService(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            with patch(
                "backend.venue_consequences.CalendarService.sync_assignment",
                side_effect=RuntimeError("simulated calendar failure"),
            ):
                failed = venues.update_venue(
                    1,
                    {
                        "expected_revision": venue["revision"],
                        "site_name": "Zwischenstand",
                        "confirm_future_assignments": True,
                    },
                    actor_member_id=1,
                )
            assert failed is not None
            current = venues.get_venue(1)
            assert current is not None
            venues.update_venue(
                1,
                {
                    "expected_revision": current["revision"],
                    "site_name": "Aktueller Stand",
                    "confirm_future_assignments": True,
                },
                actor_member_id=1,
            )

            old = VenueConsequenceService(db_path).retry_audit(failed["consequence_audit_id"])
            self.assertGreater(old["superseded"], 0)
            self.assertEqual(0, old["problems"])
        finally:
            database.__exit__(None, None, None)

    def test_abort_requires_confirmation_before_master_data_change(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = ExamVenueService(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            with self.assertRaises(ExamVenueConfirmationRequiredError):
                venues.update_venue(
                    1,
                    {"expected_revision": venue["revision"], "entrance": "Eingang West"},
                    actor_member_id=1,
                )
            unchanged = venues.get_venue(1)
            assert unchanged is not None
            self.assertEqual(venue["revision"], unchanged["revision"])
            self.assertEqual(venue["entrance"], unchanged["entrance"])
        finally:
            database.__exit__(None, None, None)


class VenueConsequenceApiTests(unittest.TestCase):
    def test_preview_failure_visibility_and_controlled_retry(self) -> None:
        with TempDatabase() as db_path:
            PlanningService(db_path).generate_proposal(1)
            PlanningService(db_path).confirm_plan(1)
            CalendarService(db_path).sync_round(1)
            venues = ExamVenueService(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            payload = {
                "expected_revision": venue["revision"],
                "site_name": "Gebäude API",
                "confirm_future_assignments": True,
            }
            auth = AuthenticationRepository(db_path)
            operator = auth.create_account("operator@example.invalid", is_operator=True)
            operator_session = auth.create_session(operator["id"])
            with ApiServer(db_path) as api:
                status, impact = api.request(
                    "POST",
                    "/api/exam-venues/1/change-impact",
                    payload,
                    credentials=operator_session,
                )
                assert_status(status, HTTPStatus.OK)
                self.assertGreater(impact["calendar"]["event_count"], 0)
                self.assertGreater(impact["notifications"]["recipient_count"], 0)

                with patch(
                    "backend.venue_consequences.CalendarService.sync_assignment",
                    side_effect=RuntimeError("simulated calendar failure"),
                ):
                    status, changed = api.request(
                        "PATCH",
                        "/api/exam-venues/1",
                        payload,
                        credentials=operator_session,
                    )
                assert_status(status, HTTPStatus.OK)
                self.assertEqual("Gebäude API", changed["site_name"])
                self.assertIn("consequence_warning", changed)

                status, visible = api.request(
                    "GET", "/api/exam-venues/1", credentials=operator_session
                )
                assert_status(status, HTTPStatus.OK)
                problems = visible["consequence_problems"]
                self.assertTrue(problems)
                audit_id = problems[0]["audit_id"]

                status, retried = api.request(
                    "POST",
                    f"/api/exam-venue-changes/{audit_id}/consequences/retry",
                    {},
                    credentials=operator_session,
                )
                assert_status(status, HTTPStatus.OK)
                self.assertEqual(0, retried["problems"])

                status, visible = api.request(
                    "GET", "/api/exam-venues/1", credentials=operator_session
                )
                assert_status(status, HTTPStatus.OK)
                self.assertEqual([], visible["consequence_problems"])


if __name__ == "__main__":
    unittest.main()
