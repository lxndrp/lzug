from __future__ import annotations

import unittest

from backend.models import COMMITTEE, EXAM_DAY_ASSIGNMENT, PERSON
from backend.planning import PlanningService
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

    def test_manual_assignment_cannot_bypass_plan_aggregate(self) -> None:
        with TempDatabase() as db_path:
            repository = ResourceRepository(db_path)
            PlanningService(db_path).generate_proposal(1)
            proposal = PlanningService(db_path).get_proposal(1)
            with self.assertRaisesRegex(ValueError, "planning aggregate"):
                repository.create(
                    EXAM_DAY_ASSIGNMENT,
                    {
                        "exam_day_id": proposal.days[0].id,
                        "committee_member_id": 1,
                        "assignment_role": "examiner",
                        "day_part": "morning",
                        "fallback_status": None,
                    },
                )


if __name__ == "__main__":
    unittest.main()
