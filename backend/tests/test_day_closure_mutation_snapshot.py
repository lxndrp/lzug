from __future__ import annotations

import unittest

from backend.application.exam_lifecycle import ExamLifecycleApplication
from backend.application.exam_lifecycle_commands import day_close_command, day_reopen_command
from backend.composition import (
    SQLiteAssessmentLifecycleAdapter,
    identity_lifecycle_work_factory,
    planning_lifecycle_work_factory,
)
from backend.execution.exam_day_closures import ExamDayClosureService
from backend.identity.authorization import AuthorizationScope
from backend.persistence.assessment import SQLiteAssessmentUnitOfWorkFactory
from backend.persistence.auth import SQLiteAuthenticationRepository
from backend.persistence.exam_lifecycle import SQLiteExamLifecycleUnitOfWorkFactory
from backend.persistence.execution import SQLiteExecutionUnitOfWorkFactory
from backend.persistence.identity import SQLiteIdentityExecutionSnapshotFactory
from backend.tests.fixture_data import prepare_exam_protocol_scenario
from backend.tests.helpers import TempDatabase, notification_service_for_test
from backend.tests.support.port_contracts import assert_materialized_port_value


class DayClosureMutationSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        prepare_exam_protocol_scenario(self.db_path)
        self.scope = AuthorizationScope(
            person_id=1,
            person_ids=frozenset({1}),
            committee_ids=frozenset({1}),
            member_ids=frozenset({1}),
            management_committee_ids=frozenset({1}),
            member_by_committee={1: 1},
        )
        authentication = SQLiteAuthenticationRepository(self.db_path)
        authentication.create_session(1)
        self.application = ExamLifecycleApplication(
            SQLiteExamLifecycleUnitOfWorkFactory(
                SQLiteExecutionUnitOfWorkFactory(
                    self.db_path,
                    identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
                ),
                SQLiteAssessmentUnitOfWorkFactory(self.db_path),
                self.db_path,
                SQLiteAssessmentLifecycleAdapter(SQLiteAssessmentUnitOfWorkFactory(self.db_path)),
            ),
            lambda: ExamDayClosureService(
                self.db_path,
                notification_service=notification_service_for_test(self.db_path),
                assessment_lifecycle_factory=SQLiteAssessmentLifecycleAdapter(),
                planning_lifecycle_work_factory=planning_lifecycle_work_factory(),
                identity_lifecycle_work_factory=identity_lifecycle_work_factory(),
            ),
        )

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def test_close_reopen_and_replay_responses_match_detached_read_projection(self) -> None:
        close_command = day_close_command(
            {
                "revision": 1,
                "closure_type": "exception",
                "confirmed": True,
                "reason": "Synthetischer Ausnahmegrund",
                "clarification_attempts": "Synthetischer Klärungsversuch",
            }
        )
        closed = self.application.close_exam_day(self.scope, 3, close_command)
        self.assertEqual(closed, self.application.get_exam_day_closure(self.scope, 3))
        self.assertEqual(closed, self.application.close_exam_day(self.scope, 3, close_command))
        assert_materialized_port_value(self, closed)

        reopen_command = day_reopen_command(
            {
                "revision": 2,
                "occasion": "Korrekturanlass",
                "source": "Prüfungsausschuss",
                "reason": "Korrektur erforderlich",
                "scope": [{"kind": "exam_result", "entity_id": 2}],
            }
        )
        reopened = self.application.reopen_exam_day(self.scope, 3, reopen_command)
        self.assertEqual(reopened, self.application.get_exam_day_closure(self.scope, 3))
        self.assertEqual(reopened, self.application.reopen_exam_day(self.scope, 3, reopen_command))
        assert_materialized_port_value(self, reopened)


if __name__ == "__main__":
    unittest.main()
