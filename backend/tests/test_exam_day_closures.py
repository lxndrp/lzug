from __future__ import annotations

import unittest
from http import HTTPStatus
from unittest.mock import patch

from sqlalchemy import select, text

from backend.application.exam_lifecycle import ExamLifecycleApplication
from backend.application.exam_lifecycle_commands import day_close_command, day_reopen_command
from backend.assessment.service import ExamResultService
from backend.composition import (
    SQLiteAssessmentLifecycleAdapter,
    authorization_service,
    calendar_lifecycle_work_factory,
    identity_lifecycle_work_factory,
    planning_lifecycle_work_factory,
)
from backend.execution.exam_day_closures import (
    ExamDayClosureService,
)
from backend.execution.exam_round_lifecycle import ExamRoundLifecycleService
from backend.identity.authorization import AuthorizationScope
from backend.persistence.assessment import SQLiteAssessmentUnitOfWorkFactory
from backend.persistence.auth import SQLiteAuthenticationRepository
from backend.persistence.database import session_scope
from backend.persistence.exam_lifecycle import SQLiteExamLifecycleUnitOfWorkFactory
from backend.persistence.execution import SQLiteExecutionUnitOfWorkFactory
from backend.persistence.identity import SQLiteIdentityExecutionSnapshotFactory
from backend.persistence.models import (
    AssessmentModelVersion,
    ExamDay,
    ExamDayAuditEvent,
    ExamDayClosure,
    ExamDayExport,
    ExamDayReopening,
    ExamDayTask,
    ExamResult,
    ExamRound,
    ExamRoundAssessmentBinding,
    ExamSlot,
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
from backend.tests.support.port_contracts import assert_materialized_port_value


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

    def test_exam_lifecycle_work_port_results_are_materialized(self) -> None:
        with session_scope(self.db_path) as session:
            model = AssessmentModelVersion(
                model_key="lifecycle-port-contract",
                version=1,
                ihk="IHK Teststadt",
                occupation="Fachinformatiker/in",
                specialization=None,
                training_regulation="Testordnung",
                exam_regulation="Prüfungsordnung",
                ihk_guidelines="Richtlinie",
                valid_from="2026-01-01",
                valid_until="2026-12-31",
                rules_json="{}",
                retention_rule_reference="PrüfO § 1",
                created_by_member_id=1,
            )
            session.add(model)
            session.flush()
            session.add(
                ExamRoundAssessmentBinding(
                    exam_round_id=1,
                    assessment_model_version_id=model.id,
                    bound_by_member_id=1,
                    binding_reason="Materialized port contract fixture",
                )
            )
            result = ExamResult(round_candidate_id=1, source="migration")
            session.add(result)
            session.flush()
            result_id = result.id
        factory = SQLiteExamLifecycleUnitOfWorkFactory(
            SQLiteExecutionUnitOfWorkFactory(
                self.db_path,
                identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
            ),
            SQLiteAssessmentUnitOfWorkFactory(self.db_path),
            self.db_path,
            SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
        )
        auth_context = SQLiteAuthenticationRepository(self.db_path).authenticate(self.chair.token)
        assert auth_context is not None
        scope = authorization_service(self.db_path).scope(auth_context)
        day_closure_service = ExamDayClosureService(
            self.db_path,
            notification_service=notification_service_for_test(self.db_path),
            assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
            planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
            identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
        )
        self.assertFalse(hasattr(day_closure_service, "get_in_session"))
        self.assertFalse(hasattr(day_closure_service, "machine_export_in_session"))
        self.assertFalse(hasattr(day_closure_service, "human_export_in_session"))
        round_lifecycle_service = ExamRoundLifecycleService(
            self.db_path,
            notification_service=notification_service_for_test(self.db_path),
            assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
            planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
            identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
            calendar_lifecycle_work_factory=calendar_lifecycle_work_factory(),
        )
        with factory() as unit_of_work:
            round_snapshot = unit_of_work.planning_lifecycle.round_lifecycle_snapshot(1)
            candidates = unit_of_work.planning_lifecycle.round_candidates(1)
            candidate_ids = tuple(item["candidate_id"] for item in candidates)
            day_slots, day_assignments = unit_of_work.planning_lifecycle.exam_day_plan(2)
            slot_ids = tuple(item.id for item in day_slots)
            reopening_impacts = unit_of_work.assessment_lifecycle.result_reopening_impacts(
                {result_id}
            )
            result_by_id = unit_of_work.assessment_lifecycle.result_by_id(result_id)
            lifecycle_facts = ExamLifecycleApplication._day_closure_facts(unit_of_work, 2, 1)
            lifecycle_day = unit_of_work.execution.read_day_closure(
                day_closure_service, scope, 2, lifecycle_facts
            )
            pending_consequence_ids = unit_of_work.consequences.pending_ids_for_round(1)
            round_facts = ExamLifecycleApplication._round_facts(unit_of_work, 1)
            lifecycle_round = unit_of_work.execution.read_round_lifecycle(
                round_lifecycle_service, scope, 1, pending_consequence_ids, round_facts
            )
            expected_round_view = round_lifecycle_service._view(
                unit_of_work.execution._session,
                round_facts.round,
                scope,
                facts=round_facts,
                pending_consequence_ids=pending_consequence_ids,
            )
            self.assertEqual(expected_round_view, lifecycle_round)
            day_export = unit_of_work.execution.export_day(
                day_closure_service, scope, 2, human=False, facts=lifecycle_facts
            )
            round_export = unit_of_work.execution.export_round(
                round_lifecycle_service, scope, 1, human=False
            )
            round_results = unit_of_work.assessment_lifecycle.results_for_round(1)
            candidate_result = unit_of_work.assessment_lifecycle.result_for_round_candidate(
                candidates[0]["id"] if candidates else -1
            )
            self.assertIsNotNone(result_by_id)
            assert result_by_id is not None
            self.assertEqual(result_id, result_by_id["id"])
            self.assertTrue(round_results)
            assert_materialized_port_value(self, lifecycle_round)
            self.assertFalse(hasattr(round_lifecycle_service, "get"))
            self.assertFalse(hasattr(round_lifecycle_service, "get_in_session"))
            self.assertTrue(any(item["id"] == result_id for item in round_results))
            self.assertIsNotNone(candidate_result)
            assert candidate_result is not None
            self.assertEqual(result_id, candidate_result["id"])
            values = (
                round_snapshot,
                candidates,
                unit_of_work.planning_lifecycle.candidate_details(candidate_ids),
                unit_of_work.planning_lifecycle.round_candidate(1, candidates[0]["id"]),
                unit_of_work.planning_lifecycle.candidate_assignment(candidates[0]["id"], 1),
                unit_of_work.planning_lifecycle.lifecycle_context(1, 1, candidate_ids),
                unit_of_work.planning_lifecycle.dependency_counts(1),
                day_slots,
                day_assignments,
                unit_of_work.planning_lifecycle.exam_day_assignments((2,)),
                unit_of_work.planning_lifecycle.exam_day_slots((2,)),
                unit_of_work.planning_lifecycle.exam_day_slot_ids((2,)),
                unit_of_work.execution.exam_day_round_id(2),
                unit_of_work.execution.exam_day_ids_for_round(1),
                unit_of_work.execution.candidate_attendance_for_slots(slot_ids),
                unit_of_work.execution.member_attendance_for_day(2, (1, 2, 3)),
                unit_of_work.execution.absence_reports_for_day(2),
                unit_of_work.consequences.pending_ids_for_round(1),
                lifecycle_day,
                lifecycle_round,
                day_export,
                round_export,
                lifecycle_facts.candidate_attendance,
                lifecycle_facts.member_attendance,
                lifecycle_facts.absences,
                lifecycle_facts.protocol_day_snapshot,
                unit_of_work.assessment_lifecycle.day_completion(2),
                unit_of_work.assessment_lifecycle.results_for_day_slots(2, slot_ids),
                reopening_impacts,
                result_by_id,
                round_results,
                candidate_result,
                unit_of_work.identity_lifecycle.committee_members(1),
                unit_of_work.identity_lifecycle.committee(1),
            )

        for value in values:
            assert_materialized_port_value(self, value)

    def test_exam_lifecycle_read_scope_pins_one_snapshot_without_write_intent(self) -> None:
        factory = SQLiteExamLifecycleUnitOfWorkFactory(
            SQLiteExecutionUnitOfWorkFactory(
                self.db_path,
                identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
            ),
            SQLiteAssessmentUnitOfWorkFactory(self.db_path),
            self.db_path,
            SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
        )
        with factory.read_scope() as unit_of_work:
            before = unit_of_work.planning_lifecycle.round_lifecycle_snapshot(1)
            self.assertIsNotNone(before)
            with session_scope(self.db_path, begin_immediate=True) as writer:
                writer.get(ExamRound, 1).revision += 1
            after = unit_of_work.planning_lifecycle.round_lifecycle_snapshot(1)

        self.assertIsNotNone(after)
        self.assertEqual(before.revision, after.revision)
        with session_scope(self.db_path) as session:
            self.assertEqual(before.revision + 1, session.get(ExamRound, 1).revision)

    def test_closure_evaluation_keeps_finding_order(self) -> None:
        service = ExamDayClosureService(
            self.db_path,
            notification_service=notification_service_for_test(self.db_path),
            assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
            planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
            identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
        )
        factory = SQLiteExamLifecycleUnitOfWorkFactory(
            SQLiteExecutionUnitOfWorkFactory(
                self.db_path,
                identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
            ),
            SQLiteAssessmentUnitOfWorkFactory(self.db_path),
            self.db_path,
            SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
        )
        with factory.read_scope() as unit_of_work:
            facts = ExamLifecycleApplication._day_closure_facts(unit_of_work, 2, 1)
            evaluation = service._evaluate(facts, 2)
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
        factory = SQLiteExamLifecycleUnitOfWorkFactory(
            SQLiteExecutionUnitOfWorkFactory(
                self.db_path,
                identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
            ),
            SQLiteAssessmentUnitOfWorkFactory(self.db_path),
            self.db_path,
            SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
        )
        with factory.read_scope() as unit_of_work:
            facts = ExamLifecycleApplication._day_closure_facts(unit_of_work, 2, 1)
            snapshot = ExamDayClosureService._load_closure_snapshot(facts)
        self.assertEqual(1, len(snapshot.slots))
        self.assertEqual("cancelled", snapshot.slots[0].execution_status)
        self.assertTrue(all(not hasattr(value, "_sa_instance_state") for value in snapshot.slots))
        assert_materialized_port_value(self, snapshot)

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
        assert_materialized_port_value(self, receipt)

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

    def test_day_export_prefers_current_closure_over_newer_noncurrent_history(self) -> None:
        with session_scope(self.db_path) as session:
            current = ExamDayClosure(
                exam_day_id=3,
                requested_revision=1,
                resulting_revision=2,
                closure_type="regular",
                actor_member_id=1,
                reason=None,
                clarification_attempts=None,
                checklist_json="[]",
                warnings_json="[]",
                protocol_references_json="[]",
                result_references_json="[]",
                status="current",
                command_fingerprint="a" * 64,
            )
            newer = ExamDayClosure(
                exam_day_id=3,
                requested_revision=2,
                resulting_revision=3,
                closure_type="regular",
                actor_member_id=1,
                reason=None,
                clarification_attempts=None,
                checklist_json="[]",
                warnings_json="[]",
                protocol_references_json="[]",
                result_references_json="[]",
                status="superseded",
                command_fingerprint="b" * 64,
            )
            session.add_all([current, newer])
            session.flush()
            current_closure_id = current.id
            newer_closure_id = newer.id

        factory = SQLiteExamLifecycleUnitOfWorkFactory(
            SQLiteExecutionUnitOfWorkFactory(
                self.db_path,
                identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
            ),
            SQLiteAssessmentUnitOfWorkFactory(self.db_path),
            self.db_path,
            SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
        )
        auth_context = SQLiteAuthenticationRepository(self.db_path).authenticate(self.chair.token)
        assert auth_context is not None
        scope = authorization_service(self.db_path).scope(auth_context)
        service = ExamDayClosureService(
            self.db_path,
            notification_service=notification_service_for_test(self.db_path),
            assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
            planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
            identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
        )
        with factory() as unit_of_work:
            facts = ExamLifecycleApplication._day_closure_facts(unit_of_work, 3, 1)
            exported = unit_of_work.execution.export_day(
                service, scope, 3, human=False, facts=facts
            )
        self.assertLess(current_closure_id, newer_closure_id)
        self.assertEqual(
            [current_closure_id, newer_closure_id],
            [item["id"] for item in exported["closure"]["history"] if item["kind"] == "closure"],
        )
        with session_scope(self.db_path) as session:
            export = session.query(ExamDayExport).filter_by(exam_day_id=3).one()
            self.assertEqual(current_closure_id, export.closure_id)

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
        closed = application.close_exam_day(
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
        assert_materialized_port_value(self, closed)
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
            updated_completion = next(
                (
                    item
                    for item in args[3].assessment_completion["slots"]
                    if item["exam_result_id"] == 2
                ),
                None,
            )
            self.assertIsNotNone(updated_completion)
            self.assertTrue(updated_completion["correction_open"])
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

    def test_lifecycle_assessment_projection_accepts_unbound_legacy_results(self) -> None:
        with session_scope(self.db_path) as session:
            day = session.get(ExamDay, 3)
            slot = session.scalar(select(ExamSlot).where(ExamSlot.exam_day_id == day.id))
            result = session.scalar(
                select(ExamResult).where(ExamResult.round_candidate_id == slot.round_candidate_id)
            )
            if result is None:
                result = ExamResult(
                    round_candidate_id=slot.round_candidate_id,
                    source="migration",
                    legacy_status="no_result_data_in_lzug",
                )
                session.add(result)
                session.flush()
            session.query(ExamRoundAssessmentBinding).filter_by(
                exam_round_id=day.exam_round_id
            ).delete()
            lifecycle = SQLiteAssessmentLifecycleAdapter(
                SQLiteAssessmentUnitOfWorkFactory(self.db_path)
            )(session)
            day_results = lifecycle.results_for_day_slots(day.id, [slot.id])
            round_results = lifecycle.results_for_round(day.exam_round_id)
            impacts = lifecycle.result_reopening_impacts({result.id})
            result_id = result.id

        self.assertEqual([result_id], [item["id"] for item in day_results])
        self.assertFalse(day_results[0]["has_assessment_binding"])
        self.assertIn(result_id, {item["id"] for item in round_results})
        self.assertEqual([None], [item["current_determination"] for item in impacts])

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

        reopened = application.reopen_exam_day(
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
        assert_materialized_port_value(self, reopened)
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
