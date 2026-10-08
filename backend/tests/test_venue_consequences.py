from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.composition import calendar_service as create_calendar_service
from backend.composition import planning_service
from backend.identity.authorization import AuthorizationScope
from backend.notifications.service import NotificationService
from backend.persistence.application_consequence_store import SQLiteApplicationConsequenceStore
from backend.persistence.application_consequences import PlanConsequence, PlanConsequenceBatch
from backend.persistence.auth import SQLiteAuthenticationRepository
from backend.persistence.database import session_scope
from backend.persistence.models import (
    CalendarEvent,
    CommitteeMember,
    ConfirmedPlanRevision,
    ExamDay,
    ExamDayAssignment,
    ExamRoom,
    ExamVenue,
    ExamVenueAuditEvent,
    Notification,
    Person,
)
from backend.planning.exam_venues import ExamVenueConfirmationRequiredError
from backend.planning.venue_consequences import (
    VenueAssignment,
    VenueCalendarConsequence,
    VenueNotificationConsequence,
    describe_venue_change,
)
from backend.planning_ports import VENUE_FIELDS, VenueAuditEventSnapshot
from backend.tests.fixture_data import FIXTURE_IDS, FIXTURE_ROOT
from backend.tests.helpers import (
    ApiServer,
    TempDatabase,
    assert_status,
    exam_venue_api_for_test,
    exam_venue_service_for_test,
    venue_consequence_service_for_test,
)


