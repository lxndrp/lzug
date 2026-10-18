from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from http import HTTPStatus
from unittest.mock import patch

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
    AbsenceConsequenceSource,
    PlanConsequence,
    PlanConsequenceBatch,
)
from backend.persistence.database import session_scope
from backend.persistence.models import (
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
