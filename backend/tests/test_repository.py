from __future__ import annotations

import unittest

from backend.models import CANDIDATE, MEMBER_AVAILABILITY, PLANNING_SETTINGS, ROUND_CANDIDATE
from backend.repositories import ResourceRepository
from backend.tests.helpers import TempDatabase


class RepositoryTests(unittest.TestCase):
    def test_candidate_list_adds_human_readable_specialization_labels(self) -> None:
        with TempDatabase() as db_path:
            candidates = ResourceRepository(db_path).candidate_list()

        self.assertEqual(12, len(candidates))
        self.assertIn("specialization_label", candidates[0])
        self.assertIn(
            "Anwendungsentwicklung",
            {candidate["specialization_label"] for candidate in candidates},
        )

    def test_create_candidate_can_attach_candidate_to_exam_round(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            created = repository.create_candidate(
                {
                    "first_name": "Max",
                    "last_name": "Test",
                    "ihk_exam_number": "FI-2026-9001",
                    "specialization": "system_integration",
                    "training_company": "Testbetrieb GmbH",
                    "exam_round_id": 1,
                    "attempt_number": 3,
                    "requires_mep": 1,
                }
            )
            summary = repository.round_summary(1)

        self.assertEqual("Max", created["first_name"])
        self.assertIsNotNone(summary)
        self.assertEqual(13, summary["counts"]["candidates"])
        self.assertEqual(5, summary["counts"]["mep_count"])
        self.assertEqual(18, summary["counts"]["required_exam_slots"])

    def test_delete_candidate_removes_round_link_first(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            self.assertTrue(repository.delete_candidate(1))
            summary = repository.round_summary(1)
            candidate = repository.get(CANDIDATE, 1)

        self.assertIsNone(candidate)
        self.assertEqual(11, summary["counts"]["candidates"])

    def test_update_candidate_updates_round_data_atomically(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            updated = repository.update_candidate(
                1,
                {
                    "last_name": "Neu",
                    "exam_round_id": 1,
                    "attempt_number": 3,
                    "requires_mep": 1,
                },
            )
            round_candidate = repository.list_filtered(
                ROUND_CANDIDATE,
                {"candidate_id": 1, "exam_round_id": 1},
            )[0]

            with self.assertRaises(ValueError):
                repository.update_candidate(
                    1,
                    {
                        "last_name": "Nicht gespeichert",
                        "exam_round_id": 999,
                        "attempt_number": 2,
                    },
                )
            after_failed_update = repository.get(CANDIDATE, 1)

        self.assertIsNotNone(updated)
        self.assertEqual("Neu", updated["last_name"])
        self.assertEqual(3, round_candidate["attempt_number"])
        self.assertEqual(1, round_candidate["requires_mep"])
        self.assertEqual("Neu", after_failed_update["last_name"])

    def test_planning_settings_upsert_enforces_chair_for_week_limit(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            updated = repository.save_planning_settings(
                {
                    "exam_round_id": 1,
                    "calendar_week_from": "2026-W47",
                    "calendar_week_to": "2026-W50",
                    "exams_per_day": 5,
                    "max_exam_days_per_week": 4,
                    "lunch_break_enabled": 0,
                    "default_location_id": 2,
                    "updated_by_member_id": 1,
                }
            )

            with self.assertRaises(ValueError):
                repository.save_planning_settings(
                    {
                        "exam_round_id": 1,
                        "calendar_week_from": "2026-W47",
                        "calendar_week_to": "2026-W50",
                        "exams_per_day": 5,
                        "max_exam_days_per_week": 5,
                        "lunch_break_enabled": 0,
                        "default_location_id": 2,
                        "updated_by_member_id": 2,
                    }
                )

            settings = repository.list_filtered(PLANNING_SETTINGS, {"exam_round_id": 1})

        self.assertEqual(1, updated["id"])
        self.assertEqual(4, updated["max_exam_days_per_week"])
        self.assertEqual(1, len(settings))

    def test_availability_upsert_manages_response_timestamp(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            answered = repository.save_member_availability(
                {
                    "exam_round_id": 1,
                    "committee_member_id": 5,
                    "candidate_exam_day_id": 1,
                    "availability": "morning",
                }
            )
            pending = repository.update_member_availability(
                answered["id"],
                {"availability": "pending"},
            )
            rows = repository.list_filtered(
                MEMBER_AVAILABILITY,
                {
                    "exam_round_id": 1,
                    "committee_member_id": 5,
                    "candidate_exam_day_id": 1,
                },
            )

        self.assertIsNotNone(answered["responded_at"])
        self.assertIsNotNone(pending)
        self.assertIsNone(pending["responded_at"])
        self.assertEqual(1, len(rows))


if __name__ == "__main__":
    unittest.main()
