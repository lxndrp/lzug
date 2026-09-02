from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend.database import MigrationError, apply_migrations, initialize, migration_status
from backend.exam_venue_migration import HUMAN_REPORT_NAME, MACHINE_REPORT_NAME


class ExamVenueMigrationTests(unittest.TestCase):
    def _legacy_database(self, directory: Path) -> tuple[Path, Path]:
        db_path = directory / "legacy.sqlite3"
        migration_directory = directory / "migrations"
        migration_directory.mkdir()
        for migration in Path("db/migrations").glob("*.sql"):
            if migration.name < "025_model_exam_venues.sql":
                shutil.copy(migration, migration_directory / migration.name)

        with patch("backend.database.MIGRATIONS_PATH", migration_directory):
            initialize(db_path, with_seed=False, reset=True)

        with closing(sqlite3.connect(db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript("""
                INSERT INTO committee (id, name, occupation, ihk, is_active, bootstrap_state)
                VALUES (1, 'PA Nord', 'Fachinformatiker/in', 'IHK Nord', 1, 'ready');
                INSERT INTO person (id, first_name, last_name, email)
                VALUES (1, 'Ada', 'Lovelace', 'ada@example.invalid');
                INSERT INTO committee_member (
                  id, person_id, committee_id, member_status, committee_role, representing_side
                ) VALUES (1, 1, 1, 'ordinary', 'chair', 'employer');
                INSERT INTO exam_half_year (id, season, year)
                VALUES (1, 'summer', 2026);
                INSERT INTO exam_round (
                  id, exam_half_year_id, committee_id, name, created_by_member_id
                ) VALUES (1, 1, 1, 'Sommer 2026 PA Nord', 1);
                INSERT INTO location (
                  id, committee_id, name, street, postal_code, city, room, is_active
                ) VALUES
                  (10, 1, 'Campus Nord', 'Musterstraße 1', '20095', 'Hamburg', 'A-101', 1),
                  (11, 1, '  campus   nord ', 'Musterstraße 1', '20095', 'Hamburg', '', 0),
                  (12, 1, 'Campus Süd', 'Musterstraße 2', '20095', 'Hamburg', 'B-201', 1),
                  (13, 1, '', '', '', '', 'Provisorium', 1);
                INSERT INTO planning_settings (
                  id, exam_round_id, calendar_week_from, calendar_week_to, exams_per_day,
                  default_location_id, updated_by_member_id
                ) VALUES (1, 1, '2026-W20', '2026-W21', 4, 11, 1);
                INSERT INTO exam_day (id, exam_round_id, location_id, date, status)
                VALUES (1, 1, 10, '2026-05-12', 'confirmed');
                INSERT INTO confirmed_plan_revision (
                  id, exam_round_id, previous_revision, resulting_revision, reason,
                  actor_member_id, before_state_json, after_state_json
                ) VALUES (
                  1, 1, 0, 1, 'Bestehende Planung migrieren', 1,
                  '{"days":[{"location_id":10}],"default_location_id":11}',
                  '{"days":[{"location_id":11}],"default_location_id":10}'
                );
            """)
            connection.commit()
        return db_path, directory / "reports"

    def test_migrates_exact_groups_references_and_migration_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            db_path, report_directory = self._legacy_database(directory)

            apply_migrations(db_path, backup_dir=report_directory)

            with closing(sqlite3.connect(db_path)) as connection:
                venues = connection.execute(
                    "SELECT id, name, is_active, accessibility_status FROM exam_venue ORDER BY id"
                ).fetchall()
                rooms = connection.execute(
                    "SELECT id, venue_id, name FROM exam_room ORDER BY id"
                ).fetchall()
                mappings = connection.execute(
                    "SELECT legacy_location_id, venue_id, room_id "
                    "FROM legacy_location_room_mapping ORDER BY legacy_location_id"
                ).fetchall()
                default_room = connection.execute(
                    "SELECT default_room_id FROM planning_settings WHERE id = 1"
                ).fetchone()[0]
                day_room = connection.execute(
                    "SELECT room_id FROM exam_day WHERE id = 1"
                ).fetchone()[0]
                revision = connection.execute(
                    "SELECT before_state_json, after_state_json "
                    "FROM confirmed_plan_revision WHERE id = 1"
                ).fetchone()
                report = connection.execute(
                    "SELECT backup_reference, source_location_count, venue_count, room_count, "
                    "clarification_count FROM exam_venue_migration_report"
                ).fetchone()
                audit_count = connection.execute(
                    "SELECT count(*) FROM exam_venue_audit_event WHERE change_type = 'migrated'"
                ).fetchone()[0]
                legacy_table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'location'"
                ).fetchone()

            machine_report = json.loads((report_directory / MACHINE_REPORT_NAME).read_text())
            human_report = (report_directory / HUMAN_REPORT_NAME).read_text()
            backup_exists = (report_directory / report[0]).is_file()
            first_audit_count = audit_count
            apply_migrations(db_path, backup_dir=report_directory)
            with closing(sqlite3.connect(db_path)) as connection:
                audit_count = connection.execute(
                    "SELECT count(*) FROM exam_venue_audit_event WHERE change_type = 'migrated'"
                ).fetchone()[0]
            current_migration = migration_status(db_path)["current"]

        self.assertEqual(
            [
                (10, "Campus Nord", 0, "needs_clarification"),
                (12, "Campus Süd", 0, "needs_clarification"),
                (13, "", 0, "needs_clarification"),
            ],
            venues,
        )
        self.assertEqual(
            [
                (10, 10, "A-101"),
                (11, 10, "Gesamter Standort"),
                (12, 12, "B-201"),
                (13, 13, "Provisorium"),
            ],
            rooms,
        )
        self.assertEqual([(10, 10, 10), (11, 10, 11), (12, 12, 12), (13, 13, 13)], mappings)
        self.assertEqual(11, default_room)
        self.assertEqual(10, day_room)
        self.assertEqual(
            {"days": [{"room_id": 10}], "default_room_id": 11}, json.loads(revision[0])
        )
        self.assertEqual(
            {"days": [{"room_id": 11}], "default_room_id": 10}, json.loads(revision[1])
        )
        self.assertTrue(report[0].startswith("legacy.migration-"))
        self.assertEqual((4, 3, 4, 3), report[1:])
        self.assertTrue(backup_exists)
        self.assertEqual(4, machine_report["source"]["locations"])
        self.assertEqual(3, machine_report["target"]["venues"])
        self.assertIn("Klärungsfälle Barrierefreiheit: 3", human_report)
        self.assertFalse(legacy_table)
        self.assertEqual(7, first_audit_count)
        self.assertEqual(first_audit_count, audit_count)
        self.assertEqual("028_add_exam_venue_change_notifications.sql", current_migration)

    def test_duplicate_normalized_rooms_stop_before_schema_changes_and_leave_reports(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            db_path, report_directory = self._legacy_database(directory)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    "INSERT INTO location "
                    "(id, committee_id, name, street, postal_code, city, room) "
                    "VALUES (14, 1, 'Campus Nord', 'Musterstraße 1', '20095', 'Hamburg', ' a-101 ')"
                )
                connection.commit()

            with self.assertRaises(MigrationError) as error:
                apply_migrations(db_path, backup_dir=report_directory)

            with closing(sqlite3.connect(db_path)) as connection:
                venue_table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'exam_venue'"
                ).fetchone()
                migration_row = connection.execute(
                    "SELECT 1 FROM schema_migration WHERE name = '025_model_exam_venues.sql'"
                ).fetchone()
                location_count = connection.execute("SELECT count(*) FROM location").fetchone()[0]
            report = json.loads((report_directory / MACHINE_REPORT_NAME).read_text())
            backup_exists = bool(list(report_directory.glob("*.sqlite")))
            human_report_exists = (report_directory / HUMAN_REPORT_NAME).is_file()

        self.assertEqual("migration_conflict", error.exception.reason)
        self.assertFalse(venue_table)
        self.assertFalse(migration_row)
        self.assertEqual(5, location_count)
        self.assertIn("duplicate_room_name", {entry["code"] for entry in report["conflicts"]})
        self.assertTrue(backup_exists)
        self.assertTrue(human_report_exists)

    def test_duplicate_venue_names_outside_an_exact_group_stop_before_schema_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            db_path, report_directory = self._legacy_database(directory)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    "INSERT INTO location "
                    "(id, committee_id, name, street, postal_code, city, room) "
                    "VALUES (14, 1, 'Campus Nord', 'Musterstraße 2', '20095', 'Hamburg', 'C-301')"
                )
                connection.commit()

            with self.assertRaises(MigrationError) as error:
                apply_migrations(db_path, backup_dir=report_directory)

            with closing(sqlite3.connect(db_path)) as connection:
                venue_table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'exam_venue'"
                ).fetchone()
                migration_row = connection.execute(
                    "SELECT 1 FROM schema_migration WHERE name = '025_model_exam_venues.sql'"
                ).fetchone()
            report = json.loads((report_directory / MACHINE_REPORT_NAME).read_text())

        self.assertEqual("migration_conflict", error.exception.reason)
        self.assertFalse(venue_table)
        self.assertFalse(migration_row)
        self.assertIn("duplicate_venue_name", {entry["code"] for entry in report["conflicts"]})


if __name__ == "__main__":
    unittest.main()