class VenueConsequenceTests(unittest.TestCase):
    @staticmethod
    def _confirmed_database():
        database = TempDatabase()
        db_path = database.__enter__()
        planning_service(db_path).generate_proposal(1)
        planning_service(db_path).confirm_plan(1)
        create_calendar_service(db_path).sync_round(1)
        return database, db_path

    def test_planning_derives_typed_venue_consequences_from_detached_values(self) -> None:
        descriptions = describe_venue_change(
            venue_id=4,
            entity_type="venue",
            entity_id=4,
            before={"street": "Altweg 1", "name": "Ort"},
            after={"street": "Neuweg 2", "name": "Ort"},
            changed_fields=frozenset({"street"}),
            meaningful_change=True,
            assignments=(VenueAssignment(assignment_id=12, recipient_member_id=9, committee_id=3),),
        )

        self.assertEqual(
            (
                VenueCalendarConsequence(
                    recipient_member_id=9,
                    assignment_id=12,
                    entity_type="venue",
                    entity_id=4,
                    expected_signature=(
                        ("city", None),
                        ("country", None),
                        ("entrance", None),
                        ("name", "Ort"),
                        ("postal_code", None),
                        ("site_name", None),
                        ("street", "Neuweg 2"),
                        ("travel_directions", None),
                    ),
                ),
            ),
            descriptions.calendar,
        )
        self.assertEqual(
            (
                VenueNotificationConsequence(
                    recipient_member_id=9,
                    assignment_ids=(12,),
                    committee_id=3,
                    venue_id=4,
                    entity_type="venue",
                    entity_id=4,
                    expected_signature=(
                        ("accessibility_notes", None),
                        ("accessibility_status", None),
                        ("city", None),
                        ("country", None),
                        ("entrance", None),
                        ("is_accessible", None),
                        ("postal_code", None),
                        ("site_name", None),
                        ("street", "Neuweg 2"),
                        ("travel_directions", None),
                    ),
                    fields=("Anschrift",),
                ),
            ),
            descriptions.notifications,
        )

    def test_processing_claim_is_exclusive_and_recovers_after_lease_expiry(self) -> None:
        now = datetime(2026, 10, 8, 12, tzinfo=UTC)
        with TempDatabase() as db_path:
            with session_scope(db_path) as session:
                batch = PlanConsequenceBatch(
                    origin_type="exam_venue_audit_event",
                    origin_key="claim-test",
                )
                session.add(batch)
                session.flush()
                task = PlanConsequence(
                    batch_id=batch.id,
                    recipient_member_id=1,
                    consequence_type="notification",
                    action="notify",
                    identity_key="member:1:committee:1",
                    details_json="{}",
                )
                session.add(task)
                session.flush()
                task_id = task.id

            service = venue_consequence_service_for_test(db_path)
            self.assertTrue(service._claim_task(task_id, now))
            self.assertFalse(service._claim_task(task_id, now + timedelta(minutes=4)))
            self.assertTrue(service._claim_task(task_id, now + timedelta(minutes=6)))

            with session_scope(db_path) as session:
                task = session.get(PlanConsequence, task_id)
                assert task is not None
                self.assertEqual("pending", task.status)
                self.assertEqual(0, task.attempt_count)
                self.assertEqual(
                    (now + timedelta(minutes=11)).isoformat(timespec="seconds"),
                    task.next_attempt_at,
                )

    def test_preview_and_meaningful_update_refresh_calendar_and_notify_members(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = exam_venue_service_for_test(db_path)
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

            result = venues.update_venue(1, payload, technical_actor="operator:test")
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
            venues = exam_venue_service_for_test(db_path)
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
            service = venue_consequence_service_for_test(db_path)
            venue = exam_venue_service_for_test(db_path).get_venue(1)
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

            venues = exam_venue_service_for_test(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            venues.update_venue(
                1,
                {
                    "expected_revision": venue["revision"],
                    "site_name": "Neuer Gebäudeteil",
                    "confirm_future_assignments": True,
                },
                technical_actor="operator:test",
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
            venues = exam_venue_service_for_test(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            with patch(
                "backend.calendar.service.CalendarService.sync_assignment",
                side_effect=RuntimeError("simulated calendar failure"),
            ):
                result = venues.update_venue(
                    1,
                    {
                        "expected_revision": venue["revision"],
                        "site_name": "Gebäude B",
                        "confirm_future_assignments": True,
                    },
                    technical_actor="operator:test",
                )
            assert result is not None
            self.assertEqual("Gebäude B", result["site_name"])
            self.assertIn("consequence_warning", result)
            audit_id = result["consequence_audit_id"]
            self.assertTrue(venue_consequence_service_for_test(db_path).problems_for_venue(1))

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
            chair_view = exam_venue_api_for_test(db_path).get_venue(1, chair_scope)
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
            member_view = exam_venue_api_for_test(db_path).get_venue(1, member_scope)
            assert member_view is not None
            self.assertEqual([], member_view["consequence_problems"])

            retried = venue_consequence_service_for_test(db_path).retry_audit(audit_id)
            replay_service = venue_consequence_service_for_test(db_path)
            with patch.object(
                replay_service, "_tasks", wraps=replay_service._tasks
            ) as derive_tasks:
                repeated = replay_service.retry_audit(audit_id)
            derive_tasks.assert_not_called()
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

    def test_process_due_recovers_missing_batches_and_expired_claims(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = exam_venue_service_for_test(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            changed = venues.update_venue(
                1,
                {
                    "expected_revision": venue["revision"],
                    "site_name": "Gebäude für Wiederanlauf",
                    "confirm_future_assignments": True,
                },
                technical_actor="operator:test",
            )
            assert changed is not None
            audit_id = changed["consequence_audit_id"]
            with session_scope(db_path) as session:
                batch = session.scalar(
                    select(PlanConsequenceBatch).where(
                        PlanConsequenceBatch.origin_type == "exam_venue_audit_event",
                        PlanConsequenceBatch.origin_key == str(audit_id),
                    )
                )
                assert batch is not None
                session.delete(batch)

            service = venue_consequence_service_for_test(db_path)
            with patch.object(service, "_supersede_stale", wraps=service._supersede_stale) as scan:
                recovered = service.process_due()
            scan.assert_not_called()
            self.assertGreater(recovered["processed"], 0)
            self.assertEqual(0, recovered["problems"])
            self.assertEqual([], service.problems_for_venue(1))

            with session_scope(db_path) as session:
                task = session.scalar(
                    select(PlanConsequence)
                    .join(PlanConsequenceBatch)
                    .where(
                        PlanConsequenceBatch.origin_type == "exam_venue_audit_event",
                        PlanConsequenceBatch.origin_key == str(audit_id),
                    )
                )
                assert task is not None
                task.status = "pending"
                task.next_attempt_at = "2000-01-01T00:00:00+00:00"

            problems = service.problems_for_venue(1)
            self.assertEqual("claim_expired", problems[0]["error_code"])
            self.assertEqual("pending", problems[0]["status"])
            retried = service.retry_audit(audit_id)
            self.assertEqual(0, retried["problems"])
            self.assertEqual([], service.problems_for_venue(1))
        finally:
            database.__exit__(None, None, None)

    def test_recovery_uses_assignment_recipients_from_the_audit_snapshot(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = exam_venue_service_for_test(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            changed = venues.update_venue(
                1,
                {
                    "expected_revision": venue["revision"],
                    "site_name": "Auditzeitiger Standort",
                    "confirm_future_assignments": True,
                },
                technical_actor="operator:test",
            )
            assert changed is not None
            audit_id = changed["consequence_audit_id"]
            with session_scope(db_path) as session:
                audit = session.get(ExamVenueAuditEvent, audit_id)
                assert audit is not None
                audit_assignments = json.loads(audit.details_json)["assignments"]
                original_recipients = {item["recipient_member_id"] for item in audit_assignments}
                batch = session.scalar(
                    select(PlanConsequenceBatch).where(
                        PlanConsequenceBatch.origin_type == "exam_venue_audit_event",
                        PlanConsequenceBatch.origin_key == str(audit_id),
                    )
                )
                assert batch is not None
                session.delete(batch)

            with session_scope(db_path) as session:
                example_member = session.scalar(
                    select(CommitteeMember).where(
                        CommitteeMember.committee_id == 1,
                        CommitteeMember.committee_role == "member",
                    )
                )
                assert example_member is not None
                person = Person(
                    first_name="Recovery",
                    last_name="Späterer Prüfer",
                    email="recovery-later@example.invalid",
                )
                session.add(person)
                session.flush()
                new_member = CommitteeMember(
                    person_id=person.id,
                    committee_id=1,
                    member_status=example_member.member_status,
                    committee_role=example_member.committee_role,
                    representing_side=example_member.representing_side,
                    is_active=1,
                )
                session.add(new_member)
                session.flush()
                later_day = session.scalar(
                    select(ExamDay)
                    .join(ExamRoom, ExamRoom.id == ExamDay.room_id)
                    .where(ExamRoom.venue_id == 1, ExamDay.status == "confirmed")
                    .order_by(ExamDay.id)
                )
                assert later_day is not None
                session.add(
                    ExamDayAssignment(
                        exam_day_id=later_day.id,
                        committee_member_id=new_member.id,
                        assignment_role="examiner",
                        day_part="full_day",
                    )
                )
                new_member_id = new_member.id

            recovered = venue_consequence_service_for_test(db_path).process_due()

            with session_scope(db_path) as session:
                recovered_recipients = set(
                    session.scalars(
                        select(PlanConsequence.recipient_member_id)
                        .join(PlanConsequenceBatch)
                        .where(
                            PlanConsequenceBatch.origin_type == "exam_venue_audit_event",
                            PlanConsequenceBatch.origin_key == str(audit_id),
                            PlanConsequence.consequence_type == "notification",
                        )
                    )
                )

            self.assertGreater(recovered["processed"], 0)
            self.assertEqual(original_recipients, recovered_recipients)
            self.assertNotIn(new_member_id, recovered_recipients)
        finally:
            database.__exit__(None, None, None)

    def test_invalid_audit_details_are_reported_even_if_batch_exists(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = venue_consequence_service_for_test(db_path)
            malformed_audit = VenueAuditEventSnapshot(
                id=999,
                venue_id=1,
                entity_type="venue",
                entity_id=1,
                details_json="{invalid-json",
                created_at="2026-10-09T00:00:00+00:00",
            )
            incomplete_audit = VenueAuditEventSnapshot(
                id=1000,
                venue_id=1,
                entity_type="room",
                entity_id=2,
                details_json=json.dumps(
                    {
                        "consequence_version": 2,
                        "before": {},
                        "after": {},
                        "changed_fields": [],
                        "meaningful_change": True,
                    }
                ),
                created_at="2026-10-09T00:00:01+00:00",
            )
            service.consequence_store.record_batch(
                origin_type="exam_venue_audit_event",
                origin_key=str(incomplete_audit.id),
                confirmed_plan_revision_id=None,
                notification_scope=(),
                tasks=(),
                error_code=None,
                now="2026-10-09T00:00:01+00:00",
            )
            audits = (malformed_audit, incomplete_audit)
            with (
                patch.object(service.venue_planner, "consequence_audits", return_value=audits),
                patch.object(service.venue_planner, "audits_for_venue", return_value=audits),
                patch.object(
                    service.venue_planner.repository,
                    "consequence_audit",
                    side_effect=audits,
                ),
            ):
                recovered = service.process_due()
                problems = service.problems_for_venue(1)

            self.assertEqual(2, recovered["audits"])
            self.assertEqual(2, recovered["problems"])
            self.assertEqual(2, len(problems))
            self.assertEqual(
                {"invalid_audit_details"}, {problem["error_code"] for problem in problems}
            )
        finally:
            database.__exit__(None, None, None)

    def test_legacy_audit_snapshot_is_only_a_problem_when_batch_is_missing(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = venue_consequence_service_for_test(db_path)
            legacy_with_batch = VenueAuditEventSnapshot(
                id=1001,
                venue_id=1,
                entity_type="venue",
                entity_id=1,
                details_json=json.dumps(
                    {
                        "consequence_version": 1,
                        "before": {"site_name": "Old"},
                        "after": {"site_name": "New"},
                        "changed_fields": ["site_name"],
                        "meaningful_change": True,
                    }
                ),
                created_at="2026-10-09T00:00:00+00:00",
            )
            legacy_without_batch = VenueAuditEventSnapshot(
                id=1002,
                venue_id=1,
                entity_type="room",
                entity_id=2,
                details_json=legacy_with_batch.details_json,
                created_at="2026-10-09T00:00:01+00:00",
            )
            service.consequence_store.record_batch(
                origin_type="exam_venue_audit_event",
                origin_key=str(legacy_with_batch.id),
                confirmed_plan_revision_id=None,
                notification_scope=(),
                tasks=(),
                error_code=None,
                now="2026-10-09T00:00:00+00:00",
            )
            audits = (legacy_with_batch, legacy_without_batch)
            with (
                patch.object(service.venue_planner, "consequence_audits", return_value=audits),
                patch.object(service.venue_planner, "audits_for_venue", return_value=audits),
            ):
                recovered = service.process_due()
                problems = service.problems_for_venue(1)

            self.assertEqual(2, recovered["audits"])
            self.assertEqual(1, recovered["problems"])
            self.assertEqual(1, len(problems))
            self.assertEqual("legacy_audit_snapshot_missing", problems[0]["error_code"])
            self.assertEqual(legacy_without_batch.id, problems[0]["audit_id"])
            self.assertFalse(problems[0]["retryable"])
        finally:
            database.__exit__(None, None, None)

    def test_v2_snapshot_rejects_unknown_or_inconsistent_changed_fields(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = venue_consequence_service_for_test(db_path)
            before = dict.fromkeys(VENUE_FIELDS)
            after = dict(before, site_name="New", entrance="North")
            invalid_snapshots = (
                {
                    "before": before,
                    "after": after,
                    "changed_fields": ["site_nam"],
                },
                {
                    "before": before,
                    "after": after,
                    "changed_fields": ["site_name"],
                },
                {
                    "before": before,
                    "after": before,
                    "changed_fields": ["site_name"],
                },
                {
                    "before": {key: value for key, value in before.items() if key != "city"},
                    "after": after,
                    "changed_fields": ["site_name", "entrance"],
                },
            )
            for index, snapshot in enumerate(invalid_snapshots):
                with self.subTest(snapshot=snapshot):
                    audit = VenueAuditEventSnapshot(
                        id=1010 + index,
                        venue_id=1,
                        entity_type="venue",
                        entity_id=1,
                        details_json=json.dumps(
                            {
                                "consequence_version": 2,
                                **snapshot,
                                "meaningful_change": True,
                                "assignments": [],
                            }
                        ),
                        created_at="2026-10-09T00:00:00+00:00",
                    )
                    with patch.object(
                        service.venue_planner.repository,
                        "consequence_audit",
                        return_value=audit,
                    ):
                        with self.assertRaisesRegex(
                            ValueError, "invalid audit-time consequence snapshot"
                        ):
                            service.process_audit(audit.id)
                        with self.assertRaisesRegex(
                            ValueError, "invalid audit-time consequence snapshot"
                        ):
                            service.retry_audit(audit.id)
                    self.assertIsNone(
                        service.consequence_store.batch_by_origin(
                            "exam_venue_audit_event", str(audit.id)
                        )
                    )
                    self.assertTrue(service._has_invalid_details(service._audit_details(audit)))
        finally:
            database.__exit__(None, None, None)

    def test_audit_snapshot_rejects_non_integer_assignment_identifiers(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            service = venue_consequence_service_for_test(db_path)
            invalid_assignments = (
                {"assignment_id": 1, "recipient_member_id": 27.8, "committee_id": 1},
                {"assignment_id": 1, "recipient_member_id": True, "committee_id": 1},
            )
            for index, assignment in enumerate(invalid_assignments):
                with self.subTest(assignment=assignment):
                    before = dict.fromkeys(VENUE_FIELDS)
                    after = dict(before, site_name="New")
                    audit = VenueAuditEventSnapshot(
                        id=1100 + index,
                        venue_id=1,
                        entity_type="venue",
                        entity_id=1,
                        details_json=json.dumps(
                            {
                                "consequence_version": 2,
                                "before": before,
                                "after": after,
                                "changed_fields": ["site_name"],
                                "meaningful_change": True,
                                "assignments": [assignment],
                            }
                        ),
                        created_at="2026-10-09T00:00:00+00:00",
                    )
                    with patch.object(
                        service.venue_planner.repository,
                        "consequence_audit",
                        return_value=audit,
                    ):
                        with self.assertRaisesRegex(
                            ValueError, "invalid audit-time consequence snapshot"
                        ):
                            service.venue_planner.source_for_audit(audit.id)
                    self.assertTrue(service._has_invalid_details(service._audit_details(audit)))
        finally:
            database.__exit__(None, None, None)

    def test_retry_supersedes_an_effect_after_a_newer_relevant_change(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = exam_venue_service_for_test(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            with patch(
                "backend.calendar.service.CalendarService.sync_assignment",
                side_effect=RuntimeError("simulated calendar failure"),
            ):
                failed = venues.update_venue(
                    1,
                    {
                        "expected_revision": venue["revision"],
                        "site_name": "Zwischenstand",
                        "confirm_future_assignments": True,
                    },
                    technical_actor="operator:test",
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
                technical_actor="operator:test",
            )

            old = venue_consequence_service_for_test(db_path).retry_audit(
                failed["consequence_audit_id"]
            )
            self.assertGreater(old["superseded"], 0)
            self.assertEqual(0, old["problems"])
        finally:
            database.__exit__(None, None, None)

    def test_retry_uses_persisted_tasks_when_audit_snapshot_cannot_be_read(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = exam_venue_service_for_test(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            with patch(
                "backend.calendar.service.CalendarService.sync_assignment",
                side_effect=RuntimeError("simulated calendar failure"),
            ):
                updated = venues.update_venue(
                    1,
                    {
                        "expected_revision": venue["revision"],
                        "site_name": "Retry from batch",
                        "confirm_future_assignments": True,
                    },
                    technical_actor="operator:test",
                )
            assert updated is not None
            service = venue_consequence_service_for_test(db_path)
            with patch.object(
                service.venue_planner,
                "source_for_audit",
                side_effect=ValueError("invalid audit-time assignment snapshot"),
            ):
                retried = service.retry_audit(updated["consequence_audit_id"])

            self.assertEqual(0, retried["problems"])
            self.assertGreater(retried["processed"], 0)
        finally:
            database.__exit__(None, None, None)

    def test_notification_write_rechecks_venue_freshness_atomically(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = exam_venue_service_for_test(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            original = NotificationService.create_direct_if_current
            state = {"advanced": False, "new_audit_id": None}

            def advance_before_atomic_write(service, **kwargs):
                if not state["advanced"]:
                    state["advanced"] = True
                    current = venues.get_venue(1)
                    assert current is not None
                    updated = venues.update_venue(
                        1,
                        {
                            "expected_revision": current["revision"],
                            "site_name": "Aktueller Standort",
                            "confirm_future_assignments": True,
                        },
                        technical_actor="operator:test",
                    )
                    assert updated is not None
                    state["new_audit_id"] = updated["consequence_audit_id"]
                return original(service, **kwargs)

            with patch.object(
                NotificationService,
                "create_direct_if_current",
                new=advance_before_atomic_write,
            ):
                old_update = venues.update_venue(
                    1,
                    {
                        "expected_revision": venue["revision"],
                        "site_name": "Zwischenstand",
                        "confirm_future_assignments": True,
                    },
                    technical_actor="operator:test",
                )

            assert old_update is not None
            old_audit_id = old_update["consequence_audit_id"]
            new_audit_id = state["new_audit_id"]
            assert new_audit_id is not None
            with session_scope(db_path) as session:
                old_notices = session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.origin_key.like(f"exam-venue-change:{old_audit_id}:%"))
                )
                new_notices = session.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.origin_key.like(f"exam-venue-change:{new_audit_id}:%"))
                )
                old_task_statuses = session.scalars(
                    select(PlanConsequence.status)
                    .join(PlanConsequenceBatch)
                    .where(
                        PlanConsequenceBatch.origin_type == "exam_venue_audit_event",
                        PlanConsequenceBatch.origin_key == str(old_audit_id),
                    )
                ).all()

            self.assertEqual(0, old_notices)
            self.assertGreater(new_notices, 0)
            self.assertIn("superseded", old_task_statuses)
        finally:
            database.__exit__(None, None, None)

    def test_record_batch_reraises_nonduplicate_integrity_errors(self) -> None:
        with TempDatabase() as db_path:
            store = SQLiteApplicationConsequenceStore(db_path)
            with self.assertRaises(IntegrityError):
                store.record_batch(
                    origin_type="exam_venue_audit_event",
                    origin_key="invalid-recipient",
                    confirmed_plan_revision_id=None,
                    notification_scope=(),
                    tasks=(
                        {
                            "recipient_member_id": 99999999,
                            "consequence_type": "calendar",
                            "action": "update",
                            "identity_key": "missing-member",
                            "details_json": "{}",
                        },
                    ),
                    error_code=None,
                    now=datetime.now(UTC).isoformat(),
                )
            with session_scope(db_path) as session:
                batch = session.scalar(
                    select(PlanConsequenceBatch).where(
                        PlanConsequenceBatch.origin_key == "invalid-recipient"
                    )
                )
            self.assertIsNone(batch)

    def test_abort_requires_confirmation_before_master_data_change(self) -> None:
        database, db_path = self._confirmed_database()
        try:
            venues = exam_venue_service_for_test(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            with self.assertRaises(ExamVenueConfirmationRequiredError):
                venues.update_venue(
                    1,
                    {"expected_revision": venue["revision"], "entrance": "Eingang West"},
                    technical_actor="operator:test",
                )
            unchanged = venues.get_venue(1)
            assert unchanged is not None
            self.assertEqual(venue["revision"], unchanged["revision"])
            self.assertEqual(venue["entrance"], unchanged["entrance"])
        finally:
            database.__exit__(None, None, None)


class VenueConsequenceApiTests(unittest.TestCase):
    def test_nonretryable_audit_problem_does_not_allow_manual_retry(self) -> None:
        database, db_path = VenueConsequenceTests._confirmed_database()
        try:
            api = exam_venue_api_for_test(db_path)
            with patch.object(
                api.consequences,
                "problems_for_venue",
                return_value=[
                    {
                        "audit_id": 123,
                        "venue_id": 1,
                        "retryable": False,
                    }
                ],
            ):
                self.assertIsNone(
                    api.retry_consequences(
                        123,
                        AuthorizationScope(
                            None, frozenset(), frozenset(), frozenset(), frozenset(), {}
                        ),
                    )
                )
        finally:
            database.__exit__(None, None, None)

    def test_preview_failure_visibility_and_controlled_retry(self) -> None:
        with TempDatabase() as db_path:
            planning_service(db_path).generate_proposal(1)
            planning_service(db_path).confirm_plan(1)
            create_calendar_service(db_path).sync_round(1)
            venues = exam_venue_service_for_test(db_path)
            venue = venues.get_venue(1)
            assert venue is not None
            payload = {
                "expected_revision": venue["revision"],
                "site_name": "Gebäude API",
                "confirm_future_assignments": True,
            }
            auth = SQLiteAuthenticationRepository(db_path)
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
                    "backend.calendar.service.CalendarService.sync_assignment",
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
