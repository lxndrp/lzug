from __future__ import annotations

import unittest
from http import HTTPStatus
from unittest.mock import patch

from sqlalchemy import select, text

from backend.execution.exam_round_lifecycle import ExamRoundConflictError, ExamRoundLifecycleService
from backend.identity.auth import AuthenticationRepository
from backend.identity.authorization import AuthorizationService
from backend.persistence.database import session_scope
from backend.persistence.models import (
    CalendarEvent,
    CandidateCommitteeAssignment,
    Committee,
    ExamDay,
    ExamRound,
    ExamRoundAuditEvent,
    ExamRoundDecision,
    ExamRoundExport,
    ExamRoundReopening,
    ExamRoundTask,
    ExamSlot,
    Notification,
    RoundCandidate,
)
from backend.tests.fixture_data import prepare_exam_protocol_scenario
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


class ExamRoundLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        authentication = AuthenticationRepository(self.db_path)
        self.chair = authentication.create_session(1)
        self.examiner = authentication.create_session(2)
        self.deputy = authentication.create_session(3)
        operator = authentication.create_account(
            "exam-round-lifecycle.operator@example.invalid", is_operator=True
        )
        self.operator = authentication.create_session(operator["id"])

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def test_closure_matrix_equal_management_lock_reopening_and_exports(self) -> None:
        with ApiServer(self.db_path) as api:
            status, initial = api.request(
                "GET", "/api/exam-rounds/1/lifecycle", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertFalse(initial["evaluation"]["ready"])
            self.assertEqual(
                {"round_has_confirmed_plan", "candidates_terminal"},
                {item["code"] for item in initial["evaluation"]["items"] if not item["ok"]},
            )

            for credentials in (self.examiner, self.operator):
                status, _error = api.request(
                    "POST",
                    "/api/exam-rounds/1/closure",
                    {"revision": 1, "confirmed": True},
                    credentials=credentials,
                )
                assert_status(status, HTTPStatus.FORBIDDEN)

            status, validation = api.request(
                "POST",
                "/api/exam-rounds/1/closure",
                {"revision": 1, "confirmed": True},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.UNPROCESSABLE_ENTITY)
            self.assertEqual("exam_round_prerequisites_failed", validation["error"]["code"])
            self.assertEqual(2, len(validation["error"]["findings"]))

            self._make_round_closable()
            command = {"revision": 1, "confirmed": True}
            status, closed = api.request(
                "POST", "/api/exam-rounds/1/closure", command, credentials=self.deputy
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(("closed", 2), (closed["status"], closed["revision"]))

            status, repeated = api.request(
                "POST", "/api/exam-rounds/1/closure", command, credentials=self.deputy
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(2, repeated["revision"])

            status, _locked = api.request(
                "PATCH",
                "/api/exam-rounds/1",
                {"name": "Unzulässige nachträgliche Änderung"},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.CONFLICT)

            status, first_export = api.request(
                "GET", "/api/exam-rounds/1/lifecycle/export.json", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("closed", first_export["lifecycle"]["status"])
            status, headers, content = api.request_raw(
                "GET", "/api/exam-rounds/1/lifecycle/export.txt", credentials=self.chair
            )
            assert_status(status, HTTPStatus.OK)
            self.assertIn("text/plain", headers["content-type"])
            self.assertIn("Prüfungsrundennachweis 1", content.decode("utf-8"))

            reopening = {
                "revision": 2,
                "occasion": "Berichtigungsantrag",
                "source": "IHK-Vorgang TEST-89",
                "reason": "Die Rundenbezeichnung muss nachweisbar berichtigt werden",
                "scope": [{"kind": "planning", "entity_id": 1}],
            }
            status, reopened = api.request(
                "POST", "/api/exam-rounds/1/reopenings", reopening, credentials=self.deputy
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(("reopening", 3), (reopened["status"], reopened["revision"]))
            self.assertTrue(all(item["obsolete"] for item in reopened["exports"]))

            status, _unaffected = api.request(
                "PUT",
                "/api/exam-rounds/1/candidates/1/terminal-status",
                {
                    "revision": 3,
                    "terminal_status": "postponed",
                    "reason": "Nicht freigegebener Bereich",
                    "postponed_until": "2027-12-01",
                },
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.CONFLICT)
            status, updated = api.request(
                "PATCH",
                "/api/exam-rounds/1",
                {"name": "Berichtigte Prüfungsrunde"},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("Berichtigte Prüfungsrunde", updated["name"])

            status, reclosed = api.request(
                "POST",
                "/api/exam-rounds/1/closure",
                {"revision": 3, "confirmed": True},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(("closed", 4), (reclosed["status"], reclosed["revision"]))
            self.assertEqual("reclosed", reclosed["history"][-1]["event_type"])

        with session_scope(self.db_path) as session:
            self.assertEqual(2, session.query(ExamRoundDecision).count())
            self.assertEqual(1, session.query(ExamRoundReopening).count())
            self.assertEqual(2, session.query(ExamRoundExport).count())

    def test_cancellation_requires_no_started_slot_and_terminal_candidates(self) -> None:
        with session_scope(self.db_path) as session:
            session.execute(
                text(
                    "UPDATE round_candidate SET terminal_status = 'postponed', is_active = 0, "
                    "terminal_reason = 'Neue verbindliche Planung', "
                    "postponed_until = '2027-12-01', terminal_at = CURRENT_TIMESTAMP "
                    "WHERE exam_round_id = 1"
                )
            )
            session.execute(
                text(
                    "UPDATE candidate_committee_assignment SET ended_at = CURRENT_TIMESTAMP "
                    "WHERE exam_round_id = 1"
                )
            )
            session.execute(
                text(
                    "INSERT INTO exam_day (id, exam_round_id, room_id, date, status) "
                    "VALUES (50, 1, 1, '2027-05-01', 'confirmed')"
                )
            )
            session.execute(
                text(
                    "INSERT INTO exam_slot (id, exam_day_id, round_candidate_id, slot_type, "
                    "starts_at, ends_at, sequence_number, status, execution_status, "
                    "actual_started_at) VALUES (50, 50, 1, 'regular', "
                    "'2027-05-01T09:00:00+02:00', '2027-05-01T10:00:00+02:00', 1, "
                    "'confirmed', 'running', '2027-05-01T09:01:00+02:00')"
                )
            )

        with ApiServer(self.db_path) as api:
            status, blocked = api.request(
                "POST",
                "/api/exam-rounds/1/cancellation",
                {"revision": 1, "confirmed": True, "reason": "Vollständige Absage"},
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.UNPROCESSABLE_ENTITY)
            self.assertEqual("no_slot_started", blocked["error"]["findings"][0]["code"])

    def test_cancellation_cancels_future_calendar_and_notifies_idempotently(self) -> None:
        with session_scope(self.db_path) as session:
            session.execute(
                text(
                    "UPDATE round_candidate SET terminal_status = 'postponed', is_active = 0, "
                    "terminal_reason = 'Neue verbindliche Planung', "
                    "postponed_until = '2027-12-01', terminal_at = CURRENT_TIMESTAMP "
                    "WHERE exam_round_id = 1"
                )
            )
            session.execute(
                text(
                    "UPDATE candidate_committee_assignment SET ended_at = CURRENT_TIMESTAMP "
                    "WHERE exam_round_id = 1"
                )
            )
            session.execute(
                text(
                    "INSERT INTO exam_day (id, exam_round_id, room_id, date, status) "
                    "VALUES (50, 1, 1, '2027-05-01', 'confirmed')"
                )
            )
            session.execute(
                text(
                    "INSERT INTO exam_slot (id, exam_day_id, round_candidate_id, slot_type, "
                    "starts_at, ends_at, sequence_number, status) VALUES "
                    "(50, 50, 1, 'regular', '2027-05-01T09:00:00+02:00', "
                    "'2027-05-01T10:00:00+02:00', 1, 'confirmed')"
                )
            )
            session.execute(
                text(
                    "INSERT INTO calendar_event (external_event_id, exam_half_year_id, "
                    "exam_round_id, exam_day_id, recipient_member_id, date, starts_at, "
                    "ends_at, time_zone, location, role, round_name, secure_reference, "
                    "source_key, status, content_hash) VALUES "
                    "('round-89-calendar', 1, 1, 50, 1, '2027-05-01', "
                    "'2027-05-01T09:00:00+02:00', '2027-05-01T10:00:00+02:00', "
                    "'Europe/Berlin', 'Raum 101', 'Vorsitz', 'Prüfungsrunde', "
                    "'/pruefungsplanung', 'round-89-calendar', 'sent', :content_hash)"
                ),
                {"content_hash": "b" * 64},
            )

        command = {
            "revision": 1,
            "confirmed": True,
            "reason": "Die Prüfungsrunde kann nicht stattfinden",
        }
        with ApiServer(self.db_path) as api:
            status, cancelled = api.request(
                "POST",
                "/api/exam-rounds/1/cancellation",
                command,
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(("cancelled", 2), (cancelled["status"], cancelled["revision"]))

            status, repeated = api.request(
                "POST",
                "/api/exam-rounds/1/cancellation",
                command,
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(2, repeated["revision"])

        with session_scope(self.db_path) as session:
            day = session.get(ExamDay, 50)
            slot = session.get(ExamSlot, 50)
            event = session.scalar(
                select(CalendarEvent).where(CalendarEvent.external_event_id == "round-89-calendar")
            )
            self.assertEqual("cancelled", day.status)
            self.assertEqual(("cancelled", "cancelled"), (slot.status, slot.execution_status))
            self.assertEqual(("cancelled", 2), (event.status, event.version))
            self.assertEqual(
                1,
                session.query(ExamRoundDecision)
                .filter_by(exam_round_id=1, decision_type="cancel")
                .count(),
            )
            self.assertGreaterEqual(
                session.query(Notification)
                .filter_by(exam_round_id=1, event_type="plan_changed")
                .count(),
                1,
            )

    def test_openapi_publishes_every_lifecycle_operation(self) -> None:
        with ApiServer(self.db_path) as api:
            status, document = api.request("GET", "/api/openapi.json")
            assert_status(status, HTTPStatus.OK)

        expected = {
            "/api/exam-rounds/{id}/lifecycle": {"get"},
            "/api/exam-rounds/{id}/closure": {"post"},
            "/api/exam-rounds/{id}/cancellation": {"post"},
            "/api/exam-rounds/{id}/reopening-impact": {"post"},
            "/api/exam-rounds/{id}/reopenings": {"post"},
            "/api/exam-rounds/{id}/candidates/{candidate_id}/terminal-status": {"put"},
            "/api/exam-rounds/{id}/results/{result_id}/ihk-status": {"put"},
            "/api/exam-rounds/{id}/lifecycle/export.json": {"get"},
            "/api/exam-rounds/{id}/lifecycle/export.txt": {"get"},
        }
        for path, methods in expected.items():
            self.assertEqual(methods, set(document["paths"][path]))

    def test_later_ihk_document_status_remains_allowed_on_a_closed_round(self) -> None:
        prepare_exam_protocol_scenario(self.db_path)
        self.deputy = AuthenticationRepository(self.db_path).create_session(3)
        with session_scope(self.db_path) as session:
            session.execute(
                text(
                    "UPDATE exam_round SET lifecycle_status = 'closed', revision = 2 "
                    "WHERE id = 2"
                )
            )

        payload = {
            "document_status": "Zeugnis extern zugestellt",
            "document_reference": "IHK-TEST-89-1",
        }
        with ApiServer(self.db_path) as api:
            status, documented = api.request(
                "PUT",
                "/api/exam-rounds/2/results/1/ihk-status",
                payload,
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(1, len(documented["ihk_statuses"]))
            self.assertEqual("closed", documented["status"])

            status, repeated = api.request(
                "PUT",
                "/api/exam-rounds/2/results/1/ihk-status",
                payload,
                credentials=self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(1, len(repeated["ihk_statuses"]))

    def test_decision_and_reopening_rollback_and_replay_preserve_all_evidence(self) -> None:
        self._make_round_closable()
        service = ExamRoundLifecycleService(self.db_path)
        context = AuthenticationRepository(self.db_path).authenticate(self.chair.token)
        scope = AuthorizationService(self.db_path).scope(context)
        close = {"revision": 1, "confirmed": True}
        with (
            patch.object(service, "_view", side_effect=RuntimeError("test view failure")),
            self.assertRaisesRegex(RuntimeError, "test view failure"),
        ):
            service.close(scope, 1, close)
        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, 1)
            self.assertEqual(("open", 1), (exam_round.lifecycle_status, exam_round.revision))
            self.assertEqual(0, session.query(ExamRoundDecision).count())
            self.assertEqual(0, session.query(ExamRoundAuditEvent).count())

        service.close(scope, 1, close)
        service.machine_export(scope, 1)
        command = {
            "revision": 2,
            "occasion": "Berichtigung",
            "source": "IHK-Vorgang",
            "reason": "Rundenbezeichnung korrigieren",
            "scope": [{"kind": "planning", "entity_id": 1}],
        }
        with (
            patch.object(service, "_view", side_effect=RuntimeError("test view failure")),
            patch.object(service, "_notify") as notify,
            self.assertRaisesRegex(RuntimeError, "test view failure"),
        ):
            service.reopen(scope, 1, command)
        notify.assert_not_called()
        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, 1)
            self.assertEqual(("closed", 2), (exam_round.lifecycle_status, exam_round.revision))
            self.assertEqual("current", session.scalar(select(ExamRoundDecision)).status)
            self.assertIsNone(session.scalar(select(ExamRoundExport)).superseded_at)
            self.assertEqual(0, session.query(ExamRoundReopening).count())
            self.assertEqual(0, session.query(ExamRoundTask).count())
            self.assertEqual(1, session.query(ExamRoundAuditEvent).count())

        with patch.object(service, "_notify", wraps=service._notify) as notify:
            reopened = service.reopen(scope, 1, command)
            repeated = service.reopen(scope, 1, command)
        notify.assert_called_once()
        self.assertEqual(reopened, repeated)
        self.assertEqual(2, len(reopened["tasks"]))
        self.assertEqual({"reconfirmation"}, {item["task_type"] for item in reopened["tasks"]})
        with self.assertRaises(ExamRoundConflictError):
            service.reopen(scope, 1, {**command, "reason": "Anderer Auftrag"})
        reclosed = service.close(scope, 1, {"revision": 3, "confirmed": True})
        self.assertEqual("reclosed", reclosed["history"][-1]["event_type"])
        self.assertTrue(all(item["status"] == "completed" for item in reclosed["tasks"]))
        with session_scope(self.db_path) as session:
            self.assertEqual(2, session.query(ExamRoundDecision).count())
            self.assertEqual(1, session.query(ExamRoundReopening).count())
            self.assertEqual(3, session.query(ExamRoundAuditEvent).count())

    def test_terminal_candidate_evidence_and_revision_guard_precede_mutation(self) -> None:
        service = ExamRoundLifecycleService(self.db_path)
        context = AuthenticationRepository(self.db_path).authenticate(self.chair.token)
        scope = AuthorizationService(self.db_path).scope(context)
        for details in (
            {"terminal_status": "result_communicated"},
            {"terminal_status": "transferred", "reason": "Wechsel"},
            {"terminal_status": "transferred", "reason": "Wechsel", "effective_new_round_id": 9999},
            {"terminal_status": "transferred", "reason": "Wechsel", "effective_new_round_id": 1},
            {"terminal_status": "postponed", "reason": "Verschiebung"},
            {"terminal_status": "ihk_terminated", "reason": "Beendigung"},
        ):
            with self.subTest(details=details), self.assertRaises(ValueError):
                service.set_candidate_terminal_status(scope, 1, 1, {"revision": 1, **details})
            with session_scope(self.db_path) as session:
                self.assertEqual(1, session.get(ExamRound, 1).revision)
                self.assertEqual("open", session.get(RoundCandidate, 1).terminal_status)

        command = {
            "revision": 1,
            "terminal_status": "postponed",
            "reason": "Neue Planung",
            "postponed_until": "2027-12-01",
        }
        with (
            patch.object(service, "_view", side_effect=RuntimeError("test view failure")),
            self.assertRaisesRegex(RuntimeError, "test view failure"),
        ):
            service.set_candidate_terminal_status(scope, 1, 1, command)
        with session_scope(self.db_path) as session:
            self.assertIsNone(
                session.scalar(
                    select(CandidateCommitteeAssignment).where(
                        CandidateCommitteeAssignment.round_candidate_id == 1
                    )
                ).ended_at
            )
        service.set_candidate_terminal_status(scope, 1, 1, command)
        with self.assertRaises(ExamRoundConflictError):
            service.set_candidate_terminal_status(scope, 1, 1, command)
        with session_scope(self.db_path) as session:
            candidate = session.get(RoundCandidate, 1)
            self.assertEqual(
                ("postponed", 0, "2027-12-01"),
                (candidate.terminal_status, candidate.is_active, candidate.postponed_until),
            )
            ended_at = session.scalar(
                select(CandidateCommitteeAssignment).where(
                    CandidateCommitteeAssignment.round_candidate_id == 1
                )
            ).ended_at
            self.assertIsNotNone(ended_at)
        service.set_candidate_terminal_status(
            scope,
            1,
            1,
            {
                "revision": 2,
                "terminal_status": "ihk_terminated",
                "reason": "IHK-Entscheidung",
                "ihk_decision_reference": "IHK-754",
            },
        )
        service.set_candidate_terminal_status(
            scope, 1, 1, {"revision": 3, "terminal_status": "open"}
        )
        with session_scope(self.db_path) as session:
            candidate = session.get(RoundCandidate, 1)
            self.assertEqual(
                ("open", 0, None, None, None),
                (
                    candidate.terminal_status,
                    candidate.is_active,
                    candidate.postponed_until,
                    candidate.ihk_decision_reference,
                    candidate.terminal_at,
                ),
            )
            self.assertEqual(
                ended_at,
                session.scalar(
                    select(CandidateCommitteeAssignment).where(
                        CandidateCommitteeAssignment.round_candidate_id == 1
                    )
                ).ended_at,
            )

    def test_transferred_status_requires_effective_assignment_in_the_target_round(self) -> None:
        service = ExamRoundLifecycleService(self.db_path)
        context = AuthenticationRepository(self.db_path).authenticate(self.chair.token)
        scope = AuthorizationService(self.db_path).scope(context)
        with session_scope(self.db_path) as session:
            target_committee = Committee(
                name="Zielausschuss", ihk="IHK Teststadt", occupation="Fachinformatiker/in"
            )
            session.add(target_committee)
            session.flush()
            target = ExamRound(
                exam_half_year_id=1,
                committee_id=target_committee.id,
                name="Neue Zuordnung",
                created_by_member_id=1,
            )
            session.add(target)
            session.flush()
            target_id = target.id
        command = {
            "revision": 1,
            "terminal_status": "transferred",
            "reason": "Wirksamer Wechsel",
            "effective_new_round_id": target_id,
        }
        with self.assertRaisesRegex(ValueError, "nicht wirksam"):
            service.set_candidate_terminal_status(scope, 1, 1, command)
        with session_scope(self.db_path) as session:
            original = session.get(RoundCandidate, 1)
            assignment = session.scalar(
                select(CandidateCommitteeAssignment).where(
                    CandidateCommitteeAssignment.round_candidate_id == 1
                )
            )
            assignment.ended_at = "2026-09-10T10:00:00+00:00"
            transferred = RoundCandidate(
                exam_round_id=target_id,
                candidate_id=original.candidate_id,
                attempt_number=original.attempt_number,
            )
            session.add(transferred)
            session.flush()
            session.add(
                CandidateCommitteeAssignment(
                    candidate_id=original.candidate_id,
                    exam_half_year_id=1,
                    exam_round_id=target_id,
                    round_candidate_id=transferred.id,
                )
            )
        service.set_candidate_terminal_status(scope, 1, 1, command)
        with session_scope(self.db_path) as session:
            candidate = session.get(RoundCandidate, 1)
            self.assertEqual(
                ("transferred", 0, target_id),
                (
                    candidate.terminal_status,
                    candidate.is_active,
                    candidate.effective_new_round_id,
                ),
            )
            self.assertEqual(2, session.get(ExamRound, 1).revision)
            self.assertEqual(
                "2026-09-10T10:00:00+00:00",
                session.scalar(
                    select(CandidateCommitteeAssignment).where(
                        CandidateCommitteeAssignment.round_candidate_id == 1
                    )
                ).ended_at,
            )

    def _make_round_closable(self) -> None:
        with session_scope(self.db_path) as session:
            session.execute(text("UPDATE exam_round SET status = 'plan_confirmed' WHERE id = 1"))
            session.execute(
                text(
                    "UPDATE round_candidate SET terminal_status = 'postponed', is_active = 0, "
                    "terminal_reason = 'Verbindliche Nachplanung', "
                    "postponed_until = '2027-12-01', terminal_at = CURRENT_TIMESTAMP "
                    "WHERE exam_round_id = 1"
                )
            )
            session.execute(
                text(
                    "UPDATE candidate_committee_assignment SET ended_at = CURRENT_TIMESTAMP "
                    "WHERE exam_round_id = 1"
                )
            )
            session.execute(
                text(
                    "INSERT INTO exam_day (id, exam_round_id, room_id, date, status, "
                    "revision, closure_status) VALUES "
                    "(50, 1, 1, '2027-05-01', 'completed', 2, 'closed')"
                )
            )
            session.execute(
                text(
                    "INSERT INTO exam_day_closure (exam_day_id, requested_revision, "
                    "resulting_revision, closure_type, actor_member_id, checklist_json, "
                    "warnings_json, protocol_references_json, result_references_json, "
                    "status, command_fingerprint) VALUES "
                    "(50, 1, 2, 'regular', 1, '[]', '[]', '[]', '[]', 'current', :fingerprint)"
                ),
                {"fingerprint": "a" * 64},
            )


if __name__ == "__main__":
    unittest.main()
