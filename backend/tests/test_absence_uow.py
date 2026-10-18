from __future__ import annotations

import unittest

from backend.mutation_locks import MutationLockCommand, MutationLockKind
from backend.persistence.absence_uow import SQLiteAbsenceUnitOfWorkFactory
from backend.persistence.database import session_scope
from backend.persistence.models import ExamDay, ExamDayAssignment, ExamRound
from backend.tests.helpers import TempDatabase


class SQLiteAbsenceUnitOfWorkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        with session_scope(self.db_path) as session:
            session.get(ExamRound, 1).status = "plan_confirmed"
            day = ExamDay(
                exam_round_id=1,
                room_id=1,
                date="2026-11-16",
                status="confirmed",
            )
            session.add(day)
            session.flush()
            assignment = ExamDayAssignment(
                exam_day_id=day.id,
                committee_member_id=1,
                assignment_role="examiner",
                day_part="morning",
            )
            session.add(assignment)
            session.flush()
            self.day_id = day.id
            self.assignment_id = assignment.id

        self.factory = SQLiteAbsenceUnitOfWorkFactory(self.db_path)

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def test_write_operations_materialize_snapshots_and_share_day_guard_session(self) -> None:
        with self.factory() as unit_of_work:
            unit_of_work.assert_mutation_allowed(
                MutationLockCommand(
                    MutationLockKind.ABSENCE_REPORT, None, {"exam_day_id": self.day_id}
                )
            )
            target = unit_of_work.target(self.day_id, self.assignment_id, None)
            self.assertIsNotNone(target)
            handle = unit_of_work.guard_day_mutation(
                day_id=self.day_id,
                kind="staffing",
                entity_id=self.assignment_id,
                payload={},
                actor_member_id=1,
            )
            report = unit_of_work.insert_report(
                target=target,
                reported_by_member_id=1,
                reported_at="2026-11-01T00:00:00+00:00",
                reason="Ausfall",
                status="reported",
            )
            unit_of_work.insert_response(
                report_id=report.id,
                member_id=2,
                requested_at="2026-11-01T00:00:00+00:00",
                expires_at=None,
                urgent=False,
            )
            unit_of_work.insert_audit(
                report_id=report.id,
                actor_member_id=1,
                event_type="reported",
                from_status=None,
                to_status="reported",
                created_at="2026-11-01T00:00:00+00:00",
                details={"reason": "Prüfung"},
            )
            unit_of_work.complete_day_mutation(handle, actor_member_id=1)
            view = unit_of_work.report_view(report.id)

        self.assertIsNotNone(view)
        if view is None:
            self.fail("Expected a detached absence view")
        self.assertEqual(0, view.report.version)
        self.assertEqual((2,), tuple(row.committee_member_id for row in view.responses))
        self.assertEqual('{"reason": "Prüfung"}', view.audit[0].details)
        with self.factory.read_scope() as unit_of_work:
            self.assertEqual(frozenset({2}), unit_of_work.response_member_ids(report.id))

    def test_day_guard_handle_cannot_cross_uow_boundary(self) -> None:
        with self.factory() as unit_of_work:
            handle = unit_of_work.guard_day_mutation(
                day_id=self.day_id,
                kind="absence",
                entity_id=1,
                payload={},
                actor_member_id=1,
            )
        with self.factory() as other_unit_of_work:
            with self.assertRaisesRegex(ValueError, "derselben Transaktion"):
                other_unit_of_work.complete_day_mutation(handle, actor_member_id=1)


if __name__ == "__main__":
    unittest.main()
