from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import text

from backend.application.exam_lifecycle import ExamLifecycleApplication
from backend.application.exam_lifecycle_commands import round_decision_command, round_reopen_command
from backend.composition import (
    SQLiteAssessmentLifecycleAdapter,
    authorization_service,
    calendar_lifecycle_work_factory,
    identity_lifecycle_work_factory,
    planning_lifecycle_work_factory,
)
from backend.execution.exam_day_closures import ExamDayClosureService
from backend.execution.exam_round_lifecycle import (
    ExamRoundConflictError,
    ExamRoundLifecycleService,
)
from backend.persistence.assessment import SQLiteAssessmentUnitOfWorkFactory
from backend.persistence.auth import SQLiteAuthenticationRepository
from backend.persistence.database import session_scope
from backend.persistence.exam_lifecycle import SQLiteExamLifecycleUnitOfWorkFactory
from backend.persistence.execution import SQLiteExecutionUnitOfWorkFactory
from backend.persistence.identity import SQLiteIdentityExecutionSnapshotFactory
from backend.tests.fixture_data import prepare_exam_protocol_scenario
from backend.tests.helpers import TempDatabase, notification_service_for_test
from backend.tests.support.port_contracts import assert_materialized_port_value


class RoundLifecycleMutationSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        prepare_exam_protocol_scenario(self.db_path)
        authentication = SQLiteAuthenticationRepository(self.db_path)
        self.chair = authentication.authenticate(authentication.create_session(1).token)
        self.deputy = authentication.authenticate(authentication.create_session(3).token)
        assessment_factory = SQLiteAssessmentUnitOfWorkFactory(self.db_path)
        self.service = ExamRoundLifecycleService(
            self.db_path,
            notification_service=notification_service_for_test(self.db_path),
            assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
            planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
            identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
            calendar_lifecycle_work_factory=calendar_lifecycle_work_factory(),
        )
        self.application = ExamLifecycleApplication(
            SQLiteExamLifecycleUnitOfWorkFactory(
                SQLiteExecutionUnitOfWorkFactory(
                    self.db_path,
                    identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
                ),
                assessment_factory,
                self.db_path,
                SQLiteAssessmentLifecycleAdapter(assessment_factory),
            ),
            lambda: ExamDayClosureService(
                self.db_path,
                notification_service=notification_service_for_test(self.db_path),
                assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
                planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
                identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
            ),
            lambda: self.service,
        )
        self.chair_scope = authorization_service(self.db_path).scope(self.chair)
        self.deputy_scope = authorization_service(self.db_path).scope(self.deputy)

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def test_candidate_and_ihk_responses_use_detached_round_snapshot(self) -> None:
        with patch.object(self.service, "_view", side_effect=AssertionError("ORM response path")):
            candidate = self.application.set_exam_round_candidate_terminal_status(
                self.chair_scope,
                1,
                1,
                {
                    "revision": 1,
                    "terminal_status": "postponed",
                    "reason": "Verbindliche Nachplanung",
                    "postponed_until": "2027-12-01",
                },
            )
            ihk = self.application.document_exam_round_ihk_status(
                self.deputy_scope,
                2,
                1,
                {
                    "document_status": "Zeugnis extern zugestellt",
                    "document_reference": "IHK-TEST-89-1",
                },
            )
        assert_materialized_port_value(self, candidate)
        assert_materialized_port_value(self, ihk)
        self.assertEqual(self._legacy_view(1, self.chair_scope), candidate)
        self.assertEqual(self._legacy_view(2, self.deputy_scope), ihk)
        self.assertEqual(
            ("postponed", 2), (candidate["candidates"][0]["terminal_status"], candidate["revision"])
        )
        self.assertEqual(1, len(ihk["ihk_statuses"]))

    def test_close_and_reopen_apply_and_replay_use_detached_snapshot(self) -> None:
        self._make_round_closable()
        close = round_decision_command({"revision": 1, "confirmed": True})
        reopen = round_reopen_command(
            {
                "revision": 2,
                "occasion": "Berichtigung",
                "source": "IHK-Vorgang",
                "reason": "Rundenbezeichnung korrigieren",
                "scope": [{"kind": "planning", "entity_id": 1}],
            }
        )
        with patch.object(self.service, "_view", side_effect=AssertionError("ORM response path")):
            closed = self.application.close_exam_round(self.chair_scope, 1, close)
        self.assertEqual(self._legacy_view(1, self.chair_scope), closed)
        with patch.object(self.service, "_view", side_effect=AssertionError("ORM response path")):
            closed_replay = self.application.close_exam_round(self.chair_scope, 1, close)
        self.assertEqual(self._legacy_view(1, self.chair_scope), closed_replay)
        with patch.object(self.service, "_view", side_effect=AssertionError("ORM response path")):
            reopened = self.application.reopen_exam_round(self.chair_scope, 1, reopen)
        self.assertEqual(self._legacy_view(1, self.chair_scope), reopened)
        with patch.object(self.service, "_view", side_effect=AssertionError("ORM response path")):
            reopened_replay = self.application.reopen_exam_round(self.chair_scope, 1, reopen)
        for response in (closed, closed_replay, reopened, reopened_replay):
            assert_materialized_port_value(self, response)
        self.assertEqual(("closed", 2), (closed["status"], closed["revision"]))
        self.assertEqual(closed, closed_replay)
        self.assertEqual(("reopening", 3), (reopened["status"], reopened["revision"]))
        self.assertEqual(reopened, reopened_replay)

    def test_cancel_apply_and_replay_use_detached_snapshot(self) -> None:
        self._make_round_closable()
        cancel = round_decision_command(
            {"revision": 1, "confirmed": True, "reason": "Prüfung abgesagt"}
        )
        with patch.object(self.service, "_view", side_effect=AssertionError("ORM response path")):
            cancelled = self.application.cancel_exam_round(self.chair_scope, 1, cancel)
            replayed = self.application.cancel_exam_round(self.chair_scope, 1, cancel)
        assert_materialized_port_value(self, cancelled)
        self.assertEqual(("cancelled", 2), (cancelled["status"], cancelled["revision"]))
        self.assertEqual(cancelled, replayed)
        self.assertEqual(self._legacy_view(1, self.chair_scope), cancelled)

    def test_candidate_mutation_checks_round_lock_inside_writer_uow(self) -> None:
        with session_scope(self.db_path) as session:
            session.execute(
                text(
                    "UPDATE exam_round SET status = 'completed', lifecycle_status = 'closed' "
                    "WHERE id = 1"
                )
            )
        with self.assertRaisesRegex(ExamRoundConflictError, "fachlich beendet"):
            self.application.set_exam_round_candidate_terminal_status(
                self.chair_scope,
                1,
                1,
                {
                    "revision": 1,
                    "terminal_status": "postponed",
                    "reason": "Verbindliche Nachplanung",
                    "postponed_until": "2027-12-01",
                },
            )

    def _legacy_view(self, round_id: int, scope):
        with session_scope(self.db_path) as session:
            planning = self.service.planning_lifecycle_work_factory(session)
            exam_round = planning.round_lifecycle_snapshot(round_id)
            return self.service._view(session, exam_round, scope, planning_work=planning)

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
