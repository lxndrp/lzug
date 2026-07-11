from __future__ import annotations

import unittest

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.database import connect, initialize
from backend.tests.helpers import TempDatabase


class DatabaseTests(unittest.TestCase):
    def test_seed_contains_full_demo_round(self) -> None:
        with TempDatabase() as db_path, connect(db_path) as connection:
            counts = {
                table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()[0]
                for table in (
                    "committee",
                    "committee_member",
                    "location",
                    "candidate",
                    "exam_round",
                    "round_candidate",
                    "planning_settings",
                    "candidate_exam_day",
                    "member_availability",
                )
            }

        self.assertEqual(
            {
                "committee": 1,
                "committee_member": 8,
                "location": 2,
                "candidate": 12,
                "exam_round": 1,
                "round_candidate": 12,
                "planning_settings": 1,
                "candidate_exam_day": 5,
                "member_availability": 40,
            },
            counts,
        )

    def test_schema_enforces_core_constraints(self) -> None:
        with TempDatabase() as db_path, connect(db_path) as connection:
            with self.assertRaises(IntegrityError):
                connection.execute(
                    text("""
                    INSERT INTO candidate (
                      first_name,
                      last_name,
                      ihk_exam_number,
                      specialization,
                      training_company
                    )
                    VALUES (
                      :first_name,
                      :last_name,
                      :ihk_exam_number,
                      :specialization,
                      :training_company
                    )
                    """),
                    {
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                        "ihk_exam_number": "FI-2026-1042",
                        "specialization": "application_development",
                        "training_company": "Analytical Engines GmbH",
                    },
                )

            with self.assertRaises(IntegrityError):
                connection.execute(text("""
                    INSERT INTO member_availability (
                      exam_round_id,
                      committee_member_id,
                      candidate_exam_day_id,
                      availability,
                      responded_at
                    )
                    VALUES (1, 1, 1, 'full_day', NULL)
                    """))

    def test_initialize_can_reset_existing_database(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with connect(db_path) as connection, connection.begin():
                connection.execute(
                    text("INSERT INTO committee (id, name, occupation) " "VALUES (99, 'Alt', 'FI')")
                )

            initialize(db_path, with_seed=True, reset=True)

            with connect(db_path) as connection:
                ids = [
                    row[0]
                    for row in connection.execute(text("SELECT id FROM committee ORDER BY id"))
                ]

        self.assertEqual([1], ids)


if __name__ == "__main__":
    unittest.main()
