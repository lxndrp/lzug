from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import UTC, datetime
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy.exc import IntegrityError

from backend.application.absence_consequences import AbsenceConsequenceApplication
from backend.application.exam_lifecycle import ExamLifecycleApplication
from backend.composition import (
    application_consequence_store,
    exam_lifecycle_unit_of_work_factory,
)
from backend.composition import (
    calendar_service as compose_calendar_service,
)
from backend.execution.absence import AbsenceService
from backend.identity.authorization import AuthorizationScope
from backend.persistence.absence_uow import SQLiteAbsenceUnitOfWorkFactory
from backend.persistence.application_consequences import (
    AbsenceConsequenceCutover,
    AbsenceConsequenceSource,
    PlanConsequence,
    PlanConsequenceBatch,
)
from backend.persistence.database import initialize, session_scope
from backend.persistence.models import (
    AbsenceAuditEvent,
    CalendarEvent,
    ExamDay,
    ExamDayAssignment,
    ExamRound,
    ExamSlot,
    MemberAvailability,
    Notification,
    ReplacementResponse,
)
from backend.tests.helpers import (
    ApiServer,
    TempDatabase,
    assert_status,
    notification_service_for_test,
)


def scope(member_id: int, *, management: bool = False) -> AuthorizationScope:
    return AuthorizationScope(
        person_id=member_id,
        person_ids=frozenset({member_id}),
        committee_ids=frozenset({1}),
        member_ids=frozenset({member_id}),
        management_committee_ids=frozenset({1}) if management else frozenset(),
        member_by_committee={1: member_id},
    )


class AbsenceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        self.calendar_service = compose_calendar_service(self.db_path)
        with session_scope(self.db_path) as session:
            round_row = session.get(ExamRound, 1)
            round_row.status = "plan_confirmed"
            day = ExamDay(
                exam_round_id=1,
                room_id=1,
                date="2026-11-16",
                status="confirmed",
            )
            session.add(day)
            session.flush()
            session.add_all(
                [
                    ExamSlot(
                        exam_day_id=day.id,
                        round_candidate_id=1,
                        slot_type="regular",
                        starts_at="2026-11-16T09:00:00+00:00",
                        ends_at="2026-11-16T10:00:00+00:00",
                        sequence_number=1,
                        status="confirmed",
                    ),
                    ExamDayAssignment(
                        exam_day_id=day.id,
                        committee_member_id=1,
                        assignment_role="examiner",
                        day_part="morning",
                    ),
                    ExamDayAssignment(
                        exam_day_id=day.id,
                        committee_member_id=3,
                        assignment_role="examiner",
                        day_part="morning",
                    ),
                    ExamDayAssignment(
                        exam_day_id=day.id,
                        committee_member_id=2,
                        assignment_role="examiner",
                        day_part="morning",
                    ),
                    ExamDayAssignment(
                        exam_day_id=day.id,
                        committee_member_id=7,
                        assignment_role="fallback",
                        day_part="morning",
                        fallback_status="confirmed",
                    ),
                ]
            )
            self.day_id = day.id
            session.flush()
            self.assignment_id = (
                session.query(ExamDayAssignment)
                .filter_by(exam_day_id=day.id, committee_member_id=1)
                .one()
                .id
            )
            self.other_assignment_id = (
                session.query(ExamDayAssignment)
                .filter_by(exam_day_id=day.id, committee_member_id=3)
                .one()
                .id
            )
            availability = (
                session.query(MemberAvailability)
                .filter_by(exam_round_id=1, committee_member_id=7, candidate_exam_day_id=1)
                .one()
            )
            availability.availability = "full_day"
            availability.responded_at = "2026-10-31T09:00:00+00:00"

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def absence_service(self) -> AbsenceService:
        return AbsenceService(SQLiteAbsenceUnitOfWorkFactory(self.db_path))

    def absence_lifecycle_application(self, service: AbsenceService):
        factory = exam_lifecycle_unit_of_work_factory(self.db_path)
        return ExamLifecycleApplication(
            factory,
            lambda: None,
            absence_consequences=AbsenceConsequenceApplication(
                unit_of_work_factory=factory,
                consequence_store=application_consequence_store(self.db_path),
                notification_service=notification_service_for_test(self.db_path),
                calendar_service=self.calendar_service,
            ),
        )

    def test_migration_029_cuts_over_legacy_absence_audit_without_replay(self) -> None:
        service = self.absence_service()
        current = datetime(2026, 11, 1, tzinfo=UTC)
        legacy_report = service.report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=current,
        )
        with session_scope(self.db_path) as session:
            legacy_audit_id = (
                session.query(AbsenceAuditEvent.id)
                .filter_by(absence_report_id=legacy_report["id"])
                .scalar()
            )

        # Recreate the database shape immediately before migration 029 while
        # retaining the historical absence report and audit event.
        with sqlite3.connect(self.db_path) as connection:
            connection.executescript("""
                DROP TRIGGER IF EXISTS absence_consequence_source_no_update;
                DROP TRIGGER IF EXISTS absence_consequence_source_no_delete;
                DROP TABLE absence_consequence_source;
                DROP TABLE absence_consequence_cutover;
                DROP TABLE calendar_assignment_execution_origin;
                ALTER TABLE exam_day_assignment DROP COLUMN revision;
                DELETE FROM schema_migration_checksum
                  WHERE name = '029_add_absence_consequence_sources.sql';
                DELETE FROM schema_migration
                  WHERE name = '029_add_absence_consequence_sources.sql';
            """)

        initialize(self.db_path)
        with session_scope(self.db_path) as session:
            cutover = session.get(AbsenceConsequenceCutover, 1)
            self.assertIsNotNone(cutover)
            assert cutover is not None
            self.assertEqual(legacy_audit_id, cutover.audit_watermark)

        lifecycle_factory = exam_lifecycle_unit_of_work_factory(self.db_path)
        processor = AbsenceConsequenceApplication(
            unit_of_work_factory=lifecycle_factory,
            consequence_store=application_consequence_store(self.db_path),
            notification_service=notification_service_for_test(self.db_path),
            calendar_service=self.calendar_service,
        )
        legacy_only = processor.process_due(now=current)
        self.assertEqual(0, legacy_only["sources"])
        self.assertEqual(1, legacy_only["legacy_unreplayable"])
        with session_scope(self.db_path) as session:
            self.assertEqual(0, session.query(PlanConsequenceBatch).count())

        post_cutover_report = service.report(
            scope(1, management=True),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.other_assignment_id},
            now=current,
        )
        with session_scope(self.db_path) as session:
            post_cutover_audit_id = (
                session.query(AbsenceAuditEvent.id)
                .filter_by(absence_report_id=post_cutover_report["id"])
                .scalar()
            )
        post_cutover = processor.process_due(now=current)
        self.assertEqual(1, post_cutover["sources"])
        self.assertEqual(1, post_cutover["legacy_unreplayable"])
        with session_scope(self.db_path) as session:
            origins = session.query(PlanConsequenceBatch.origin_key).all()
            self.assertEqual(
                [f"absence-audit:{post_cutover_audit_id}"],
                [origin for (origin,) in origins],
            )

        initialize(self.db_path)
        replay = processor.process_due(now=current)
        self.assertEqual(1, replay["sources"])
        self.assertEqual(1, replay["legacy_unreplayable"])
        with session_scope(self.db_path) as session:
            self.assertEqual(1, session.query(PlanConsequenceBatch).count())

    def test_absence_effects_are_skipped_after_another_worker_reclaims_the_lease(self) -> None:
        current = datetime(2026, 11, 1, tzinfo=UTC)
        initial_lease = "2026-11-01T00:05:00+00:00"
        replacement_lease = "2026-11-01T00:10:00+00:00"
        for consequence_type in ("calendar", "notification"):
            with self.subTest(consequence_type=consequence_type):
                task = SimpleNamespace(
                    id=1,
                    origin_key="absence-audit:1",
                    recipient_member_id=7,
                    consequence_type=consequence_type,
                    details_json=json.dumps(
                        {
                            "assignment_id": 1,
                            "round_id": 1,
                            "assignment_revision": 2,
                            "calendar_action": "update",
                            "before_image": [],
                            "committee_id": 1,
                            "event_type": "replacement_selected",
                            "title": "Ersatzmitglied ausgewählt",
                            "message": "Folgearbeit",
                            "action_path": "/absence-reports/1",
                        }
                    ),
                    attempt_count=0,
                    calendar_event_id=None,
                    calendar_event_version=None,
                )
                store = Mock()
                store.claim_task.return_value = True
                store.task.side_effect = [
                    task,
                    SimpleNamespace(status="pending", next_attempt_at=replacement_lease),
                ]
                processor = AbsenceConsequenceApplication(
                    unit_of_work_factory=Mock(),
                    consequence_store=store,
                    notification_service=Mock(),
                    calendar_service=Mock(),
                )

                self.assertTrue(processor._process_task(1, current))

                store.claim_task.assert_called_once_with(
                    1,
                    now="2026-11-01T00:00:00+00:00",
                    lease_until=initial_lease,
                )
                store.set_task_state.assert_not_called()
                processor.calendar.apply_absence_follow_up.assert_not_called()
                processor.notifications.create_direct.assert_not_called()

    def test_failed_absence_notification_is_retried_and_recorded_as_succeeded(self) -> None:
        current = datetime(2026, 11, 1, tzinfo=UTC)
        retry_at = "2026-11-01T00:02:00+00:00"
        store = application_consequence_store(self.db_path)
        batch_id = store.record_batch(
            origin_type="absence_audit_event",
            origin_key="absence-audit:retry-test",
            confirmed_plan_revision_id=None,
            notification_scope=(7,),
            tasks=(
                {
                    "recipient_member_id": 7,
                    "consequence_type": "notification",
                    "action": "notify",
                    "identity_key": "absence-audit:retry-test",
                    "details_json": json.dumps(
                        {
                            "committee_id": 1,
                            "round_id": 1,
                            "event_type": "replacement_selected",
                            "title": "Ersatzmitglied ausgewählt",
                            "message": "Folgearbeit",
                            "action_path": "/absence-reports/1",
                        }
                    ),
                },
            ),
            error_code=None,
            now="2026-11-01T00:00:00+00:00",
        )
        task_id = store.due_task_ids(
            origin_type="absence_audit_event",
            now="2026-11-01T00:00:00+00:00",
            batch_id=batch_id,
        )[0]
        notifications = Mock()
        notifications.create_direct.side_effect = [RuntimeError("provider unavailable"), None]
        processor = AbsenceConsequenceApplication(
            unit_of_work_factory=Mock(),
            consequence_store=store,
            notification_service=notifications,
            calendar_service=Mock(),
        )

        self.assertTrue(processor._process_task(task_id, current))
        failed = store.task(task_id)
        self.assertEqual("temporarily_failed", failed.status)
        self.assertEqual(1, failed.attempt_count)
        self.assertEqual(retry_at, failed.next_attempt_at)

        self.assertTrue(processor._process_task(task_id, datetime(2026, 11, 1, 0, 2, tzinfo=UTC)))
        succeeded = store.task(task_id)
        self.assertEqual("succeeded", succeeded.status)
        self.assertEqual(2, succeeded.attempt_count)
        self.assertEqual(2, notifications.create_direct.call_count)

    def test_report_uses_exclusive_fallback_window_and_audit_history(self) -> None:
        result = self.absence_service().report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )

        self.assertEqual("fallback_requested", result["status"])
        self.assertEqual([7], [item["committee_member_id"] for item in result["responses"]])
        self.assertEqual("reported", result["audit"][0]["event_type"])
        self.assertEqual("fallback_requested", result["audit"][0]["to_status"])
        self.assertEqual(
            24,
            int(
                (
                    datetime.fromisoformat(result["responses"][0]["expires_at"])
                    - datetime(2026, 11, 1, tzinfo=UTC)
                ).total_seconds()
                / 3600
            ),
        )

    def test_urgent_report_requests_fallback_and_other_eligible_members(self) -> None:
        result = self.absence_service().report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=datetime(2026, 11, 15, tzinfo=UTC),
        )

        self.assertEqual("replacement_requested", result["status"])
        self.assertEqual({4, 7}, {item["committee_member_id"] for item in result["responses"]})
        self.assertTrue(all(item["urgent"] for item in result["responses"]))

    def test_expired_fallback_opens_further_search_and_audits_deadline(self) -> None:
        service = self.absence_service()
        result = service.report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )

        updated = service.respond(
            scope(7),
            result["responses"][0]["id"],
            {"response": "available"},
            now=datetime(2026, 11, 2, tzinfo=UTC),
        )

        self.assertEqual("replacement_requested", updated["status"])
        self.assertEqual("unavailable", updated["responses"][0]["response"])
        audit_types = {event["event_type"] for event in updated["audit"]}
        self.assertIn("fallback_expired", audit_types)
        self.assertIn("replacement_search_opened", audit_types)

    def test_report_checks_round_lock_in_its_writer_session(self) -> None:
        service = self.absence_service()
        with session_scope(self.db_path) as session:
            session.get(ExamRound, 1).lifecycle_status = "closed"
        with self.assertRaisesRegex(ValueError, "fachlich beendet"):
            service.report(
                scope(1),
                {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
                now=datetime(2026, 11, 1, tzinfo=UTC),
            )

        with session_scope(self.db_path) as session:
            self.assertEqual(0, session.query(ReplacementResponse).count())

    def test_selection_checks_round_lock_before_calendar_preflight_sync(self) -> None:
        service = self.absence_service()
        report = service.report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )
        report = service.respond(
            scope(7),
            report["responses"][0]["id"],
            {"response": "available"},
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )

        with session_scope(self.db_path) as session:
            session.get(ExamRound, 1).lifecycle_status = "closed"
        locked_service = self.absence_service()
        application = self.absence_lifecycle_application(locked_service)
        processor = application._absence_consequences
        with (
            patch.object(
                processor.calendar,
                "apply_absence_follow_up",
                wraps=processor.calendar.apply_absence_follow_up,
            ) as sync,
            self.assertRaisesRegex(ValueError, "fachlich beendet"),
        ):
            application.select_absence_replacement(
                scope(1, management=True),
                report["id"],
                {"committee_member_id": 7, "version": report["version"]},
                locked_service,
                now=datetime(2026, 11, 1, tzinfo=UTC),
            )
        sync.assert_not_called()

    def test_selection_is_single_versioned_transition_and_replays_calendar_work(self) -> None:
        service = self.absence_service()
        result = service.report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )
        response_id = result["responses"][0]["id"]
        service.respond(
            scope(7), response_id, {"response": "available"}, now=datetime(2026, 11, 1, tzinfo=UTC)
        )
        selected = self.absence_lifecycle_application(service).select_absence_replacement(
            scope(1, management=True),
            result["id"],
            {"committee_member_id": 7, "version": 1},
            service,
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )

        self.assertEqual("replacement_selected", selected["status"])
        self.assertEqual(7, selected["selected_replacement_member_id"])
        with session_scope(self.db_path) as session:
            assignment = session.get(ExamDayAssignment, self.assignment_id)
            events = (
                session.query(CalendarEvent)
                .filter(CalendarEvent.source_key.like(f"assignment:{self.assignment_id}:%"))
                .all()
            )
            self.assertEqual(7, assignment.committee_member_id)
            self.assertEqual(1, len(events))
            self.assertEqual({"sent"}, {event.status for event in events})
            self.assertEqual({7}, {event.recipient_member_id for event in events})
            self.assertEqual(1, session.query(ReplacementResponse).count())

    def test_application_selection_commits_an_immutable_replay_source(self) -> None:
        service = self.absence_service()
        current = datetime(2026, 11, 1, tzinfo=UTC)
        report = service.report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=current,
        )
        report = service.respond(
            scope(7), report["responses"][0]["id"], {"response": "available"}, now=current
        )
        lifecycle_factory = exam_lifecycle_unit_of_work_factory(self.db_path)
        processor = AbsenceConsequenceApplication(
            unit_of_work_factory=lifecycle_factory,
            consequence_store=application_consequence_store(self.db_path),
            notification_service=notification_service_for_test(self.db_path),
            calendar_service=self.calendar_service,
        )
        application = ExamLifecycleApplication(
            lifecycle_factory,
            lambda: None,
            absence_consequences=processor,
        )

        selected = application.select_absence_replacement(
            scope(1, management=True),
            report["id"],
            {"committee_member_id": 7, "version": report["version"]},
            service,
            now=current,
        )

        self.assertEqual("replacement_selected", selected["status"])
        with session_scope(self.db_path) as session:
            source = (
                session.query(AbsenceConsequenceSource)
                .order_by(AbsenceConsequenceSource.id.desc())
                .first()
            )
            payload = json.loads(source.source_json)
            assignment = session.get(ExamDayAssignment, self.assignment_id)
            self.assertEqual("lzug-absence-consequence-source-v1", payload["format"])
            self.assertEqual(list(range(1, 9)), payload["recipient_member_ids"])
            self.assertEqual(2, source.assignment_revision)
            self.assertEqual(2, assignment.revision)
            self.assertIn("guard_snapshot", payload)
            batch = (
                session.query(PlanConsequenceBatch).filter_by(origin_key=payload["origin_id"]).one()
            )
            batch_id = batch.id
            self.assertEqual("absence_audit_event", batch.origin_type)
            self.assertEqual(9, session.query(PlanConsequence).filter_by(batch_id=batch.id).count())
            with self.assertRaises(IntegrityError), session.begin_nested():
                source.source_json = "{}"
                session.flush()

        with session_scope(self.db_path) as session:
            session.query(PlanConsequence).filter_by(batch_id=batch_id).delete()
            session.delete(session.get(PlanConsequenceBatch, batch_id))
        replay = processor.process_due(now=current)
        self.assertEqual(3, replay["sources"])
        with session_scope(self.db_path) as session:
            self.assertEqual(3, session.query(PlanConsequenceBatch).count())

    def test_repeated_selection_cycles_create_distinct_notice_origins(self) -> None:
        service = self.absence_service()
        current = datetime(2026, 11, 1, tzinfo=UTC)
        report = service.report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=current,
        )
        report = service.respond(
            scope(7), report["responses"][0]["id"], {"response": "available"}, now=current
        )
        application = self.absence_lifecycle_application(service)
        selected = application.select_absence_replacement(
            scope(1, management=True),
            report["id"],
            {"committee_member_id": 7, "version": report["version"]},
            service,
            now=current,
        )
        reopened = application.reopen_absence(
            scope(1, management=True),
            report["id"],
            {"reason": "Erneute Prüfung", "version": selected["version"]},
            service,
            now=current,
        )
        application.select_absence_replacement(
            scope(1, management=True),
            report["id"],
            {"committee_member_id": 7, "version": reopened["version"]},
            service,
            now=current,
        )

        with session_scope(self.db_path) as session:
            notices = (
                session.query(Notification)
                .filter(Notification.event_type.in_(("replacement_selected", "absence_reopened")))
                .all()
            )
            selected_notices = [
                item for item in notices if item.event_type == "replacement_selected"
            ]
            reopened_notices = [item for item in notices if item.event_type == "absence_reopened"]
            self.assertEqual(16, len(selected_notices))
            self.assertEqual(8, len(reopened_notices))
            self.assertEqual(16, len({item.origin_key for item in selected_notices}))
            self.assertEqual(8, len({item.origin_key for item in reopened_notices}))
            self.assertTrue(all(item.origin_key.startswith("absence-audit:") for item in notices))

    def test_cancellation_freezes_calendar_follow_up_for_durable_processing(self) -> None:
        service = self.absence_service()
        self.calendar_service.sync_round(1)
        result = service.report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )

        application = self.absence_lifecycle_application(service)
        cancelled = application.cancel_absence(
            scope(1, management=True),
            result["id"],
            {"reason": "Kein Ersatz verfügbar"},
            service,
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )

        with session_scope(self.db_path) as session:
            source = (
                session.query(AbsenceConsequenceSource)
                .order_by(AbsenceConsequenceSource.id.desc())
                .first()
            )
            payload = json.loads(source.source_json)
            self.assertEqual("cancel", payload["calendar_action"])
            self.assertTrue(payload["calendar_enabled"])
            self.assertEqual(2, session.get(ExamDayAssignment, self.assignment_id).revision)
            events = (
                session.query(CalendarEvent)
                .filter_by(exam_day_assignment_id=self.assignment_id)
                .all()
            )
            self.assertTrue(events)
            self.assertTrue(all(event.status == "cancelled" for event in events))

        self.calendar_service.sync_round(1)
        with session_scope(self.db_path) as session:
            self.assertTrue(
                all(
                    event.status == "cancelled"
                    for event in session.query(CalendarEvent).filter_by(
                        exam_day_assignment_id=self.assignment_id
                    )
                )
            )

        reopened = application.reopen_absence(
            scope(1, management=True),
            result["id"],
            {"reason": "Termin wiederhergestellt", "version": cancelled["version"]},
            service,
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )
        self.assertEqual("replacement_requested", reopened["status"])
        with session_scope(self.db_path) as session:
            source = (
                session.query(AbsenceConsequenceSource)
                .order_by(AbsenceConsequenceSource.id.desc())
                .first()
            )
            payload = json.loads(source.source_json)
            self.assertTrue(payload["calendar_enabled"])
            self.assertEqual(3, source.assignment_revision)
            self.assertEqual(3, session.get(ExamDayAssignment, self.assignment_id).revision)
            self.assertTrue(
                any(
                    event.status == "sent"
                    for event in session.query(CalendarEvent).filter_by(
                        exam_day_assignment_id=self.assignment_id
                    )
                )
            )

        current_report = reopened
        for cycle in range(5):
            cancelled = application.cancel_absence(
                scope(1, management=True),
                result["id"],
                {"reason": f"Absage {cycle}", "version": current_report["version"]},
                service,
                now=datetime(2026, 11, 1, tzinfo=UTC),
            )
            current_report = application.reopen_absence(
                scope(1, management=True),
                result["id"],
                {"reason": f"Wiederöffnung {cycle}", "version": cancelled["version"]},
                service,
                now=datetime(2026, 11, 1, tzinfo=UTC),
            )

        with session_scope(self.db_path) as session:
            sources = (
                session.query(AbsenceConsequenceSource)
                .filter_by(assignment_id=self.assignment_id)
                .all()
            )
            calendar_images = []
            for source in sources:
                payload = json.loads(source.source_json)
                if (
                    payload.get("calendar_action") == "cancel"
                    or payload.get("notice", {}).get("event_type") == "absence_reopened"
                ):
                    calendar_images.append(payload["calendar_before_image"])
            self.assertEqual(12, len(calendar_images))
            self.assertLessEqual(max(map(len, calendar_images)), 1)

    def test_urgent_report_freezes_urgent_notification_replay(self) -> None:
        service = self.absence_service()
        current = datetime(2026, 11, 15, tzinfo=UTC)
        application = self.absence_lifecycle_application(service)
        application.report_absence(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            service,
            now=current,
        )
        with session_scope(self.db_path) as session:
            source = (
                session.query(AbsenceConsequenceSource)
                .order_by(AbsenceConsequenceSource.id.desc())
                .first()
            )
            self.assertTrue(json.loads(source.source_json)["notice"]["urgent"])
            notification = (
                session.query(Notification)
                .filter_by(event_type="urgent_replacement_requested")
                .first()
            )
            self.assertIsNotNone(notification)

    def test_post_commit_source_failure_does_not_fail_report_and_admin_retries_permanent_tasks(
        self,
    ) -> None:
        service = self.absence_service()
        application = self.absence_lifecycle_application(service)
        processor = application._absence_consequences
        with (
            patch.object(processor, "process_due") as full_scan,
            patch.object(processor, "process_source", side_effect=RuntimeError("store offline")),
        ):
            result = application.report_absence(
                scope(1),
                {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
                service,
                now=datetime(2026, 11, 1, tzinfo=UTC),
            )
        full_scan.assert_not_called()
        self.assertGreater(result["id"], 0)
        with session_scope(self.db_path) as session:
            self.assertEqual(1, session.query(AbsenceConsequenceSource).count())
            for task in session.query(PlanConsequence):
                task.status = "permanently_failed"
                task.attempt_count = 4
            session.query(Notification).delete()

        processor.process_due(now=datetime(2026, 11, 1, tzinfo=UTC))
        with session_scope(self.db_path) as session:
            self.assertTrue(
                all(task.status == "succeeded" for task in session.query(PlanConsequence))
            )
            self.assertGreater(session.query(Notification).count(), 0)

    def test_failed_selection_preserves_assignment_audit_version_and_follow_up_work(self) -> None:
        service = self.absence_service()
        current = datetime(2026, 11, 1, tzinfo=UTC)
        report = service.report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=current,
        )
        report = service.respond(
            scope(7), report["responses"][0]["id"], {"response": "available"}, now=current
        )
        command = {"committee_member_id": 7, "version": report["version"]}
        for actor, payload, error in (
            (scope(2), command, PermissionError),
            (scope(1, management=True), {**command, "version": 0}, ValueError),
            (scope(1, management=True), {**command, "committee_member_id": 4}, ValueError),
        ):
            with self.subTest(payload=payload, actor=actor), self.assertRaises(error):
                self.absence_lifecycle_application(service).select_absence_replacement(
                    actor, report["id"], payload, service, now=current
                )
            self.assertEqual(report, service.get(scope(1), report["id"]))

        with session_scope(self.db_path) as session:
            day_revision = session.get(ExamDay, self.day_id).revision
        with (
            patch.object(service, "required_view", side_effect=RuntimeError("test view failure")),
            patch.object(
                self.calendar_service,
                "apply_absence_follow_up",
                wraps=self.calendar_service.apply_absence_follow_up,
            ) as sync,
            self.assertRaisesRegex(RuntimeError, "test view failure"),
        ):
            self.absence_lifecycle_application(service).select_absence_replacement(
                scope(1, management=True), report["id"], command, service, now=current
            )
        sync.assert_not_called()
        self.assertEqual(report, service.get(scope(1), report["id"]))
        with session_scope(self.db_path) as session:
            self.assertEqual(
                1, session.get(ExamDayAssignment, self.assignment_id).committee_member_id
            )
            self.assertEqual(day_revision, session.get(ExamDay, self.day_id).revision)

        selected = self.absence_lifecycle_application(service).select_absence_replacement(
            scope(1, management=True), report["id"], command, service, now=current
        )
        self.assertEqual(report["version"] + 1, selected["version"])
        self.assertEqual(
            1, sum(event["event_type"] == "replacement_selected" for event in selected["audit"])
        )
        with self.assertRaises(ValueError):
            self.absence_lifecycle_application(service).select_absence_replacement(
                scope(1, management=True), report["id"], command, service, now=current
            )
        self.assertEqual(selected, service.get(scope(1), report["id"]))

    def test_member_cannot_report_another_member_absence(self) -> None:
        with self.assertRaises(PermissionError):
            self.absence_service().report(
                scope(2),
                {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
                now=datetime(2026, 11, 1, tzinfo=UTC),
            )

    def test_http_api_exposes_the_process_without_client_actor_fields(self) -> None:
        with ApiServer(self.db_path) as api:
            status, result = api.request(
                "POST",
                "/api/absence-reports",
                {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            )
            assert_status(status, HTTPStatus.CREATED)
            self.assertEqual(1, result["reported_by_member_id"])
            status, collection = api.request("GET", "/api/absence-reports")
            assert_status(status, HTTPStatus.OK)
            self.assertEqual([result["id"]], [item["id"] for item in collection["items"]])
