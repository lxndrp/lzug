from __future__ import annotations

import sqlite3
import unittest
from contextlib import closing
from http import HTTPStatus
from threading import Barrier, Thread
from unittest.mock import patch

from sqlalchemy import select

from backend.composition import authorization_service, exam_protocol_service
from backend.execution.exam_protocols import (
    ENTRY_CATEGORIES,
    ExamProtocolConflictError,
)
from backend.execution.slot_service import ExecutionService
from backend.persistence.auth import SQLiteAuthenticationRepository
from backend.persistence.database import initialize, session_scope
from backend.persistence.day_mutations import ExecutionDayMutationConflictError
from backend.persistence.execution import (
    SQLiteExecutionUnitOfWorkFactory,
    create_started_protocol,
)
from backend.persistence.identity import SQLiteIdentityExecutionSnapshotFactory
from backend.persistence.models import (
    CandidateExamAttendance,
    ExamDay,
    ExamDayAssignment,
    ExamProtocol,
    ExamProtocolParticipant,
    ExamProtocolResponse,
    ExamProtocolRevision,
    ExamRound,
    ExamSlot,
    MemberExamAttendance,
)
from backend.tests.helpers import ApiServer, TempDatabase, assert_status
from backend.tests.test_database import rewind_exam_protocol_migration


class ExamProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        self.authentication = SQLiteAuthenticationRepository(self.db_path)
        self.chair = self.authentication.create_session(1)
        self.examiner = self.authentication.create_session(2)
        outsider = self.authentication.create_account(
            "testperson.delta.account@example.invalid", person_id=4
        )
        operator = self.authentication.create_account(
            "protocol.operator@example.invalid", is_operator=True
        )
        self.deputy = self.authentication.create_session(3)
        self.outsider = self.authentication.create_session(outsider["id"])
        self.operator = self.authentication.create_session(operator["id"])

        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, 1)
            exam_round.status = "plan_confirmed"
            day = ExamDay(
                exam_round_id=1,
                room_id=1,
                date="2026-11-16",
                status="confirmed",
                lunch_break_enabled=1,
                created_from_proposal=1,
            )
            session.add(day)
            session.flush()
            slot = ExamSlot(
                exam_day_id=day.id,
                round_candidate_id=1,
                slot_type="regular",
                starts_at="2026-11-16T09:00:00+01:00",
                ends_at="2026-11-16T10:00:00+01:00",
                sequence_number=1,
                status="confirmed",
                actual_started_at="2026-11-16T09:03:00+01:00",
                execution_status="running",
                status_changed_at="2026-11-16T09:03:00+01:00",
            )
            session.add(slot)
            session.flush()
            session.add_all(
                ExamDayAssignment(
                    exam_day_id=day.id,
                    committee_member_id=member_id,
                    assignment_role="examiner",
                    day_part="full_day",
                )
                for member_id in (1, 2, 3)
            )
            session.add(
                CandidateExamAttendance(
                    exam_slot_id=slot.id,
                    status="present",
                    arrived_at="2026-11-16T08:55:00+01:00",
                )
            )
            session.add_all(
                (
                    MemberExamAttendance(
                        exam_day_id=day.id,
                        committee_member_id=1,
                        status="present",
                        arrived_at="2026-11-16T08:45:00+01:00",
                    ),
                    MemberExamAttendance(
                        exam_day_id=day.id,
                        committee_member_id=2,
                        status="absent",
                    ),
                    MemberExamAttendance(
                        exam_day_id=day.id,
                        committee_member_id=3,
                        status="late",
                        arrived_at="2026-11-16T09:01:00+01:00",
                    ),
                )
            )
            protocol_id = create_started_protocol(
                session,
                slot_id=slot.id,
                participant_member_ids={1, 3},
                created_by_member_id=1,
                created_at="2026-11-16T09:03:00+01:00",
            )
            self.day_id = day.id
            self.slot_id = slot.id
            self.protocol_id = protocol_id

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def request(self, api: ApiServer, method: str, suffix: str, payload=None, credentials=None):
        return api.request(
            method,
            f"/api/exam-protocols/{self.protocol_id}{suffix}",
            payload,
            credentials=credentials or self.chair,
        )

    def save_normal(self, api: ApiServer, version: int = 1):
        status, protocol = self.request(
            api,
            "PATCH",
            "",
            {"version": version, "declaration": "without_special_occurrences", "entries": []},
        )
        assert_status(status, HTTPStatus.OK)
        return protocol

    def test_stale_execution_day_revision_remains_an_http_conflict(self) -> None:
        with ApiServer(self.db_path) as api:
            status, result = api.request(
                "PATCH",
                f"/api/confirmed-plan-days/{self.day_id}/slots/{self.slot_id}/attendance",
                {"status": "absent", "day_revision": 0},
                credentials=self.chair,
            )

        assert_status(status, HTTPStatus.CONFLICT)
        self.assertEqual("exam_day_conflict", result["error"]["code"])

    def complete_normal(self, api: ApiServer):
        protocol = self.save_normal(api)
        version = protocol["current_version"]
        status, protocol = self.request(api, "POST", "/submit", {"version": version})
        assert_status(status, HTTPStatus.OK)
        status, protocol = self.request(
            api,
            "POST",
            "/responses",
            {
                "version": version,
                "response": "reservation",
                "statement": "Vorbehalt zur ausdrücklichen Verlaufserklärung.",
            },
        )
        assert_status(status, HTTPStatus.OK)
        status, protocol = self.request(
            api,
            "POST",
            "/responses",
            {"version": version, "response": "confirmed"},
            self.examiner,
        )
        assert_status(status, HTTPStatus.OK)
        return protocol

    def test_structured_versions_reactions_exports_and_data_minimization(self) -> None:
        with ApiServer(self.db_path) as api:
            status, protocol = api.request(
                "GET",
                f"/api/confirmed-plan-days/{self.day_id}/slots/{self.slot_id}/protocol",
                credentials=self.examiner,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual({1, 3}, set(protocol["participants"]))
            self.assertEqual("in_progress", protocol["state"])

            status, error = self.request(
                api,
                "PATCH",
                "",
                {
                    "version": 1,
                    "declaration": "with_special_occurrences",
                    "entries": [
                        {
                            "category": "other",
                            "statement": "Sachlicher Ablauf",
                            "occurred_from": "2026-11-16T09:05:00+01:00",
                            "occurred_to": None,
                            "diagnosis": "nicht zulässig",
                        }
                    ],
                },
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            self.assertIn("unzulässige Felder", error["error"])

            version = 1
            for category in sorted(ENTRY_CATEGORIES):
                status, protocol = self.request(
                    api,
                    "PATCH",
                    "",
                    {
                        "version": version,
                        "declaration": "with_special_occurrences",
                        "entries": [
                            {
                                "category": category,
                                "statement": f"Prüfbarer Sachverhalt: {category}",
                                "occurred_from": "2026-11-16T09:05:00+01:00",
                                "occurred_to": "2026-11-16T09:06:00+01:00",
                            }
                        ],
                    },
                )
                assert_status(status, HTTPStatus.OK)
                version = protocol["current_version"]
                self.assertEqual(category, protocol["current_revision"]["entries"][0]["category"])

            status, _conflict = self.request(
                api,
                "PATCH",
                "",
                {"version": 1, "declaration": "without_special_occurrences", "entries": []},
            )
            assert_status(status, HTTPStatus.CONFLICT)

            status, protocol = self.request(
                api,
                "POST",
                "/submit",
                {"version": version},
                self.examiner,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("awaiting_confirmation", protocol["state"])
            entry_id = protocol["current_revision"]["entries"][0]["id"]

            reservation = {
                "version": version,
                "response": "reservation",
                "entry_id": entry_id,
                "statement": "Vorbehalt bezieht sich auf den dokumentierten Zeitpunkt.",
            }
            status, protocol = self.request(api, "POST", "/responses", reservation)
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("reaction_missing", protocol["state"])
            status, repeated = self.request(api, "POST", "/responses", reservation)
            assert_status(status, HTTPStatus.OK)
            self.assertEqual(
                protocol["current_revision"]["responses"],
                repeated["current_revision"]["responses"],
            )

            status, protocol = self.request(
                api,
                "POST",
                "/responses",
                {"version": version, "response": "confirmed"},
                self.examiner,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("fully_with_reservation", protocol["state"])
            self.assertTrue(protocol["closing_ready"])

            status, exported = self.request(api, "GET", "/export.json")
            assert_status(status, HTTPStatus.OK)
            self.assertTrue(exported["complete"])
            self.assertEqual(len(ENTRY_CATEGORIES) + 1, len(exported["protocol"]["history"]))
            self.assertEqual(False, exported["references"]["assessment"]["available"])
            status, headers, content = api.request_raw(
                "GET",
                f"/api/exam-protocols/{self.protocol_id}/export.txt",
                credentials=self.examiner,
            )
            assert_status(status, HTTPStatus.OK)
            self.assertIn("text/plain", headers["content-type"])
            self.assertIn("VOLLSTÄNDIG", content.decode("utf-8"))

    def test_role_boundaries_correction_reconfirmation_and_retention(self) -> None:
        with ApiServer(self.db_path) as api:
            for credentials in (self.outsider, self.operator):
                status, _body = self.request(api, "GET", "", credentials=credentials)
                assert_status(status, HTTPStatus.FORBIDDEN)

            status, manager_view = self.request(api, "GET", "", credentials=self.deputy)
            assert_status(status, HTTPStatus.OK)
            self.assertFalse(manager_view["permissions"]["edit"])
            self.assertFalse(manager_view["permissions"]["respond"])
            self.assertTrue(manager_view["permissions"]["coordinate_correction"])

            protocol = self.complete_normal(api)
            status, _blocked = self.request(
                api,
                "PATCH",
                "",
                {
                    "version": protocol["current_version"],
                    "declaration": "without_special_occurrences",
                    "entries": [],
                },
            )
            assert_status(status, HTTPStatus.CONFLICT)

            status, protocol = self.request(
                api,
                "POST",
                "/correction-requests",
                {"version": protocol["current_version"], "reason": "Zeitpunkt ergänzen"},
                self.examiner,
            )
            assert_status(status, HTTPStatus.OK)
            request_id = protocol["correction_requests"][0]["id"]

            with session_scope(self.db_path) as session:
                session.get(ExamDay, self.day_id).status = "completed"

            correction = {
                "version": protocol["current_version"],
                "correction_request_id": request_id,
                "reason": "Ergänzungsbedarf koordiniert",
            }
            status, _blocked = self.request(
                api, "POST", "/open-correction", correction, self.deputy
            )
            assert_status(status, HTTPStatus.BAD_REQUEST)
            correction["reopening_reference"] = "Wiederöffnung nach Tagesabschluss #36"
            status, protocol = self.request(
                api, "POST", "/open-correction", correction, self.deputy
            )
            assert_status(status, HTTPStatus.OK)
            self.assertEqual("correction_open", protocol["state"])
            self.assertTrue(protocol["permissions"]["edit"])
            old_version = protocol["current_version"] - 1
            old_revision = next(
                revision for revision in protocol["history"] if revision["version"] == old_version
            )
            self.assertTrue(old_revision["obsolete"])
            self.assertEqual(2, len(old_revision["responses"]))

            status, protocol = self.request(
                api,
                "PATCH",
                "",
                {
                    "version": protocol["current_version"],
                    "declaration": "with_special_occurrences",
                    "entries": [
                        {
                            "category": "late_start",
                            "statement": "Beginn um drei Minuten verspätet.",
                            "occurred_from": "2026-11-16T09:00:00+01:00",
                            "occurred_to": "2026-11-16T09:03:00+01:00",
                        }
                    ],
                },
                self.deputy,
            )
            assert_status(status, HTTPStatus.OK)
            version = protocol["current_version"]
            status, _blocked = self.request(
                api, "POST", "/submit", {"version": version}, self.deputy
            )
            assert_status(status, HTTPStatus.FORBIDDEN)
            status, protocol = self.request(api, "POST", "/submit", {"version": version})
            assert_status(status, HTTPStatus.OK)
            for credentials in (self.chair, self.examiner):
                status, protocol = self.request(
                    api,
                    "POST",
                    "/responses",
                    {"version": version, "response": "confirmed"},
                    credentials,
                )
                assert_status(status, HTTPStatus.OK)
            self.assertEqual("fully_confirmed", protocol["state"])

            retention = {
                "rule_reference": "PrüfO Teststadt § 10",
                "retain_until": "2036-12-31",
                "legal_hold": True,
                "hold_reason": "Laufendes Rechtsmittel",
            }
            status, protocol = self.request(api, "PUT", "/retention", retention, self.deputy)
            assert_status(status, HTTPStatus.OK)
            self.assertTrue(protocol["retention"]["legal_hold"])
            retention.update({"retain_until": "2035-12-31", "legal_hold": False})
            status, _blocked = self.request(api, "PUT", "/retention", retention, self.deputy)
            assert_status(status, HTTPStatus.BAD_REQUEST)

    def test_response_validation_and_failed_day_completion_leave_no_partial_response(self) -> None:
        service = exam_protocol_service(self.db_path)
        context = self.authentication.authenticate(self.chair.token)
        scope = authorization_service(self.db_path).scope(context)
        protocol = service.update_content(
            scope,
            self.protocol_id,
            {"version": 1, "declaration": "without_special_occurrences", "entries": []},
        )
        version = protocol["current_version"]
        service.submit(scope, self.protocol_id, {"version": version})
        for details, message in (
            ({"response": "reservation", "entry_id": True, "statement": "Vorbehalt"}, "Ungültige"),
            (
                {"response": "reservation", "entry_id": 9999, "statement": "Vorbehalt"},
                "aktuellen Stand",
            ),
            ({"response": "reservation", "statement": ""}, "statement"),
            ({"response": "confirmed", "statement": "Vorbehalt"}, "keinen Vorbehaltstext"),
        ):
            with self.subTest(details=details), self.assertRaisesRegex(ValueError, message):
                service.respond(scope, self.protocol_id, {"version": version, **details})

        command = {
            "version": version,
            "response": "reservation",
            "statement": "Dokumentierter Vorbehalt",
        }
        with (
            patch(
                "backend.persistence.execution.complete_day_mutation",
                side_effect=RuntimeError("test day failure"),
            ),
            self.assertRaisesRegex(RuntimeError, "test day failure"),
        ):
            service.respond(scope, self.protocol_id, command)
        with session_scope(self.db_path) as session:
            self.assertEqual(0, session.query(ExamProtocolResponse).count())
        recorded = service.respond(scope, self.protocol_id, command)
        self.assertEqual(recorded, service.respond(scope, self.protocol_id, command))
        with self.assertRaises(ExamProtocolConflictError):
            service.respond(scope, self.protocol_id, {**command, "statement": "Anderer Vorbehalt"})
        with session_scope(self.db_path) as session:
            self.assertEqual(1, session.query(ExamProtocolResponse).count())

    def test_completion_contract_distinguishes_not_started_and_legacy_completed(self) -> None:
        with session_scope(self.db_path) as session:
            cancelled = ExamSlot(
                exam_day_id=self.day_id,
                round_candidate_id=2,
                slot_type="regular",
                starts_at="2026-11-16T10:15:00+01:00",
                ends_at="2026-11-16T11:15:00+01:00",
                sequence_number=2,
                status="confirmed",
                execution_status="cancelled",
                status_reason="Nicht erschienen",
            )
            legacy = ExamSlot(
                exam_day_id=self.day_id,
                round_candidate_id=3,
                slot_type="regular",
                starts_at="2026-11-16T11:30:00+01:00",
                ends_at="2026-11-16T12:30:00+01:00",
                sequence_number=3,
                status="confirmed",
                actual_started_at="2026-11-16T11:31:00+01:00",
                actual_completed_at="2026-11-16T12:29:00+01:00",
                execution_status="completed",
            )
            session.add_all((cancelled, legacy))
            session.flush()
            cancelled_id = cancelled.id
            legacy_id = legacy.id

        with ApiServer(self.db_path) as api:
            status, _missing = api.request(
                "GET",
                f"/api/confirmed-plan-days/{self.day_id}/slots/{cancelled_id}/protocol",
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.NOT_FOUND)
            status, completion = api.request(
                "GET",
                f"/api/confirmed-plan-days/{self.day_id}/protocol-completion",
                credentials=self.chair,
            )
            assert_status(status, HTTPStatus.OK)
            by_slot = {item["exam_slot_id"]: item for item in completion["slots"]}
            self.assertEqual("not_required", by_slot[cancelled_id]["state"])
            self.assertEqual("legacy_missing", by_slot[legacy_id]["state"])
            self.assertTrue(by_slot[cancelled_id]["regular_close_ready"])
            self.assertTrue(by_slot[legacy_id]["regular_close_ready"])
            self.assertFalse(by_slot[self.slot_id]["regular_close_ready"])

    def test_migration_creates_only_required_ongoing_protocols_without_invented_content(
        self,
    ) -> None:
        with session_scope(self.db_path) as session:
            completed = ExamSlot(
                exam_day_id=self.day_id,
                round_candidate_id=2,
                slot_type="regular",
                starts_at="2026-11-16T10:15:00+01:00",
                ends_at="2026-11-16T11:15:00+01:00",
                sequence_number=2,
                status="confirmed",
                actual_started_at="2026-11-16T10:16:00+01:00",
                actual_completed_at="2026-11-16T11:14:00+01:00",
                execution_status="completed",
            )
            session.add(completed)
            session.flush()
            completed_id = completed.id

        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            rewind_exam_protocol_migration(connection, remove_history=True)
            connection.commit()

        initialize(self.db_path)
        with session_scope(self.db_path) as session:
            protocols = list(session.scalars(select(ExamProtocol).order_by(ExamProtocol.id)))
            self.assertEqual([self.slot_id], [protocol.exam_slot_id for protocol in protocols])
            self.assertEqual("migration", protocols[0].source)
            revision = session.scalar(
                select(ExamProtocolRevision).where(
                    ExamProtocolRevision.exam_protocol_id == protocols[0].id
                )
            )
            self.assertIsNone(revision.declaration)
            participants = set(
                session.scalars(
                    select(ExamProtocolParticipant.committee_member_id).where(
                        ExamProtocolParticipant.exam_protocol_id == protocols[0].id
                    )
                )
            )
            self.assertEqual({1, 3}, participants)
            self.assertIsNone(
                session.scalar(
                    select(ExamProtocol).where(ExamProtocol.exam_slot_id == completed_id)
                )
            )


class ExecutionPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, 1)
            exam_round.status = "plan_confirmed"
            day = ExamDay(
                exam_round_id=1,
                room_id=1,
                date="2026-11-16",
                status="confirmed",
                lunch_break_enabled=1,
                created_from_proposal=1,
            )
            session.add(day)
            session.flush()
            slot = ExamSlot(
                exam_day_id=day.id,
                round_candidate_id=1,
                slot_type="regular",
                starts_at="2026-11-16T09:00:00+01:00",
                ends_at="2026-11-16T10:00:00+01:00",
                sequence_number=1,
                status="confirmed",
            )
            session.add(slot)
            session.flush()
            session.add_all(
                ExamDayAssignment(
                    exam_day_id=day.id,
                    committee_member_id=member_id,
                    assignment_role="examiner",
                    day_part="full_day",
                )
                for member_id in (1, 2, 3)
            )
            session.add(CandidateExamAttendance(exam_slot_id=slot.id, status="present"))
            self.day_id = day.id
            self.slot_id = slot.id
        self.execution_factory = SQLiteExecutionUnitOfWorkFactory(
            self.db_path,
            identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
        )
        self.service = ExecutionService(
            self.execution_factory,
            clock=lambda: "2026-11-16T09:03:00+00:00",
        )

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def _mark_quorum_present(self) -> None:
        with session_scope(self.db_path) as session:
            session.add_all(
                MemberExamAttendance(
                    exam_day_id=self.day_id,
                    committee_member_id=member_id,
                    status="present",
                )
                for member_id in (1, 2, 3)
            )

    def test_start_commits_slot_protocol_participants_and_day_revision_together(self) -> None:
        self._mark_quorum_present()
        result = self.service.start_slot(
            self.day_id,
            self.slot_id,
            {"expected_day_revision": 1},
            actor_member_id=1,
        )
        self.assertEqual("running", result["execution_status"])
        with session_scope(self.db_path) as session:
            slot = session.get(ExamSlot, self.slot_id)
            day = session.get(ExamDay, self.day_id)
            protocol = session.query(ExamProtocol).filter_by(exam_slot_id=self.slot_id).one()
            participants = set(
                session.scalars(
                    select(ExamProtocolParticipant.committee_member_id).where(
                        ExamProtocolParticipant.exam_protocol_id == protocol.id
                    )
                )
            )
            self.assertEqual("running", slot.execution_status)
            self.assertEqual("2026-11-16T09:03:00+00:00", slot.actual_started_at)
            self.assertEqual(2, day.revision)
            self.assertEqual({1, 2, 3}, participants)

    def test_quorum_failure_leaves_start_and_revision_unchanged(self) -> None:
        with session_scope(self.db_path) as session:
            session.add(
                MemberExamAttendance(
                    exam_day_id=self.day_id,
                    committee_member_id=1,
                    status="present",
                )
            )
        with self.assertRaisesRegex(ValueError, "Mindestens drei"):
            self.service.start_slot(
                self.day_id,
                self.slot_id,
                {"expected_day_revision": 1},
                actor_member_id=1,
            )
        with session_scope(self.db_path) as session:
            self.assertEqual("open", session.get(ExamSlot, self.slot_id).execution_status)
            self.assertEqual(1, session.get(ExamDay, self.day_id).revision)
            self.assertEqual(
                0,
                session.query(ExamProtocol).filter_by(exam_slot_id=self.slot_id).count(),
            )

    def test_protocol_failure_rolls_back_slot_mutation_and_revision(self) -> None:
        self._mark_quorum_present()
        with patch(
            "backend.persistence.execution.create_started_protocol",
            side_effect=RuntimeError("protocol write failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "protocol write failed"):
                self.service.start_slot(
                    self.day_id,
                    self.slot_id,
                    {"expected_day_revision": 1},
                    actor_member_id=1,
                )
        with session_scope(self.db_path) as session:
            self.assertEqual("open", session.get(ExamSlot, self.slot_id).execution_status)
            self.assertEqual(1, session.get(ExamDay, self.day_id).revision)
            self.assertEqual(
                0,
                session.query(ExamProtocol).filter_by(exam_slot_id=self.slot_id).count(),
            )

    def test_parallel_start_creates_one_protocol_and_advances_one_revision(self) -> None:
        self._mark_quorum_present()
        barrier = Barrier(2)
        results: list[dict[str, object]] = []
        errors: list[BaseException] = []

        def start() -> None:
            try:
                barrier.wait(timeout=5)
                results.append(
                    self.service.start_slot(
                        self.day_id,
                        self.slot_id,
                        {"expected_day_revision": 1},
                        actor_member_id=1,
                    )
                )
            except BaseException as error:
                errors.append(error)

        threads = [Thread(target=start) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual([], errors)
        self.assertEqual(2, len(results))
        with session_scope(self.db_path) as session:
            self.assertEqual(
                1,
                session.query(ExamProtocol).filter_by(exam_slot_id=self.slot_id).count(),
            )
            self.assertEqual(2, session.get(ExamDay, self.day_id).revision)

    def test_attendance_advances_revision_once_and_is_idempotent(self) -> None:
        with session_scope(self.db_path) as session:
            assignment_id = session.scalar(
                select(ExamDayAssignment.id).where(
                    ExamDayAssignment.exam_day_id == self.day_id,
                    ExamDayAssignment.committee_member_id == 1,
                )
            )
        payload = {"status": "late", "arrived_at": "2026-11-16T08:59:00+01:00"}
        self.service.save_member_attendance(self.day_id, assignment_id, payload, actor_member_id=1)
        self.service.save_member_attendance(self.day_id, assignment_id, payload, actor_member_id=1)
        with session_scope(self.db_path) as session:
            self.assertEqual(2, session.get(ExamDay, self.day_id).revision)
            attendance = (
                session.query(MemberExamAttendance)
                .filter_by(exam_day_id=self.day_id, committee_member_id=1)
                .one()
            )
            self.assertEqual("late", attendance.status)
            self.assertEqual("2026-11-16T08:59:00+01:00", attendance.arrived_at)

    def test_day_mutation_operations_commit_only_with_the_enclosing_uow(self) -> None:
        request = {
            "day_id": self.day_id,
            "kind": "slot_status",
            "entity_id": self.slot_id,
            "expected_day_revision": 1,
            "actor_member_id": 1,
            "protocol_revision_id": None,
        }
        with self.execution_factory(write=True) as work:
            handle = work.guard_day_mutation(request)
            work.complete_day_mutation(handle, actor_member_id=1, reason="correction")

        with session_scope(self.db_path) as session:
            self.assertEqual(2, session.get(ExamDay, self.day_id).revision)

    def test_stale_day_mutation_is_rejected_by_the_execution_adapter(self) -> None:
        request = {
            "day_id": self.day_id,
            "kind": "slot_status",
            "entity_id": self.slot_id,
            "expected_day_revision": 0,
            "actor_member_id": 1,
            "protocol_revision_id": None,
        }
        with self.assertRaisesRegex(
            ExecutionDayMutationConflictError, "Prüfungstag wurde zwischenzeitlich geändert"
        ):
            with self.execution_factory(write=True) as work:
                work.guard_day_mutation(request)

        with session_scope(self.db_path) as session:
            self.assertEqual(1, session.get(ExamDay, self.day_id).revision)

    def test_day_mutation_operations_roll_back_with_the_enclosing_uow(self) -> None:
        request = {
            "day_id": self.day_id,
            "kind": "slot_status",
            "entity_id": self.slot_id,
            "expected_day_revision": 1,
            "actor_member_id": 1,
            "protocol_revision_id": None,
        }
        with self.assertRaisesRegex(RuntimeError, "abort outer operation"):
            with self.execution_factory(write=True) as work:
                handle = work.guard_day_mutation(request)
                work.complete_day_mutation(handle, actor_member_id=1, reason="correction")
                raise RuntimeError("abort outer operation")

        with session_scope(self.db_path) as session:
            self.assertEqual(1, session.get(ExamDay, self.day_id).revision)


if __name__ == "__main__":
    unittest.main()
