from __future__ import annotations

import unittest

from sqlalchemy import text

from backend.database import connect
from backend.models import (
    CANDIDATE,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_ROUND,
    EXAM_SLOT,
    LOCATION,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
)
from backend.planning import PlanningService
from backend.repositories import ResourceRepository
from backend.tests.helpers import TempDatabase


class PlanningTests(unittest.TestCase):
    def test_request_availabilities_moves_prepared_draft_into_coordination(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            repository.update(EXAM_ROUND, 1, {"status": "draft"})

            requested = PlanningService(db_path).request_availabilities(1)
            persisted = repository.get(EXAM_ROUND, 1)

        self.assertEqual("availability_requested", requested["status"])
        self.assertEqual("availability_requested", persisted["status"])

    def test_missing_round_is_rejected(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with self.assertRaisesRegex(ValueError, "Exam round not found"):
                PlanningService(db_path).generate_proposal(1)

    def test_missing_planning_settings_are_rejected(self) -> None:
        with TempDatabase() as db_path:
            with connect(db_path) as connection:
                connection.execute(text("DELETE FROM planning_settings"))
                connection.commit()

            with self.assertRaisesRegex(ValueError, "Planning settings not found"):
                PlanningService(db_path).generate_proposal(1)

    def test_no_active_candidate_days_are_rejected(self) -> None:
        with TempDatabase() as db_path:
            with connect(db_path) as connection:
                connection.execute(text("DELETE FROM candidate_exam_day"))
                connection.commit()

            with self.assertRaisesRegex(ValueError, "No active candidate exam days found"):
                PlanningService(db_path).generate_proposal(1)

    def test_confirmation_without_proposal_is_rejected(self) -> None:
        with TempDatabase() as db_path:
            with self.assertRaisesRegex(ValueError, "No planning proposal found"):
                PlanningService(db_path).confirm_plan(1)

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

    def test_confirmed_other_committee_reservation_blocks_proposal(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            other_round = self._create_overlapping_round(repository)
            for member_id in range(5, 9):
                repository.update(COMMITTEE_MEMBER, member_id, {"is_active": 0})

            PlanningService(db_path).generate_proposal(other_round["id"])
            PlanningService(db_path).confirm_plan(other_round["id"])
            proposal = PlanningService(db_path).generate_proposal(1)

        self.assertFalse(proposal["validation"]["passed"])
        self.assertTrue(
            any("bestätigte Termine" in message for message in proposal["validation"]["messages"])
        )

    def test_other_proposal_and_fallback_reserve_person_before_confirmation(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            other_round = self._create_overlapping_round(repository)
            for member_id in range(5, 9):
                repository.update(COMMITTEE_MEMBER, member_id, {"is_active": 0})

            PlanningService(db_path).generate_proposal(other_round["id"])
            other_assignments = repository.list(EXAM_DAY_ASSIGNMENT)
            proposal = PlanningService(db_path).generate_proposal(1)

        self.assertTrue(any(item["assignment_role"] == "fallback" for item in other_assignments))
        self.assertFalse(proposal["validation"]["passed"])
        self.assertTrue(
            any("Planungsvorschläge" in message for message in proposal["validation"]["messages"])
        )

    def _create_overlapping_round(self, repository: ResourceRepository) -> dict[str, object]:
        committee = repository.create(COMMITTEE, {"name": "PA 2", "occupation": "FI"})
        members = []
        for person_id, side in enumerate(("employer", "employee", "school", "employer"), start=1):
            members.append(
                repository.create_membership(
                    {
                        "person_id": person_id,
                        "committee_id": committee["id"],
                        "member_status": "ordinary",
                        "committee_role": "member",
                        "representing_side": side,
                        "is_active": 1,
                    }
                )
            )
        location = repository.create(
            LOCATION,
            {
                "committee_id": committee["id"],
                "name": "Raum 2",
                "street": "Testweg 1",
                "postal_code": "00000",
                "city": "Teststadt",
                "room": "2.01",
                "is_active": 1,
            },
        )
        exam_round = repository.create(
            EXAM_ROUND,
            {
                "exam_half_year_id": 1,
                "committee_id": committee["id"],
                "name": "Winter 2026/27 PA 2",
                "availability_deadline": "2026-10-15 18:00:00",
                "created_by_member_id": members[0]["id"],
            },
        )
        for index in range(5):
            candidate = repository.create(
                CANDIDATE,
                {
                    "first_name": "Prüfling",
                    "last_name": f"Konflikt-{index}",
                    "ihk_exam_number": f"TEST-88-{index}",
                    "specialization": "system_integration",
                    "training_company": "Testbetrieb Konflikt",
                },
            )
            repository.create(
                ROUND_CANDIDATE,
                {
                    "exam_round_id": exam_round["id"],
                    "candidate_id": candidate["id"],
                    "attempt_number": 1,
                    "requires_mep": 0,
                    "is_active": 1,
                },
            )
        repository.create(
            PLANNING_SETTINGS,
            {
                "exam_round_id": exam_round["id"],
                "calendar_week_from": "2026-W47",
                "calendar_week_to": "2026-W47",
                "exams_per_day": 1,
                "max_exam_days_per_week": 5,
                "lunch_break_enabled": 1,
                "exclude_public_holidays": 0,
                "holiday_subdivision_code": None,
                "default_location_id": location["id"],
                "updated_by_member_id": members[0]["id"],
            },
        )
        for date in ("2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"):
            candidate_day = repository.create(
                CANDIDATE_EXAM_DAY,
                {"exam_round_id": exam_round["id"], "date": date, "is_active": 1},
            )
            for member in members:
                repository.create(
                    MEMBER_AVAILABILITY,
                    {
                        "exam_round_id": exam_round["id"],
                        "committee_member_id": member["id"],
                        "candidate_exam_day_id": candidate_day["id"],
                        "availability": "full_day",
                        "responded_at": "2026-01-01T00:00:00+00:00",
                    },
                )
        PlanningService(repository.db_path).request_availabilities(exam_round["id"])
        return exam_round


if __name__ == "__main__":
    unittest.main()
