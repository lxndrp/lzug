from __future__ import annotations

import unittest
from http import HTTPStatus
from unittest.mock import patch

from sqlalchemy import event, text

from backend.application.exam_lifecycle import ExamLifecycleApplication
from backend.application.exam_lifecycle_commands import day_close_command, day_reopen_command
from backend.assessment.service import ExamResultService
from backend.composition import (
    SQLiteAssessmentLifecycleAdapter,
    identity_lifecycle_work_factory,
    planning_lifecycle_work_factory,
)
from backend.execution.exam_day_closures import (
    ExamDayClosureService,
)
from backend.identity.authorization import AuthorizationScope
from backend.persistence.assessment import SQLiteAssessmentUnitOfWorkFactory
from backend.persistence.auth import SQLiteAuthenticationRepository
from backend.persistence.database import session_scope
from backend.persistence.exam_lifecycle import SQLiteExamLifecycleUnitOfWorkFactory
from backend.persistence.execution import SQLiteExecutionUnitOfWorkFactory
from backend.persistence.identity import SQLiteIdentityExecutionSnapshotFactory
from backend.persistence.models import (
    ExamDay,
    ExamDayAuditEvent,
    ExamDayClosure,
    ExamDayExport,
    ExamDayReopening,
    ExamDayTask,
    ExamResult,
    ExamRoundAssessmentBinding,
    MemberExamAttendance,
    Notification,
    ResultCalculation,
    ResultCommunication,
    ResultCorrection,
    ResultDetermination,
)
from backend.tests.fixture_data import prepare_exam_protocol_scenario
from backend.tests.helpers import (
    ApiServer,
    TempDatabase,
    assert_status,
    notification_service_for_test,
)


class ExamDayClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        prepare_exam_protocol_scenario(self.db_path)
        authentication = SQLiteAuthenticationRepository(self.db_path)
        self.chair = authentication.create_session(1)
        self.examiner = authentication.create_session(2)
        self.deputy = authentication.create_session(3)
        outsider = authentication.create_account(
            "exam-day-closure.outsider@example.invalid", person_id=4
        )
        operator = authentication.create_account(
            "exam-day-closure.operator@example.invalid", is_operator=True
        )
        self.outsider = authentication.create_session(outsider["id"])
        self.operator = authentication.create_session(operator["id"])

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def test_exam_lifecycle_uow_binds_both_domains_to_one_rollback_boundary(self) -> None:
        factory = SQLiteExamLifecycleUnitOfWorkFactory(
            SQLiteExecutionUnitOfWorkFactory(
                self.db_path,
                identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
            ),
            SQLiteAssessmentUnitOfWorkFactory(self.db_path),
            self.db_path,
            SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
        )

        with self.assertRaisesRegex(RuntimeError, "synthetic lifecycle failpoint"):
            with factory() as unit_of_work:
                execution_session = unit_of_work.execution._session
                assessment_session = unit_of_work.assessment.repository.session
                lifecycle_assessment_session = (
                    unit_of_work.assessment_lifecycle._work.repository.session
                )
                self.assertIs(execution_session, assessment_session)
                self.assertIs(execution_session, lifecycle_assessment_session)
                day = execution_session.get(ExamDay, 2)
                day.revision = 99
                raise RuntimeError("synthetic lifecycle failpoint")

        with session_scope(self.db_path) as session:
            self.assertEqual(1, session.get(ExamDay, 2).revision)

    def test_closure_evaluation_keeps_finding_order(self) -> None:
        with session_scope(self.db_path) as session:
            evaluation = ExamDayClosureService._evaluate(
                ExamDayClosureService(
                    self.db_path,
                    notification_service=notification_service_for_test(self.db_path),
                    assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
                    planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
                    identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
                ),
                session,
                session.get(ExamDay, 2),
            )
        self.assertEqual(
            [
                "day_has_slots",
                "slots_terminal",
                "cancelled_slots_reasoned",
                "actual_times_complete",
                "candidate_attendance_complete",
                "staff_attendance_complete",
                "staffing_rule_compliant",
                "absence_processes_complete",
                "protocols_complete",
                "results_complete",
            ],
            [item["code"] for item in evaluation["items"]],
        )

    def test_closure_snapshot_loads_attendance_in_bounded_queries(self) -> None:
        statements: list[str] = []
        with session_scope(self.db_path) as session:
            day = session.get(ExamDay, 2)
            connection = session.connection()

            def count_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
                statements.append(statement)

            event.listen(connection, "before_cursor_execute", count_statement)
            try:
                snapshot = ExamDayClosureService._load_closure_snapshot(
                    session,
                    day,
                    planning_lifecycle_work_factory()(session),
                    identity_lifecycle_work_factory()(session),
                )
            finally:
                event.remove(connection, "before_cursor_execute", count_statement)

        self.assertEqual(1, len(snapshot.slots))
        self.assertEqual(5, len(statements))

    def test_result_without_determination_is_not_mutated_by_reopening(self) -> None:
        with session_scope(self.db_path) as session:
            result = session.get(ExamResult, 2)
            expected_version = result.version

            with session_scope(self.db_path) as concurrent_session:
                concurrent_session.execute(
                    text("UPDATE exam_result SET version = version + 1 WHERE id = 2")
                )

            assessment = SQLiteAssessmentLifecycleAdapter()(session)
            receipt = assessment.open_result_correction(
                result_id=result.id,
                reopening_id=1,
                actor_member_id=1,
                reason="fixture correction",
                requested_at="2026-10-02T12:00:00+00:00",
            )

        with session_scope(self.db_path) as session:
            self.assertEqual(expected_version + 1, session.get(ExamResult, 2).version)
        self.assertIsNone(receipt["determination_id"])

    def test_missing_assessment_binding_is_reported_as_blocked_day_completion(self) -> None:
        with session_scope(self.db_path) as session:
            day = session.get(ExamDay, 3)
            self.assertIsNotNone(day)
            session.query(ExamRoundAssessmentBinding).filter_by(
                exam_round_id=day.exam_round_id
            ).delete()
            snapshot = (
                SQLiteAssessmentUnitOfWorkFactory(self.db_path)
                .in_session(session)
                .queries.day_completion(day.id)
            )

        assert snapshot is not None
        result_slots = [slot for slot in snapshot["slots"] if slot["result"] is not None]
        self.assertTrue(result_slots)
        self.assertTrue(all(slot["result"]["model"] is None for slot in result_slots))
        completion = ExamResultService().completion_from_snapshot(snapshot)
        self.assertFalse(completion["closing_ready"])
        self.assertTrue(all(row["state"] == "model_missing" for row in completion["slots"]))

    def test_execution_and_assessment_share_the_application_transaction(self) -> None:
        factory = SQLiteExamLifecycleUnitOfWorkFactory(
            SQLiteExecutionUnitOfWorkFactory(
                self.db_path,
                identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
            ),
            SQLiteAssessmentUnitOfWorkFactory(self.db_path),
            self.db_path,
        )
        with self.assertRaisesRegex(RuntimeError, "rollback cross-domain write"):
            with factory() as work:
                result = work.assessment.queries.result_by_id(2)
                self.assertIsNotNone(result)
                unchanged = work.assessment.repository.open_day_reopening_correction(
                    {
                        "result_id": 2,
                        "expected_result_version": result["version"],
                        "reopening_reference": "exam-day-reopening:1",
                        "requested_by_member_id": 1,
                        "reason": "Fachliche Korrektur",
                        "requested_at": "2026-10-08T12:00:00+00:00",
                    }
                )
                self.assertIsNone(unchanged["determination_id"])
                self.assertEqual(result["version"], unchanged["result_version"])
                work.assessment.repository.set_result_state(
                    {
                        "result_id": 2,
                        "expected_result_version": result["version"],
                        "state": "calculation_ready",
                    }
                )
                assignment = next(
                    item
                    for item in work.execution.assignments(1)
                    if item["committee_member_id"] == 1
                )
                work.execution.save_member_attendance(
                    1,
                    assignment["id"],
                    1,
                    {"status": "late", "arrived_at": "2026-11-16T08:59:00+01:00"},
                    actor_member_id=1,
                    expected_day_revision=1,
                )
                raise RuntimeError("rollback cross-domain write")

        with session_scope(self.db_path) as session:
            self.assertEqual("incomplete", session.get(ExamResult, 2).current_state)
            self.assertEqual(1, session.get(ExamDay, 1).revision)
            self.assertEqual(
                "present",
                session.query(MemberExamAttendance)
                .filter_by(exam_day_id=1, committee_member_id=1)
                .one()
                .status,
            )

    def test_regular_cancelled_day_close_is_atomic_idempotent_locked_and_exportable(
        self,
    ) -> None:
        with ApiServer(self.db_path) as api:
            status, initial = api.request(
                "GET", "/api/confirmed-plan-days/2/closure", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertTrue(initial["evaluation"]["regular_close_ready"])
            self.assertTrue(all(item["ok"] for item in initial["evaluation"]["items"]))

            command = {"revision": 1, "closure_type": "regular", "confirmed": True}
            for credentials in (self.examiner, self.outsider, self.operator):
                status, _error = api.request(
                    "POST",
                    "/api/confirmed-plan-days/2/closure",
                    command,
                    credentials=credentials,
                )
                assert_status(status, HTTPStatus.FORBIDDEN)

            status, closed = api.request(
                "POST", "/api/confirmed-plan-days/2/closure", command, credentials=self.deputy
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("closed", closed["status"])
            self.assertEqual(2, closed["revision"])

            status, repeated = api.request(
                "POST", "/api/confirmed-plan-days/2/closure", command, credentials=self.deputy
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(2, repeated["revision"])
            self.assertEqual(
                1, len([item for item in repeated["history"] if item["kind"] == "closure"])
            )

            status, _conflict = api.request(
                "POST",
                "/api/confirmed-plan-days/2/closure",
                {
                    **command,
                    "closure_type": "exception",
                    "reason": "x",
                    "clarification_attempts": "y",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.CONFLICT)

            status, _locked = api.request(
                "PATCH",
                "/api/confirmed-plan-days/2/slots/2/attendance",
                {"status": "absent", "day_revision": 2},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.CONFLICT)
            status, _locked = api.request(
                "PATCH",
                "/api/confirmed-plan-days/2/slots/2/status",
                {
                    "status": "cancelled",
                    "reason": "Nachträgliche Inhaltsänderung",
                    "day_revision": 2,
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.CONFLICT)

            status, exported = api.request(
                "GET", "/api/confirmed-plan-days/2/closure/export.json", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("closed", exported["closure"]["status"])
            self.assertEqual(2, exported["closure"]["revision"])
            status, headers, content = api.request_raw(
                "GET", "/api/confirmed-plan-days/2/closure/export.txt", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertIn("text/plain", headers["content-type"])
            self.assertIn("Abschlussnachweis Prüfungstag 2", content.decode("utf-8"))

        with session_scope(self.db_path) as session:
            self.assertEqual(1, session.query(ExamDayClosure).filter_by(exam_day_id=2).count())
            self.assertEqual(2, session.query(ExamDayExport).filter_by(exam_day_id=2).count())
            self.assertEqual(2, session.get(ExamDay, 2).revision)

    def test_exception_late_response_targeted_reopening_and_reclose(self) -> None:
        with ApiServer(self.db_path) as api:
            status, initial = api.request(
                "GET", "/api/confirmed-plan-days/3/closure", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertFalse(initial["evaluation"]["regular_close_ready"])
            self.assertTrue(initial["evaluation"]["exception_close_ready"])
            self.assertEqual(
                ["written_exam"],
                initial["evaluation"]["result_references"][0]["external_inputs_pending"],
            )

            status, _invalid = api.request(
                "POST",
                "/api/confirmed-plan-days/3/closure",
                {"revision": 1, "closure_type": "exception", "confirmed": True},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)

            command = {
                "revision": 1,
                "closure_type": "exception",
                "confirmed": True,
                "reason": "Eine synthetische Protokollreaktion steht aus",
                "clarification_attempts": "Synthetische Erinnerung dokumentiert",
            }
            status, closed = api.request(
                "POST", "/api/confirmed-plan-days/3/closure", command, credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("closed_exception", closed["status"])
            open_followups = [
                item
                for item in closed["tasks"]
                if item["task_type"] == "protocol_follow_up" and item["status"] == "open"
            ]
            self.assertEqual([3], [item["recipient_member_id"] for item in open_followups])

            status, protocol = api.request(
                "POST",
                "/api/exam-protocols/2/responses",
                {"version": 1, "response": "confirmed", "day_revision": 2},
                credentials=self.examiner,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("fully_confirmed", protocol["state"])
            status, after_response = api.request(
                "GET", "/api/confirmed-plan-days/3/closure", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("closed_exception", after_response["status"])
            self.assertEqual("completed", after_response["tasks"][0]["status"])

            status, _locked = api.request(
                "PATCH",
                "/api/exam-protocols/2",
                {
                    "version": 1,
                    "declaration": "without_special_occurrences",
                    "entries": [],
                    "day_revision": 2,
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.CONFLICT)

            scope = [{"kind": "exam_protocol", "entity_id": 2}]
            status, impact = api.request(
                "POST",
                "/api/confirmed-plan-days/3/reopening-impact",
                {"scope": scope},
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertIn("exam_protocol:2", impact["expanded_scope"])
            self.assertIn("exam_result:2", impact["expanded_scope"])

            reopen = {
                "revision": 2,
                "occasion": "Synthetischer Korrekturhinweis",
                "source": "IHK-Testanforderung TEST-36",
                "reason": "Der unveränderliche Demo-Pfad benötigt eine Korrektur",
                "scope": scope,
            }
            status, _forbidden = api.request(
                "POST",
                "/api/confirmed-plan-days/3/reopenings",
                reopen,
                credentials=self.examiner,
            )
            assert_status(status, HTTPStatus.FORBIDDEN)
            status, reopened = api.request(
                "POST", "/api/confirmed-plan-days/3/reopenings", reopen, credentials=self.deputy
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("reopening", reopened["status"])
            self.assertEqual(3, reopened["revision"])
            status, repeated = api.request(
                "POST", "/api/confirmed-plan-days/3/reopenings", reopen, credentials=self.deputy
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(3, repeated["revision"])

            status, _unaffected = api.request(
                "PATCH",
                "/api/confirmed-plan-days/3/slots/3/attendance",
                {"status": "late", "arrived_at": "2027-05-20T08:56:00+02:00", "day_revision": 3},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.CONFLICT)

            status, protocol = api.request(
                "PATCH",
                "/api/exam-protocols/2",
                {
                    "version": 2,
                    "declaration": "without_special_occurrences",
                    "entries": [],
                    "day_revision": 3,
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(4, protocol["day_revision"])
            correction_version = protocol["current_version"]
            status, _stale = api.request(
                "POST",
                "/api/exam-protocols/2/submit",
                {"version": correction_version, "day_revision": 3},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.CONFLICT)

            status, protocol = api.request(
                "POST",
                "/api/exam-protocols/2/submit",
                {"version": correction_version, "day_revision": 4},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            for credentials in (self.chair, self.deputy, self.examiner):
                status, protocol = api.request(
                    "POST",
                    "/api/exam-protocols/2/responses",
                    {
                        "version": correction_version,
                        "response": "confirmed",
                        "day_revision": protocol["day_revision"],
                    },
                    credentials=credentials,
                )
                assert_status(status, HTTPStatus.OK)

            status, reclosed = api.request(
                "POST",
                "/api/confirmed-plan-days/3/closure",
                {
                    "revision": protocol["day_revision"],
                    "closure_type": "regular",
                    "confirmed": True,
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("closed", reclosed["status"])
            self.assertEqual(
                2, len([item for item in reclosed["history"] if item["kind"] == "closure"])
            )

            status, result = api.request("GET", "/api/exam-results/2", credentials=self.chair)
            assert_status(status, HTTPStatus.OK)
            status, result = api.request(
                "POST",
                "/api/exam-results/2/external-results",
                {
                    "version": result["version"],
                    "area_key": "written_exam",
                    "points": "82",
                    "grade": "gut",
                    "professional_status": "bestanden",
                    "determining_authority": "IHK Teststadt",
                    "source_reference": "Bescheid TEST-36",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            external_id = result["external_results"][-1]["id"]
            status, _result = api.request(
                "POST",
                f"/api/exam-results/2/external-results/{external_id}/confirm",
                {"version": result["version"]},
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            status, after_external = api.request(
                "GET", "/api/confirmed-plan-days/3/closure", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("closed", after_external["status"])
            self.assertEqual(reclosed["revision"], after_external["revision"])

        with session_scope(self.db_path) as session:
            followup = session.query(ExamDayTask).filter_by(task_type="protocol_follow_up").one()
            self.assertEqual("completed", followup.status)
            self.assertEqual(
                1,
                session.query(Notification)
                .filter_by(event_type="exam_day_protocol_follow_up", recipient_member_id=3)
                .count(),
            )

    def test_historical_day_can_only_be_corrected_in_the_requested_scope(self) -> None:
        with session_scope(self.db_path) as session:
            day = session.get(ExamDay, 2)
            day.status = "completed"
            day.closure_status = "historical"

        with ApiServer(self.db_path) as api:
            scope = [{"kind": "slot_status", "entity_id": 2}]
            status, reopened = api.request(
                "POST",
                "/api/confirmed-plan-days/2/reopenings",
                {
                    "revision": 1,
                    "occasion": "Korrektur eines historischen Absagegrunds",
                    "source": "IHK-Testanforderung TEST-36-HIST",
                    "reason": "Der dokumentierte Absagegrund war unvollständig",
                    "scope": scope,
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("reopening", reopened["status"])
            self.assertFalse(any(item["kind"] == "closure" for item in reopened["history"]))

            status, corrected = api.request(
                "PATCH",
                "/api/confirmed-plan-days/2/slots/2/status",
                {
                    "status": "cancelled",
                    "reason": "Vollständig dokumentierter synthetischer Absagegrund",
                    "day_revision": 2,
                    "actual_started_at": None,
                    "actual_completed_at": None,
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(3, corrected["day"]["revision"])

            status, closed = api.request(
                "POST",
                "/api/confirmed-plan-days/2/closure",
                {"revision": 3, "closure_type": "regular", "confirmed": True},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("closed", closed["status"])
            self.assertEqual(
                1, len([item for item in closed["history"] if item["kind"] == "closure"])
            )

    def test_notification_creation_failure_does_not_rollback_exception_close(self) -> None:
        with patch(
            "backend.execution.exam_day_closures.NotificationService.create_direct",
            side_effect=RuntimeError("synthetic delivery creation failure"),
        ):
            with ApiServer(self.db_path) as api:
                status, closed = api.request(
                    "POST",
                    "/api/confirmed-plan-days/3/closure",
                    {
                        "revision": 1,
                        "closure_type": "exception",
                        "confirmed": True,
                        "reason": "Synthetischer Ausnahmegrund",
                        "clarification_attempts": "Synthetischer Klärungsversuch",
                    },
                    credentials=self.chair,
                )
                assert_status(status, HTTPStatus.OK)
                self.assertEqual("closed_exception", closed["status"])

        with session_scope(self.db_path) as session:
            self.assertEqual("closed_exception", session.get(ExamDay, 3).closure_status)
            self.assertEqual(1, session.query(ExamDayClosure).filter_by(exam_day_id=3).count())
            self.assertEqual(1, session.query(ExamDayTask).filter_by(exam_day_id=3).count())

    def test_close_transaction_outcome_defers_notifications_until_published(self) -> None:
        service = ExamDayClosureService(
            self.db_path,
            notification_service=notification_service_for_test(self.db_path),
            assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
            planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
            identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
        )
        scope = AuthorizationScope(
            person_id=1,
            person_ids=frozenset({1}),
            committee_ids=frozenset({1}),
            member_ids=frozenset({1}),
            management_committee_ids=frozenset({1}),
            member_by_committee={1: 1},
        )
        application = ExamLifecycleApplication(
            SQLiteExamLifecycleUnitOfWorkFactory(
                SQLiteExecutionUnitOfWorkFactory(
                    self.db_path,
                    identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
                ),
                SQLiteAssessmentUnitOfWorkFactory(self.db_path),
                self.db_path,
                SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
            ),
            lambda: service,
        )

        def assert_committed_before_notification(*_args, **_kwargs):
            with session_scope(self.db_path) as session:
                self.assertEqual("closed_exception", session.get(ExamDay, 3).closure_status)

        with patch(
            "backend.execution.exam_day_closures.NotificationService.create_direct",
            side_effect=assert_committed_before_notification,
        ) as create_direct:
            application.close_exam_day(
                scope,
                3,
                day_close_command(
                    {
                        "revision": 1,
                        "closure_type": "exception",
                        "confirmed": True,
                        "reason": "Synthetischer Ausnahmegrund",
                        "clarification_attempts": "Synthetischer Klärungsversuch",
                    }
                ),
            )
            create_direct.assert_called()

    def test_application_close_rolls_back_execution_write_failure(self) -> None:
        service = ExamDayClosureService(
            self.db_path,
            notification_service=notification_service_for_test(self.db_path),
            assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
            planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
            identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
        )
        application = ExamLifecycleApplication(
            SQLiteExamLifecycleUnitOfWorkFactory(
                SQLiteExecutionUnitOfWorkFactory(
                    self.db_path,
                    identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
                ),
                SQLiteAssessmentUnitOfWorkFactory(self.db_path),
                self.db_path,
                SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
            ),
            lambda: service,
        )
        scope = AuthorizationScope(
            person_id=1,
            person_ids=frozenset({1}),
            committee_ids=frozenset({1}),
            member_ids=frozenset({1}),
            management_committee_ids=frozenset({1}),
            member_by_committee={1: 1},
        )
        with patch.object(
            ExamDayClosureService,
            "_record_closure",
            side_effect=RuntimeError("synthetic execution write failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic execution write failure"):
                application.close_exam_day(
                    scope,
                    3,
                    day_close_command(
                        {
                            "revision": 1,
                            "closure_type": "exception",
                            "confirmed": True,
                            "reason": "Synthetischer Ausnahmegrund",
                            "clarification_attempts": "Synthetischer Klärungsversuch",
                        }
                    ),
                )

        with session_scope(self.db_path) as session:
            self.assertEqual("open", session.get(ExamDay, 3).closure_status)
            self.assertIsNone(
                session.query(ExamDayClosure).filter(ExamDayClosure.exam_day_id == 3).one_or_none()
            )

    def test_reopen_rolls_back_assessment_correction_and_execution_evidence(self) -> None:
        service = ExamDayClosureService(
            self.db_path,
            notification_service=notification_service_for_test(self.db_path),
            assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
            planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
            identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
        )
        application = ExamLifecycleApplication(
            SQLiteExamLifecycleUnitOfWorkFactory(
                SQLiteExecutionUnitOfWorkFactory(
                    self.db_path,
                    identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
                ),
                SQLiteAssessmentUnitOfWorkFactory(self.db_path),
                self.db_path,
                SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
            ),
            lambda: service,
        )
        scope = AuthorizationScope(
            person_id=1,
            person_ids=frozenset({1}),
            committee_ids=frozenset({1}),
            member_ids=frozenset({1}),
            management_committee_ids=frozenset({1}),
            member_by_committee={1: 1},
        )
        application.close_exam_day(
            scope,
            3,
            day_close_command(
                {
                    "revision": 1,
                    "closure_type": "exception",
                    "confirmed": True,
                    "reason": "Synthetischer Ausnahmegrund",
                    "clarification_attempts": "Synthetischer Klärungsversuch",
                }
            ),
        )
        with session_scope(self.db_path) as session:
            calculation = ResultCalculation(
                exam_result_id=2,
                version=1,
                input_fingerprint="f" * 64,
                total_points="80",
                grade="1",
                passed=1,
                calculation_path_json="{}",
                created_at="2026-10-08T12:00:00+00:00",
            )
            session.add(calculation)
            session.flush()
            session.add(
                ResultDetermination(
                    exam_result_id=2,
                    revision=1,
                    result_calculation_id=calculation.id,
                    participant_member_ids_json="[1,2,3]",
                    vote_json='{"yes":[1,2,3],"no":[],"abstain":[]}',
                    dissent_json="[]",
                    status="current",
                    determined_by_member_id=1,
                    determined_at="2026-10-08T12:00:00+00:00",
                )
            )

        with session_scope(self.db_path) as session:
            result_before = session.get(ExamResult, 2)
            result_state = (result_before.version, result_before.correction_open)
            correction_count = session.query(ResultCorrection).count()
            task_count = session.query(ExamDayTask).filter_by(exam_day_id=3).count()
            audit_count = session.query(ExamDayAuditEvent).filter_by(exam_day_id=3).count()

        def fail_after_assessment_mutation(*args, **kwargs):
            transaction = args[0]
            self.assertTrue(transaction.get(ExamResult, 2).correction_open)
            self.assertEqual(1, transaction.query(ResultCorrection).count())
            self.assertEqual("reopening", transaction.get(ExamDay, 3).closure_status)
            self.assertEqual(
                1,
                transaction.query(ExamDayReopening).filter_by(exam_day_id=3).count(),
            )
            self.assertEqual(
                task_count, transaction.query(ExamDayTask).filter_by(exam_day_id=3).count()
            )
            self.assertEqual(1, args[4][2]["determination_id"])
            raise RuntimeError("synthetic failure after assessment correction")

        with (
            patch.object(
                service,
                "complete_reopen_intent",
                side_effect=fail_after_assessment_mutation,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "after assessment correction"):
                application.reopen_exam_day(
                    scope,
                    3,
                    day_reopen_command(
                        {
                            "revision": 2,
                            "occasion": "Korrekturanlass",
                            "source": "Prüfungsausschuss",
                            "reason": "Korrektur erforderlich",
                            "scope": [{"kind": "exam_result", "entity_id": 2}],
                        }
                    ),
                )

        with session_scope(self.db_path) as session:
            self.assertEqual(
                ("closed_exception", 2),
                (session.get(ExamDay, 3).closure_status, session.get(ExamDay, 3).revision),
            )
            result_after = session.get(ExamResult, 2)
            self.assertEqual(result_state, (result_after.version, result_after.correction_open))
            self.assertEqual(correction_count, session.query(ResultCorrection).count())
            self.assertEqual(
                task_count, session.query(ExamDayTask).filter_by(exam_day_id=3).count()
            )
            self.assertEqual(
                audit_count,
                session.query(ExamDayAuditEvent).filter_by(exam_day_id=3).count(),
            )
            self.assertEqual(0, session.query(ExamDayReopening).filter_by(exam_day_id=3).count())

    def _assert_reopen_result_follow_up(self, external_document_status: str | None, expected: str):
        service = ExamDayClosureService(
            self.db_path,
            notification_service=notification_service_for_test(self.db_path),
            assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
            planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
            identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
        )
        application = ExamLifecycleApplication(
            SQLiteExamLifecycleUnitOfWorkFactory(
                SQLiteExecutionUnitOfWorkFactory(
                    self.db_path,
                    identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
                ),
                SQLiteAssessmentUnitOfWorkFactory(self.db_path),
                self.db_path,
                SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
            ),
            lambda: service,
        )
        scope = AuthorizationScope(
            person_id=1,
            person_ids=frozenset({1}),
            committee_ids=frozenset({1}),
            member_ids=frozenset({1}),
            management_committee_ids=frozenset({1}),
            member_by_committee={1: 1},
        )
        application.close_exam_day(
            scope,
            3,
            day_close_command(
                {
                    "revision": 1,
                    "closure_type": "exception",
                    "confirmed": True,
                    "reason": "Synthetischer Ausnahmegrund",
                    "clarification_attempts": "Synthetischer Klärungsversuch",
                }
            ),
        )
        with session_scope(self.db_path) as session:
            calculation = ResultCalculation(
                exam_result_id=2,
                version=1,
                input_fingerprint="c" * 64,
                total_points="80",
                grade="1",
                passed=1,
                calculation_path_json="{}",
                created_at="2026-10-08T12:00:00+00:00",
            )
            session.add(calculation)
            session.flush()
            determination = ResultDetermination(
                exam_result_id=2,
                revision=1,
                result_calculation_id=calculation.id,
                participant_member_ids_json="[1,2,3]",
                vote_json='{"yes":[1,2,3],"no":[],"abstain":[]}',
                dissent_json="[]",
                status="current",
                determined_by_member_id=1,
                determined_at="2026-10-08T12:00:00+00:00",
            )
            session.add(determination)
            session.flush()
            session.add(
                ResultCommunication(
                    exam_result_id=2,
                    result_determination_id=determination.id,
                    method="persönliche Bekanntgabe",
                    responsible_member_id=1,
                    communicated_at="2026-10-08T12:01:00+00:00",
                    external_document_status=external_document_status,
                    external_document_reference=(
                        "IHK-Fachverfahren" if external_document_status else None
                    ),
                    status="current",
                )
            )

        application.reopen_exam_day(
            scope,
            3,
            day_reopen_command(
                {
                    "revision": 2,
                    "occasion": "Korrekturanlass",
                    "source": "Prüfungsausschuss",
                    "reason": "Korrektur erforderlich",
                    "scope": [{"kind": "exam_result", "entity_id": 2}],
                }
            ),
        )
        with session_scope(self.db_path) as session:
            tasks = session.query(ExamDayTask).filter_by(exam_day_id=3).all()
            task_types = {task.task_type for task in tasks}
            self.assertIn(expected, task_types)
            if external_document_status is None:
                self.assertNotIn("ihk_clarification", task_types)
            else:
                self.assertIn("result_recommunication", task_types)

    def test_reopen_adds_recommunication_task_for_communicated_result(self) -> None:
        self._assert_reopen_result_follow_up(None, "result_recommunication")

    def test_reopen_adds_ihk_clarification_for_processed_result(self) -> None:
        self._assert_reopen_result_follow_up("eingereicht", "ihk_clarification")

    def test_each_material_failed_prerequisite_is_reported_and_blocks_exception_close(
        self,
    ) -> None:
        scenarios = (
            (
                "open slot",
                "slots_terminal",
                "UPDATE exam_slot SET execution_status = 'open' WHERE id = 3",
            ),
            (
                "running slot",
                "slots_terminal",
                "UPDATE exam_slot SET execution_status = 'running', "
                "actual_completed_at = NULL WHERE id = 3",
            ),
            (
                "follow-up slot",
                "slots_terminal",
                "UPDATE exam_slot SET execution_status = 'needs_follow_up' WHERE id = 3",
            ),
            (
                "unreasoned cancellation",
                "cancelled_slots_reasoned",
                "UPDATE exam_slot SET execution_status = 'cancelled', actual_started_at = NULL, "
                "actual_completed_at = NULL, status_reason = NULL WHERE id = 3",
            ),
            (
                "missing actual end",
                "actual_times_complete",
                "UPDATE exam_slot SET actual_completed_at = NULL WHERE id = 3",
            ),
            (
                "missing candidate attendance",
                "candidate_attendance_complete",
                "DELETE FROM candidate_exam_attendance WHERE exam_slot_id = 3",
            ),
            (
                "missing member attendance",
                "staff_attendance_complete",
                "DELETE FROM member_exam_attendance WHERE exam_day_id = 3 "
                "AND committee_member_id = 3",
            ),
            (
                "invalid actual staffing",
                "staffing_rule_compliant",
                "UPDATE committee_member SET is_active = 0 WHERE id = 3",
            ),
            (
                "open absence process",
                "absence_processes_complete",
                "INSERT INTO absence_report "
                "(exam_day_id, committee_member_id, reason, status, "
                "exam_day_assignment_id, reported_by_member_id, version) "
                "VALUES (3, 3, 'Synthetischer Ausfall', 'reported', 6, 3, 1)",
            ),
            (
                "unsubmitted protocol",
                "protocols_complete",
                "UPDATE exam_protocol_revision SET declaration = NULL, workflow_state = 'draft', "
                "submitted_at = NULL WHERE id = 2",
            ),
            (
                "more than one missing protocol response",
                "protocols_complete",
                "DELETE FROM exam_protocol_response WHERE exam_protocol_revision_id = 2 "
                "AND committee_member_id = 2",
            ),
            (
                "incomplete day assessment",
                "results_complete",
                "DELETE FROM individual_assessment WHERE id = 2",
            ),
            (
                "open result correction",
                "results_complete",
                "UPDATE exam_result SET correction_open = 1 WHERE id = 2",
            ),
            (
                "calculation ready without determination",
                "results_complete",
                "UPDATE exam_result SET current_state = 'calculation_ready' WHERE id = 2",
            ),
        )
        for name, finding_code, statement in scenarios:
            with self.subTest(prerequisite=name), TempDatabase() as db_path:
                prepare_exam_protocol_scenario(db_path)
                authentication = SQLiteAuthenticationRepository(db_path)
                chair = authentication.create_session(1)
                with session_scope(db_path) as session:
                    session.execute(text(statement))
                with ApiServer(db_path) as api:
                    status, closure = api.request(
                        "GET", "/api/confirmed-plan-days/3/closure", credentials=chair
                    )
                    assert_status(status, HTTPStatus.OK)
                    finding = next(
                        item
                        for item in closure["evaluation"]["items"]
                        if item["code"] == finding_code
                    )
                    self.assertFalse(finding["ok"])
                    status, error = api.request(
                        "POST",
                        "/api/confirmed-plan-days/3/closure",
                        {
                            "revision": 1,
                            "closure_type": "exception",
                            "confirmed": True,
                            "reason": "Synthetischer Ausnahmegrund",
                            "clarification_attempts": "Synthetischer Klärungsversuch",
                        },
                        credentials=chair,
                    )
                    assert_status(status, HTTPStatus.UNPROCESSABLE_ENTITY)
                    self.assertTrue(error["error"]["findings"])

    def test_reservation_and_protocol_occurrence_are_visible_before_close(self) -> None:
        with session_scope(self.db_path) as session:
            session.execute(
                text(
                    "UPDATE exam_protocol_revision SET declaration = 'with_special_occurrences' "
                    "WHERE id = 2"
                )
            )
            session.execute(
                text(
                    "INSERT INTO exam_protocol_entry "
                    "(exam_protocol_revision_id, category, statement, occurred_from, "
                    "recorded_by_member_id) VALUES "
                    "(2, 'procedural_deviation', 'Synthetische Besonderheit', "
                    "'2027-05-20T09:30:00+02:00', 1)"
                )
            )
            session.execute(
                text(
                    "UPDATE exam_protocol_response SET response = 'reservation', "
                    "statement = 'Synthetischer Vorbehalt' "
                    "WHERE exam_protocol_revision_id = 2 AND committee_member_id = 2"
                )
            )

        with ApiServer(self.db_path) as api:
            status, closure = api.request(
                "GET", "/api/confirmed-plan-days/3/closure", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertTrue(closure["evaluation"]["exception_close_ready"])
            warning = closure["evaluation"]["warnings"][0]
            self.assertEqual("Synthetische Besonderheit", warning["entries"][0]["statement"])
            self.assertEqual("Synthetischer Vorbehalt", warning["reservations"][0]["statement"])


if __name__ == "__main__":
    unittest.main()
