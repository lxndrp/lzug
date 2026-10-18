from __future__ import annotations

import unittest

from sqlalchemy import select

from backend.application.exam_lifecycle import ExamLifecycleApplication
from backend.composition import (
    SQLiteAssessmentLifecycleAdapter,
    authorization_service,
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
            notification_service=notification_service_for_test(self.db_path),
        )
        self.unit_of_work_factory = SQLiteExamLifecycleUnitOfWorkFactory(
            SQLiteExecutionUnitOfWorkFactory(
                self.db_path,
                identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
            ),
            assessment_factory,
            self.db_path,
            SQLiteAssessmentLifecycleAdapter(assessment_factory),
        )
        self.application = ExamLifecycleApplication(
            self.unit_of_work_factory,
            lambda: ExamDayClosureService(
                notification_service=notification_service_for_test(self.db_path),
            ),
            lambda: self.service,
        )
        self.scope = authorization_service(self.db_path).scope(self.chair)

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def test_round_service_has_no_session_opening_compatibility_entrypoints(self):
        for name in (
            "set_candidate_terminal_status",
            "delete_empty_draft",
            "machine_export",
            "human_export",
            "document_ihk_status",
            "document_ihk_status_command_in_session",
            "assert_mutable",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(self.service, name))
        self.assertFalse(hasattr(self.service, "db_path"))

    def test_round_lifecycle_read_uses_the_detached_snapshot_projection(self):
        application = ExamLifecycleApplication(
            self.unit_of_work_factory,
            lambda: self.fail("round lifecycle reads must not construct an Execution service"),
        )

        actual = application.get_exam_round_lifecycle(self.scope, 1)

        assert_materialized_port_value(self, actual)
        self.assertEqual(1, actual["round_id"])

    def test_machine_export_uses_the_application_snapshot_path(self):
        with session_scope(self.db_path) as session:
            initial_export_count = len(session.scalars(select(ExamRoundExport)).all())
        actual = self.application.export_exam_round(self.scope, 1, human=False)

        assert_materialized_port_value(self, actual)
        self.assertEqual(1, actual["export_version"])
        self.assertEqual("machine", actual["export"]["export_kind"])
        self.assertEqual("open", actual["export"]["lifecycle_status"])
        with session_scope(self.db_path) as session:
            self.assertEqual(
                initial_export_count + 1,
                len(session.scalars(select(ExamRoundExport)).all()),
            )

    def test_human_export_uses_the_application_snapshot_path(self):
        with session_scope(self.db_path) as session:
            initial_export_count = len(session.scalars(select(ExamRoundExport)).all())
        actual = self.application.export_exam_round(self.scope, 1, human=True)
        assert_materialized_port_value(self, actual)
        self.assertEqual(1, actual["export_version"])
        self.assertIn("status", actual["lifecycle"])
        self.assertIn("round", actual["snapshot"])
        with session_scope(self.db_path) as session:
            self.assertEqual(
                initial_export_count + 1,
                len(session.scalars(select(ExamRoundExport)).all()),
            )


if __name__ == "__main__":
    unittest.main()
