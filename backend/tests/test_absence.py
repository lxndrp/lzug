from __future__ import annotations

import unittest
from datetime import UTC, datetime
from http import HTTPStatus

from backend.absence import AbsenceService
from backend.authorization import AuthorizationScope
from backend.database import session_scope
from backend.models import (
    CalendarEvent,
    ExamDay,
    ExamDayAssignment,
    ExamRound,
    ExamSlot,
    MemberAvailability,
    ReplacementResponse,
)
from backend.tests.helpers import ApiServer, TempDatabase, assert_status


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

    def test_report_uses_exclusive_fallback_window_and_audit_history(self) -> None:
        result = AbsenceService(self.db_path).report(
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
        result = AbsenceService(self.db_path).report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=datetime(2026, 11, 15, tzinfo=UTC),
        )

        self.assertEqual("replacement_requested", result["status"])
        self.assertEqual({4, 7}, {item["committee_member_id"] for item in result["responses"]})
        self.assertTrue(all(item["urgent"] for item in result["responses"]))

    def test_expired_fallback_opens_further_search_and_audits_deadline(self) -> None:
        service = AbsenceService(self.db_path)
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

    def test_selection_is_single_versioned_transition_and_emits_calendar_work(self) -> None:
        service = AbsenceService(self.db_path)
        result = service.report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )
        response_id = result["responses"][0]["id"]
        service.respond(
            scope(7), response_id, {"response": "available"}, now=datetime(2026, 11, 1, tzinfo=UTC)
        )
        selected = service.select_replacement(
            scope(1, management=True),
            result["id"],
            {"committee_member_id": 7, "version": 1},
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
            self.assertEqual(2, len(events))
            self.assertEqual({"cancelled", "sent"}, {event.status for event in events})
            self.assertEqual({1, 7}, {event.recipient_member_id for event in events})
            self.assertEqual(1, session.query(ReplacementResponse).count())

    def test_cancellation_marks_only_the_affected_calendar_assignment(self) -> None:
        service = AbsenceService(self.db_path)
        result = service.report(
            scope(1),
            {"exam_day_id": self.day_id, "exam_day_assignment_id": self.assignment_id},
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )

        service.cancel(
            scope(1, management=True),
            result["id"],
            {"reason": "Kein Ersatz verfügbar"},
            now=datetime(2026, 11, 1, tzinfo=UTC),
        )

        with session_scope(self.db_path) as session:
            events = (
                session.query(CalendarEvent)
                .filter(CalendarEvent.source_key.like(f"assignment:{self.assignment_id}:%"))
                .all()
            )
            self.assertTrue(events)
            self.assertTrue(all(event.status == "cancelled" for event in events))

    def test_member_cannot_report_another_member_absence(self) -> None:
        with self.assertRaises(PermissionError):
            AbsenceService(self.db_path).report(
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
