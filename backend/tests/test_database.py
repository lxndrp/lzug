from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.database import (
    BUSY_TIMEOUT_MS,
    SQLITE_JOURNAL_MODE,
    MigrationError,
    connect,
    connection_scope,
    database_path,
    database_url,
    engine_for,
    initialize,
    is_ready,
    migration_status,
    sqlite_settings,
)
from backend.tests.helpers import TempDatabase


class DatabaseTests(unittest.TestCase):
    def test_connection_scope_closes_the_connection_and_engine(self) -> None:
        with TempDatabase() as db_path, connection_scope(db_path) as connection:
            self.assertEqual(1, connection.execute(text("SELECT 1")).scalar_one())

        self.assertTrue(connection.closed)

    def test_each_connection_uses_the_self_hosting_sqlite_settings(self) -> None:
        with TempDatabase() as db_path, connect(db_path) as connection:
            settings = sqlite_settings(connection)

        self.assertEqual(
            {
                "foreign_keys": 1,
                "journal_mode": SQLITE_JOURNAL_MODE,
                "synchronous": 1,
                "busy_timeout": BUSY_TIMEOUT_MS,
            },
            settings,
        )

    def test_database_path_accepts_paths_and_sqlite_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configured.sqlite"

            self.assertEqual(path, database_path(path))
            self.assertEqual(path, database_path(database_url(path)))

    def test_database_path_reads_one_environment_setting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "environment.sqlite"

            with patch.dict(
                "os.environ",
                {"LZUG_DATABASE_URL": database_url(path), "LZUG_DATABASE_PATH": ""},
            ):
                self.assertEqual(path, database_path())

            with patch.dict(
                "os.environ",
                {
                    "LZUG_DATABASE_URL": database_url(path),
                    "LZUG_DATABASE_PATH": str(path),
                },
            ):
                with self.assertRaisesRegex(ValueError, "only one"):
                    database_path()

    def test_readiness_requires_an_initialized_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "readiness.sqlite"

            self.assertFalse(is_ready(db_path))
            initialize(db_path)
            self.assertTrue(is_ready(db_path))

    def test_busy_timeout_allows_a_waiting_writer_after_the_lock_is_released(self) -> None:
        with TempDatabase() as db_path:
            first_engine = engine_for(db_path)
            second_engine = engine_for(db_path)
            first = first_engine.connect()
            second = second_engine.connect()
            transaction = first.begin()
            first.execute(text("UPDATE candidate SET last_name = 'Erster' WHERE id = 1"))

            started = Event()
            finished = Event()
            errors: list[BaseException] = []

            def write_from_second_connection() -> None:
                started.set()
                try:
                    with second.begin():
                        second.execute(
                            text("UPDATE candidate SET last_name = 'Zweiter' WHERE id = 1")
                        )
                except BaseException as error:  # pragma: no cover - asserted below
                    errors.append(error)
                finally:
                    finished.set()

            writer = Thread(target=write_from_second_connection)
            writer.start()
            self.assertTrue(started.wait(timeout=1))
            self.assertFalse(finished.wait(timeout=0.1))
            transaction.commit()
            self.assertTrue(finished.wait(timeout=2))
            writer.join(timeout=1)

            second.close()
            first.close()
            second_engine.dispose()
            first_engine.dispose()

            self.assertEqual([], errors)
            with connect(db_path) as connection:
                last_name = connection.execute(
                    text("SELECT last_name FROM candidate WHERE id = 1")
                ).scalar_one()
            self.assertEqual("Zweiter", last_name)

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
                    text(
                        "INSERT INTO round_candidate "
                        "(exam_round_id, candidate_id, attempt_number) "
                        "VALUES (999, 999, 1)"
                    )
                )

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

    def test_initialize_rejects_unversioned_existing_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "legacy.sqlite3"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    "CREATE TABLE planning_settings "
                    "(id INTEGER PRIMARY KEY, calendar_week_from TEXT, calendar_week_to TEXT)"
                )

            with self.assertRaisesRegex(MigrationError, "no versioned migration history"):
                initialize(db_path)

    def test_initialize_upgrades_legacy_history_and_creates_safety_snapshot(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("DROP TABLE schema_migration_checksum")
                connection.execute("DROP INDEX user_account_one_operator")
                connection.execute(
                    "DELETE FROM schema_migration " "WHERE name IN (?, ?)",
                    ("009_harden_migration_history.sql", "010_add_operator_auth_tokens.sql"),
                )
                connection.execute("DROP TABLE auth_token")
                connection.commit()

            before = migration_status(db_path)
            self.assertEqual("migration_required", before["state"])
            self.assertEqual("008_add_authentication_sessions.sql", before["current"])
            initialize(db_path)
            after = migration_status(db_path)
            self.assertEqual("ready", after["state"])
            self.assertEqual("010_add_operator_auth_tokens.sql", after["current"])
            self.assertTrue(list(db_path.parent.joinpath("backups").glob("*.sqlite")))

            history_before = after["history"]
            initialize(db_path)
            self.assertEqual(history_before, migration_status(db_path)["history"])

    def test_initialize_runs_multiple_pending_migrations_in_order(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("DROP TABLE schema_migration_checksum")
                connection.execute("DROP TABLE auth_session")
                connection.execute("DROP TABLE auth_token")
                connection.execute("DROP INDEX user_account_one_operator")
                connection.execute("ALTER TABLE user_account RENAME TO user_account_legacy")
                connection.executescript("""
                    CREATE TABLE user_account (
                      id INTEGER PRIMARY KEY,
                      person_id INTEGER UNIQUE REFERENCES person(id) ON DELETE SET NULL,
                      email TEXT NOT NULL UNIQUE,
                      password_hash TEXT NOT NULL,
                      passkey_enabled INTEGER NOT NULL DEFAULT 0 CHECK (passkey_enabled IN (0, 1)),
                      two_factor_enabled INTEGER NOT NULL DEFAULT 0
                        CHECK (two_factor_enabled IN (0, 1)),
                      last_login_at TEXT,
                      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      CHECK (two_factor_enabled = 0 OR passkey_enabled = 1)
                    );
                    INSERT INTO user_account (
                      id, person_id, email, password_hash, passkey_enabled,
                      two_factor_enabled, last_login_at, created_at, updated_at
                    )
                    SELECT id, person_id, email, password_hash, passkey_enabled,
                           two_factor_enabled, last_login_at, created_at, updated_at
                    FROM user_account_legacy;
                    DROP TABLE user_account_legacy;
                """)
                connection.execute(
                    "DELETE FROM schema_migration WHERE name IN (?, ?, ?)",
                    (
                        "008_add_authentication_sessions.sql",
                        "009_harden_migration_history.sql",
                        "010_add_operator_auth_tokens.sql",
                    ),
                )
                connection.commit()

            initialize(db_path)
            status = migration_status(db_path)
            self.assertEqual("ready", status["state"])
            self.assertEqual(
                [
                    "008_add_authentication_sessions.sql",
                    "009_harden_migration_history.sql",
                    "010_add_operator_auth_tokens.sql",
                ],
                [entry["name"] for entry in status["history"][-3:]],
            )

    def test_initialize_rejects_unversioned_legacy_round_schema(self) -> None:
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

            with self.assertRaisesRegex(MigrationError, "no versioned migration history"):
                initialize(db_path)

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

    def test_tampered_checksum_makes_database_unready(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    "UPDATE schema_migration_checksum SET checksum = "
                    "'0000000000000000000000000000000000000000000000000000000000000000' "
                    "WHERE name = '007_add_documents.sql'"
                )
                connection.commit()

            self.assertFalse(is_ready(db_path))
            self.assertEqual("migration_error", migration_status(db_path)["state"])

    def test_concurrent_initialization_is_serialized_and_idempotent(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("DROP TABLE schema_migration_checksum")
                connection.execute("DROP INDEX user_account_one_operator")
                connection.execute(
                    "DELETE FROM schema_migration " "WHERE name IN (?, ?)",
                    ("009_harden_migration_history.sql", "010_add_operator_auth_tokens.sql"),
                )
                connection.execute("DROP TABLE auth_token")
                connection.commit()

            started = Event()
            errors: list[BaseException] = []

            def initialize_concurrently() -> None:
                started.wait(timeout=2)
                try:
                    initialize(db_path)
                except BaseException as error:  # pragma: no cover - asserted below
                    errors.append(error)

            threads = [Thread(target=initialize_concurrently) for _ in range(2)]
            for thread in threads:
                thread.start()
            started.set()
            for thread in threads:
                thread.join(timeout=5)

            self.assertEqual([], errors)
            self.assertEqual("ready", migration_status(db_path)["state"])

    def test_failed_migration_can_be_retried_without_recording_a_false_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "retry.sqlite3"
            migration_directory = Path(directory) / "migrations"
            migration_directory.mkdir()
            for migration in Path("db/migrations").glob("*.sql"):
                shutil.copy(migration, migration_directory / migration.name)
            (migration_directory / "009_harden_migration_history.sql").write_text(
                "BEGIN; ALTER TABLE missing_table ADD COLUMN broken TEXT; COMMIT;",
                encoding="utf-8",
            )
            initialize(db_path, with_seed=False, reset=True)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("DROP TABLE schema_migration_checksum")
                connection.execute("DROP INDEX user_account_one_operator")
                connection.execute(
                    "DELETE FROM schema_migration " "WHERE name IN (?, ?)",
                    ("009_harden_migration_history.sql", "010_add_operator_auth_tokens.sql"),
                )
                connection.execute("DROP TABLE auth_token")
                connection.commit()

            with patch("backend.database.MIGRATIONS_PATH", migration_directory):
                with self.assertRaisesRegex(MigrationError, "009_harden_migration_history"):
                    initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                self.assertIsNone(
                    connection.execute(
                        "SELECT 1 FROM schema_migration "
                        "WHERE name = '009_harden_migration_history.sql'"
                    ).fetchone()
                )

            shutil.copy(
                Path("db/migrations/009_harden_migration_history.sql"),
                migration_directory / "009_harden_migration_history.sql",
            )
            with patch("backend.database.MIGRATIONS_PATH", migration_directory):
                initialize(db_path)
            self.assertEqual("ready", migration_status(db_path)["state"])

    def test_unknown_history_makes_database_unready(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    "DELETE FROM schema_migration WHERE name = ?",
                    ("009_harden_migration_history.sql",),
                )
                connection.execute(
                    "INSERT INTO schema_migration (name) VALUES (?)", ("999_unknown.sql",)
                )
                connection.commit()

            self.assertFalse(is_ready(db_path))
            self.assertEqual("migration_error", migration_status(db_path)["state"])


if __name__ == "__main__":
    unittest.main()
