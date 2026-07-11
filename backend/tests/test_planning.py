from __future__ import annotations

import unittest

from backend.models import EXAM_DAY, EXAM_DAY_ASSIGNMENT, EXAM_ROUND, EXAM_SLOT
from backend.planning import PlanningService
from backend.repositories import ResourceRepository
from backend.tests.helpers import TempDatabase


class PlanningTests(unittest.TestCase):
    def test_generate_proposal_persists_days_slots_assignments(self) -> None:
        with TempDatabase() as db_path:
            proposal = PlanningService(db_path).generate_proposal(1)
            repository = ResourceRepository(db_path)
            exam_days = repository.list_filtered(EXAM_DAY, {"exam_round_id": 1})
            exam_slots = repository.list(EXAM_SLOT)
            assignments = repository.list(EXAM_DAY_ASSIGNMENT)
            exam_round = repository.get(EXAM_ROUND, 1)

        self.assertTrue(proposal["validation"]["passed"])
        self.assertEqual("plan_proposed", proposal["status"])
        self.assertEqual("plan_proposed", exam_round["status"])
        self.assertEqual(16, proposal["counts"]["planned_slots"])
        self.assertEqual(16, len(exam_slots))
        self.assertGreaterEqual(len(exam_days), 3)
        self.assertGreaterEqual(len(assignments), len(exam_days) * 4)

    def test_mep_slots_are_at_the_end_of_each_day(self) -> None:
        with TempDatabase() as db_path:
            PlanningService(db_path).generate_proposal(1)
            repository = ResourceRepository(db_path)
            exam_days = repository.list_filtered(EXAM_DAY, {"exam_round_id": 1})
            slots = repository.list(EXAM_SLOT)

        for exam_day in exam_days:
            day_slots = [slot for slot in slots if slot["exam_day_id"] == exam_day["id"]]
            slot_types = [slot["slot_type"] for slot in day_slots]
            if "mep" in slot_types:
                first_mep = slot_types.index("mep")
                self.assertTrue(all(slot_type == "mep" for slot_type in slot_types[first_mep:]))
                self.assertIn("regular", slot_types[:first_mep])

    def test_generate_proposal_replaces_existing_proposal(self) -> None:
        with TempDatabase() as db_path:
            service = PlanningService(db_path)
            first = service.generate_proposal(1)
            second = service.generate_proposal(1)
            repository = ResourceRepository(db_path)
            exam_slots = repository.list(EXAM_SLOT)

        self.assertEqual(16, first["counts"]["planned_slots"])
        self.assertEqual(16, second["counts"]["planned_slots"])
        self.assertEqual(16, len(exam_slots))

    def test_confirm_plan_updates_statuses_and_blocks_replacement(self) -> None:
        with TempDatabase() as db_path:
            service = PlanningService(db_path)
            service.generate_proposal(1)
            confirmed = service.confirm_plan(1)
            repository = ResourceRepository(db_path)
            exam_round = repository.get(EXAM_ROUND, 1)
            exam_days = repository.list_filtered(EXAM_DAY, {"exam_round_id": 1})
            exam_slots = repository.list(EXAM_SLOT)
            assignments = repository.list(EXAM_DAY_ASSIGNMENT)

            with self.assertRaises(ValueError):
                service.generate_proposal(1)

        self.assertEqual("plan_confirmed", confirmed["status"])
        self.assertEqual("plan_confirmed", exam_round["status"])
        self.assertTrue(all(day["status"] == "confirmed" for day in exam_days))
        self.assertTrue(all(slot["status"] == "confirmed" for slot in exam_slots))
        self.assertTrue(
            all(
                assignment["fallback_status"] == "confirmed"
                for assignment in assignments
                if assignment["assignment_role"] == "fallback"
            )
        )


if __name__ == "__main__":
    unittest.main()
