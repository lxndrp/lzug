from __future__ import annotations

import unittest

from backend.models import COMMITTEE, EXAM_DAY, EXAM_DAY_ASSIGNMENT, EXAM_ROUND, PERSON
from backend.repositories import ResourceRepository
from backend.tests.helpers import TempDatabase


class PersonMembershipTests(unittest.TestCase):
    def test_existing_person_can_join_another_committee(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            committee = repository.create(COMMITTEE, {"name": "PA 2", "occupation": "FI"})
            membership = repository.create_membership(
                {
                    "person_id": 1,
                    "committee_id": committee["id"],
                    "member_status": "deputy",
                    "committee_role": "member",
                    "representing_side": "school",
                    "is_active": 1,
                }
            )
        self.assertEqual(1, membership["person_id"])

    def test_person_email_is_canonical(self) -> None:
        with TempDatabase() as db_path:
            person = ResourceRepository(db_path).create(
                PERSON,
                {
                    "first_name": "Testperson",
                    "last_name": "Normalisierung",
                    "email": " Testperson.Normalisierung@Example.Invalid ",
                    "mobile": None,
                },
            )
        self.assertEqual("testperson.normalisierung@example.invalid", person["email"])

    def test_manual_assignment_rejects_person_in_other_committee(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            committee = repository.create(COMMITTEE, {"name": "PA 2", "occupation": "FI"})
            membership = repository.create_membership(
                {
                    "person_id": 1,
                    "committee_id": committee["id"],
                    "member_status": "ordinary",
                    "committee_role": "chair",
                    "representing_side": "employer",
                    "is_active": 1,
                }
            )
            other_round = repository.create(
                EXAM_ROUND,
                {
                    "exam_half_year_id": 1,
                    "committee_id": committee["id"],
                    "name": "Sommer",
                    "created_by_member_id": membership["id"],
                },
            )
            other_day = repository.create(
                EXAM_DAY,
                {
                    "exam_round_id": other_round["id"],
                    "location_id": 1,
                    "date": "2026-11-16",
                    "status": "proposed",
                    "lunch_break_enabled": 1,
                    "created_from_proposal": 1,
                },
            )
            repository.create(
                EXAM_DAY_ASSIGNMENT,
                {
                    "exam_day_id": other_day["id"],
                    "committee_member_id": membership["id"],
                    "assignment_role": "examiner",
                    "day_part": "morning",
                    "fallback_status": None,
                },
            )
            current_day = repository.create(
                EXAM_DAY,
                {
                    "exam_round_id": 1,
                    "location_id": 1,
                    "date": "2026-11-16",
                    "status": "proposed",
                    "lunch_break_enabled": 1,
                    "created_from_proposal": 1,
                },
            )
            with self.assertRaisesRegex(ValueError, "PA 2.*2026-11-16"):
                repository.create(
                    EXAM_DAY_ASSIGNMENT,
                    {
                        "exam_day_id": current_day["id"],
                        "committee_member_id": 1,
                        "assignment_role": "examiner",
                        "day_part": "morning",
                        "fallback_status": None,
                    },
                )


if __name__ == "__main__":
    unittest.main()
