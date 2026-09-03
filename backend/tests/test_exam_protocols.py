from __future__ import annotations

import sqlite3
import unittest
from http import HTTPStatus

from sqlalchemy import select

from backend.auth import AuthenticationRepository
from backend.database import initialize, session_scope
from backend.exam_protocols import ENTRY_CATEGORIES, create_protocol_for_started_slot
from backend.models import (
    CandidateExamAttendance,
    ExamDay,
    ExamDayAssignment,
    ExamProtocol,
    ExamProtocolParticipant,
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
        self.authentication = AuthenticationRepository(self.db_path)
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
            protocol = create_protocol_for_started_slot(
                session,
                slot_id=slot.id,
                participant_member_ids={1, 3},
                created_by_member_id=1,
                created_at="2026-11-16T09:03:00+01:00",
            )
            self.day_id = day.id
            self.slot_id = slot.id
            self.protocol_id = protocol.id

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

        with sqlite3.connect(self.db_path) as connection:
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


if __name__ == "__main__":
    unittest.main()
