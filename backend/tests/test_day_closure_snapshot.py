from __future__ import annotations

import unittest

from backend.persistence.database import session_scope
from backend.persistence.day_closure_snapshot import SQLiteExamDayClosureReadSnapshotReader
from backend.persistence.day_lifecycle_snapshot import SQLiteExamDayLifecycleSnapshotReader
from backend.persistence.models import ExamDayClosure, ExamDayExport, ExamDayReopening
from backend.tests.fixture_data import prepare_exam_protocol_scenario
from backend.tests.helpers import TempDatabase
from backend.tests.support.port_contracts import assert_materialized_port_value


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
        assert_materialized_port_value(self, snapshot)

    def test_lifecycle_reader_materializes_replay_and_reopening_state(self) -> None:
        with session_scope(self.db_path) as session:
            session.add(
                ExamDayClosure(
                    exam_day_id=3,
                    requested_revision=1,
                    resulting_revision=2,
                    closure_type="regular",
                    actor_member_id=1,
                    reason=None,
                    clarification_attempts=None,
                    checklist_json="[]",
                    warnings_json="[]",
                    protocol_references_json="[]",
                    result_references_json="[]",
                    previous_closure_id=None,
                    status="superseded",
                    command_fingerprint="c" * 64,
                    closed_at="2026-10-18T10:00:00+00:00",
                )
            )
            session.flush()
            session.add(
                ExamDayReopening(
                    exam_day_id=3,
                    previous_closure_id=None,
                    requested_revision=2,
                    resulting_revision=3,
                    occasion="Korrektur",
                    source="Prüfungsprotokoll",
                    reason="Berichtigung",
                    requested_scope_json='["exam_protocol:1"]',
                    scope_json='["exam_protocol:1"]',
                    completed_scope_json="[]",
                    impacts_json="{}",
                    actor_member_id=1,
                    status="open",
                    command_fingerprint="r" * 64,
                    opened_at="2026-10-18T10:01:00+00:00",
                )
            )
            session.flush()
            snapshot = SQLiteExamDayLifecycleSnapshotReader(
                session
            ).load_exam_day_lifecycle_snapshot(3)
            self.assertTrue(session.is_active)

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(3, snapshot.day["id"])
        self.assertEqual(("c" * 64,), snapshot.closure_fingerprints)
        self.assertEqual(
            {
                "id": 1,
                "status": "open",
                "command_fingerprint": "r" * 64,
                "requested_scope": ["exam_protocol:1"],
                "completed_scope": [],
            },
            snapshot.reopenings[0],
        )
        assert_materialized_port_value(self, snapshot)
