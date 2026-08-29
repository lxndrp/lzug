from __future__ import annotations

import unittest
from http import HTTPStatus
from unittest.mock import patch

from sqlalchemy import text

from backend.auth import AuthenticationRepository
from backend.database import session_scope
from backend.models import ExamDay, ExamDayClosure, ExamDayExport, ExamDayTask, Notification
from backend.tests.helpers import ApiServer, TempDatabase, assert_status
from demo.artifacts import _add_exam_protocol_scenario


class ExamDayClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        _add_exam_protocol_scenario(self.db_path)
        authentication = AuthenticationRepository(self.db_path)
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
            "backend.exam_day_closures.NotificationService.create_direct",
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
                _add_exam_protocol_scenario(db_path)
                authentication = AuthenticationRepository(db_path)
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
