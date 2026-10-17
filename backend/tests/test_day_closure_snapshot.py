from __future__ import annotations

import unittest

from backend.persistence.database import session_scope
from backend.persistence.day_closure_snapshot import SQLiteExamDayClosureReadSnapshotReader
from backend.persistence.models import ExamDayExport
from backend.tests.fixture_data import prepare_exam_protocol_scenario
from backend.tests.helpers import TempDatabase


class ExamDayClosureSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = TempDatabase()
        self.db_path = self.database.__enter__()
        prepare_exam_protocol_scenario(self.db_path)

    def tearDown(self) -> None:
        self.database.__exit__(None, None, None)

    def test_reader_materializes_ordered_day_history_and_tasks(self) -> None:
        with session_scope(self.db_path) as session:
            session.add_all(
                [
                    ExamDayExport(
                        exam_day_id=3,
                        closure_id=None,
                        export_kind="machine",
                        status="open",
                        generated_by_member_id=1,
                        generated_at="2026-10-18T10:00:00+00:00",
                    ),
                    ExamDayExport(
                        exam_day_id=3,
                        closure_id=None,
                        export_kind="human",
                        status="open",
                        generated_by_member_id=1,
                        generated_at="2026-10-18T10:01:00+00:00",
                    ),
                ]
            )
            session.flush()
            snapshot = SQLiteExamDayClosureReadSnapshotReader(
                session
            ).load_day_closure_read_snapshot(3)
            self.assertIsNotNone(snapshot)
            self.assertTrue(session.is_active)

        assert snapshot is not None
        self.assertEqual(3, snapshot.day["id"])
        self.assertEqual((1, 2), tuple(item["id"] for item in snapshot.history))
        self.assertEqual(
            ("machine", "human"), tuple(item["export_kind"] for item in snapshot.history)
        )
        self.assertEqual((), snapshot.tasks)
        self.assertTrue(all(not hasattr(value, "_sa_instance_state") for value in snapshot.history))
