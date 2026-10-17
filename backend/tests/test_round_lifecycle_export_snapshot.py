from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy import select

from backend.application.exam_lifecycle import ExamLifecycleApplication
from backend.composition import (
    SQLiteAssessmentLifecycleAdapter,
    authorization_service,
    calendar_lifecycle_work_factory,
    identity_lifecycle_work_factory,
    planning_lifecycle_work_factory,
)
from backend.execution.exam_day_closures import ExamDayClosureService
from backend.execution.exam_round_lifecycle import ExamRoundLifecycleService
from backend.persistence.assessment import SQLiteAssessmentUnitOfWorkFactory
from backend.persistence.auth import SQLiteAuthenticationRepository
from backend.persistence.database import session_scope
from backend.persistence.exam_lifecycle import SQLiteExamLifecycleUnitOfWorkFactory
from backend.persistence.execution import SQLiteExecutionUnitOfWorkFactory
from backend.persistence.identity import SQLiteIdentityExecutionSnapshotFactory
from backend.persistence.models import ExamRoundExport
from backend.tests.fixture_data import prepare_exam_protocol_scenario
from backend.tests.helpers import TempDatabase, notification_service_for_test
from backend.tests.support.port_contracts import assert_materialized_port_value


class RoundLifecycleExportSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        prepare_exam_protocol_scenario(self.db_path)
        authentication = SQLiteAuthenticationRepository(self.db_path)
        self.chair = authentication.authenticate(authentication.create_session(1).token)
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
        self.scope = authorization_service(self.db_path).scope(self.chair)

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def test_machine_export_matches_legacy_projection_and_avoids_orm_execution_path(self):
        with session_scope(self.db_path) as session:
            initial_export_count = len(session.scalars(select(ExamRoundExport)).all())
        expected = self.service.machine_export(self.scope, 1)
        with (
            patch.object(self.service, "_export_in_session", side_effect=AssertionError),
            patch.object(self.service, "_snapshot", side_effect=AssertionError),
            patch.object(self.service, "_view", side_effect=AssertionError),
        ):
            actual = self.application.export_exam_round(self.scope, 1, human=False)

        assert_materialized_port_value(self, actual)
        self.assertEqual(expected["snapshot"], actual["snapshot"])
        self.assertEqual(
            expected["lifecycle"],
            {**actual["lifecycle"], "exports": actual["lifecycle"]["exports"][:-1]},
        )
        self.assertEqual(expected["export"]["export_kind"], actual["export"]["export_kind"])
        self.assertEqual(
            expected["export"]["lifecycle_status"], actual["export"]["lifecycle_status"]
        )
        self.assertEqual(
            expected["export"]["generated_by_member_id"], actual["export"]["generated_by_member_id"]
        )
        with session_scope(self.db_path) as session:
            self.assertEqual(
                initial_export_count + 2,
                len(session.scalars(select(ExamRoundExport)).all()),
            )
        generated_at = datetime.fromisoformat(actual["export"]["generated_at"])
        self.assertEqual(UTC, generated_at.tzinfo)
        self.assertEqual(0, generated_at.microsecond)

    def test_human_export_matches_legacy_rendering_without_orm_execution_path(self):
        expected = self.service.human_export(self.scope, 1)
        with (
            patch.object(self.service, "_export_in_session", side_effect=AssertionError),
            patch.object(self.service, "_snapshot", side_effect=AssertionError),
            patch.object(self.service, "_view", side_effect=AssertionError),
        ):
            actual = self.application.export_exam_round(self.scope, 1, human=True)
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
