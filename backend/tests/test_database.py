from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

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
                    "exam_half_year",
                    "exam_round",
                    "round_candidate",
                    "candidate_committee_assignment",
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
                "exam_half_year": 1,
                "exam_round": 1,
                "round_candidate": 12,
                "candidate_committee_assignment": 12,
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
                        "first_name": "Prüfling",
                        "last_name": "Datenbank",
                        "ihk_exam_number": "TEST-2026-0001",
                        "specialization": "application_development",
                        "training_company": "Testbetrieb Datenbank",
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

    def test_initialize_migrates_existing_planning_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "legacy.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    "CREATE TABLE planning_settings "
                    "(id INTEGER PRIMARY KEY, calendar_week_from TEXT, calendar_week_to TEXT)"
                )

            initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(planning_settings)")
                }
                migrations = {
                    row[0] for row in connection.execute("SELECT name FROM schema_migration")
                }

        self.assertIn("exclude_public_holidays", columns)
        self.assertIn("holiday_subdivision_code", columns)
        self.assertIn("001_add_holiday_planning_settings.sql", migrations)

    def test_initialize_groups_legacy_rounds_under_a_migrated_half_year(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "legacy-round.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    "CREATE TABLE exam_round "
                    "(id INTEGER PRIMARY KEY, committee_id INTEGER NOT NULL, name TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE planning_settings "
                    "(id INTEGER PRIMARY KEY, calendar_week_from TEXT, calendar_week_to TEXT)"
                )
                connection.execute(
                    "INSERT INTO exam_round (id, committee_id, name) "
                    "VALUES (17, 4, 'Winter 2026/27')"
                )
                connection.commit()

            initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                half_year = connection.execute(
                    "SELECT season, year, status FROM exam_half_year"
                ).fetchone()
                migrated_round = connection.execute(
                    "SELECT exam_half_year_id FROM exam_round WHERE id = 17"
                ).fetchone()
                migrations = {
                    row[0] for row in connection.execute("SELECT name FROM schema_migration")
                }

        self.assertEqual(("winter", 2026, "active"), half_year)
        self.assertEqual(1, migrated_round[0])
        self.assertIn("003_add_exam_half_years.sql", migrations)

    def test_schema_marks_one_seeded_candidate_assignment_active_per_half_year(self) -> None:
        with TempDatabase() as db_path, connect(db_path) as connection:
            active_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM candidate_committee_assignment "
                    "WHERE candidate_id = 1 AND exam_half_year_id = 1 AND ended_at IS NULL"
                )
            ).fetchone()[0]
            migrations = {
                row[0] for row in connection.execute(text("SELECT name FROM schema_migration"))
            }

        self.assertEqual(1, active_count)
        self.assertIn("004_add_candidate_committee_assignments.sql", migrations)

    def test_initialize_migrates_legacy_candidate_assignments_without_losing_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "legacy-candidates.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.executescript("""
                    CREATE TABLE schema_migration (name TEXT PRIMARY KEY);
                    INSERT INTO schema_migration (name) VALUES
                      ('001_add_holiday_planning_settings.sql'),
                      ('002_add_person_memberships.sql'),
                      ('003_add_exam_half_years.sql');
                    CREATE TABLE candidate (id INTEGER PRIMARY KEY);
                    CREATE TABLE exam_half_year (id INTEGER PRIMARY KEY);
                    CREATE TABLE exam_round (
                      id INTEGER PRIMARY KEY,
                      exam_half_year_id INTEGER NOT NULL
                    );
                    CREATE TABLE round_candidate (
                      id INTEGER PRIMARY KEY,
                      exam_round_id INTEGER NOT NULL,
                      candidate_id INTEGER NOT NULL,
                      attempt_number INTEGER NOT NULL,
                      requires_mep INTEGER NOT NULL,
                      created_at TEXT NOT NULL,
                      updated_at TEXT NOT NULL
                    );
                    INSERT INTO candidate VALUES (1);
                    INSERT INTO exam_half_year VALUES (1);
                    INSERT INTO exam_round VALUES (1, 1), (2, 1);
                    INSERT INTO round_candidate VALUES
                      (1, 1, 1, 1, 0, '2026-01-01 08:00:00', '2026-02-01 08:00:00'),
                      (2, 2, 1, 1, 0, '2026-02-01 08:00:00', '2026-02-01 08:00:00');
                """)
                connection.commit()

            initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                history = connection.execute(
                    "SELECT exam_round_id, ended_at, change_reason "
                    "FROM candidate_committee_assignment ORDER BY exam_round_id"
                ).fetchall()
                active_flags = connection.execute(
                    "SELECT id, is_active FROM round_candidate ORDER BY id"
                ).fetchall()

        self.assertEqual(2, len(history))
        self.assertIsNotNone(history[0][1])
        self.assertIn("Migration", history[0][2])
        self.assertIsNone(history[1][1])
        self.assertEqual([(1, 0), (2, 1)], active_flags)


if __name__ == "__main__":
    unittest.main()
