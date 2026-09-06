from __future__ import annotations

import json
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

from backend.calendar import CalendarService
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
from backend.planning import ConfirmedPlanChange, PlanningService
from backend.tests.fixture_data import (
    ADAPTER_COUNTS,
    CANDIDATE_EXAM_NUMBERS,
    FIXTURE_IDS,
    FIXTURE_ROOT,
)
from backend.tests.helpers import TempDatabase, development_seed_sql


def _rewind_plan_reference_json(raw: str) -> str:
    """Restore legacy location keys while preparing an earlier migration fixture."""
    value = json.loads(raw)

    def rewind(item):
        if isinstance(item, list):
            return [rewind(entry) for entry in item]
        if not isinstance(item, dict):
            return item
        restored = {key: rewind(entry) for key, entry in item.items()}
        for new, old in (
            ("room_id", "location_id"),
            ("default_room_id", "default_location_id"),
        ):
            if new in restored:
                restored[old] = restored.pop(new)
        return restored

    return json.dumps(rewind(value), separators=(",", ":"), sort_keys=True)


def rewind_exam_venue_migration(connection: sqlite3.Connection) -> None:
    """Restore the pre-025 schema for tests of earlier upgrade paths."""
    if not connection.execute(
        "SELECT 1 FROM schema_migration WHERE name = ?",
        ("025_model_exam_venues.sql",),
    ).fetchone():
        return
    connection.create_function("lzug_rewind_plan_json", 1, _rewind_plan_reference_json)
    cleanup_checksum = (
        "DELETE FROM schema_migration_checksum "
        "WHERE name IN ("
        "'025_model_exam_venues.sql', '027_expand_exam_venue_audit.sql', "
        "'028_add_exam_venue_change_notifications.sql'"
        ");"
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("schema_migration_checksum",),
        ).fetchone()
        else ""
    )
    connection.executescript(f"""
        PRAGMA foreign_keys = OFF;
        BEGIN TRANSACTION;

        CREATE TABLE location (
          id INTEGER PRIMARY KEY,
          committee_id INTEGER NOT NULL REFERENCES committee(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          street TEXT NOT NULL,
          postal_code TEXT NOT NULL,
          city TEXT NOT NULL,
          room TEXT NOT NULL,
          is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        INSERT INTO location (
          id, committee_id, name, street, postal_code, city, room, is_active,
          created_at, updated_at
        )
        SELECT
          room.id,
          COALESCE(venue.committee_id, 1),
          venue.name,
          venue.street,
          venue.postal_code,
          venue.city,
          room.name,
          room.is_active,
          room.created_at,
          room.updated_at
        FROM exam_room AS room
        JOIN exam_venue AS venue ON venue.id = room.venue_id;

        CREATE TABLE planning_settings_025_rewind (
          id INTEGER PRIMARY KEY,
          exam_round_id INTEGER NOT NULL UNIQUE REFERENCES exam_round(id) ON DELETE CASCADE,
          calendar_week_from TEXT NOT NULL,
          calendar_week_to TEXT NOT NULL,
          exams_per_day INTEGER NOT NULL CHECK (exams_per_day >= 1),
          max_exam_days_per_week INTEGER NOT NULL DEFAULT 3
            CHECK (max_exam_days_per_week BETWEEN 1 AND 5),
          lunch_break_enabled INTEGER NOT NULL DEFAULT 1 CHECK (lunch_break_enabled IN (0, 1)),
          exclude_public_holidays INTEGER NOT NULL DEFAULT 0
            CHECK (exclude_public_holidays IN (0, 1)),
          holiday_subdivision_code TEXT,
          default_location_id INTEGER REFERENCES location(id) ON DELETE SET NULL,
          updated_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CHECK (calendar_week_from <= calendar_week_to),
          CHECK (
            holiday_subdivision_code IS NULL
            OR holiday_subdivision_code IN (
              'DE-BB', 'DE-BE', 'DE-BW', 'DE-BY', 'DE-HB', 'DE-HE', 'DE-HH', 'DE-MV',
              'DE-NI', 'DE-NW', 'DE-RP', 'DE-SH', 'DE-SL', 'DE-SN', 'DE-ST', 'DE-TH'
            )
          ),
          CHECK (exclude_public_holidays = 0 OR holiday_subdivision_code IS NOT NULL)
        );
        INSERT INTO planning_settings_025_rewind (
          id, exam_round_id, calendar_week_from, calendar_week_to, exams_per_day,
          max_exam_days_per_week, lunch_break_enabled, exclude_public_holidays,
          holiday_subdivision_code, default_location_id, updated_by_member_id,
          created_at, updated_at
        )
        SELECT
          id, exam_round_id, calendar_week_from, calendar_week_to, exams_per_day,
          max_exam_days_per_week, lunch_break_enabled, exclude_public_holidays,
          holiday_subdivision_code, default_room_id, updated_by_member_id,
          created_at, updated_at
        FROM planning_settings;
        DROP TABLE planning_settings;
        ALTER TABLE planning_settings_025_rewind RENAME TO planning_settings;

        CREATE TABLE exam_day_025_rewind (
          id INTEGER PRIMARY KEY,
          exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
          location_id INTEGER NOT NULL REFERENCES location(id) ON DELETE RESTRICT,
          date TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'proposed' CHECK (
            status IN ('proposed', 'confirmed', 'changed', 'cancelled', 'completed')
          ),
          revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
          closure_status TEXT NOT NULL DEFAULT 'open' CHECK (
            closure_status IN ('open', 'closed', 'closed_exception', 'reopening', 'historical')
          ),
          lunch_break_enabled INTEGER NOT NULL DEFAULT 1 CHECK (lunch_break_enabled IN (0, 1)),
          created_from_proposal INTEGER NOT NULL DEFAULT 1 CHECK (created_from_proposal IN (0, 1)),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (exam_round_id, date)
        );
        INSERT INTO exam_day_025_rewind (
          id, exam_round_id, location_id, date, status, revision, closure_status,
          lunch_break_enabled, created_from_proposal, created_at, updated_at
        )
        SELECT
          id, exam_round_id, room_id, date, status, revision, closure_status,
          lunch_break_enabled, created_from_proposal, created_at, updated_at
        FROM exam_day;
        DROP TABLE exam_day;
        ALTER TABLE exam_day_025_rewind RENAME TO exam_day;
        CREATE INDEX exam_day_round_date ON exam_day(exam_round_id, date);

        UPDATE confirmed_plan_revision
        SET before_state_json = lzug_rewind_plan_json(before_state_json),
            after_state_json = lzug_rewind_plan_json(after_state_json);

        DROP TRIGGER IF EXISTS exam_venue_active_requires_room_insert;
        DROP TRIGGER IF EXISTS exam_venue_active_requires_room_update;
        DROP TRIGGER IF EXISTS exam_room_keep_active_venue_on_update;
        DROP TRIGGER IF EXISTS exam_room_keep_active_venue_on_delete;
        DROP TRIGGER IF EXISTS exam_venue_contact_room_same_venue_insert;
        DROP TRIGGER IF EXISTS exam_venue_contact_room_same_venue_update;
        DROP TRIGGER IF EXISTS exam_venue_audit_immutable_update;
        DROP TRIGGER IF EXISTS exam_venue_audit_immutable_delete;
        DROP TRIGGER IF EXISTS exam_venue_migration_report_immutable_update;
        DROP TRIGGER IF EXISTS exam_venue_migration_report_immutable_delete;
        DROP TABLE exam_venue_contact_room;
        DROP TABLE exam_venue_contact;
        DROP TABLE legacy_location_room_mapping;
        DROP TABLE exam_venue_audit_event;
        DROP TABLE exam_venue_migration_report;
        DROP TABLE exam_room;
        DROP TABLE exam_venue;
        {cleanup_checksum}
        DELETE FROM schema_migration
        WHERE name IN (
          '025_model_exam_venues.sql',
          '027_expand_exam_venue_audit.sql',
          '028_add_exam_venue_change_notifications.sql'
        );
        COMMIT;
        PRAGMA foreign_keys = ON;
    """)


def rewind_notification_migration(connection: sqlite3.Connection) -> None:
    """Restore the pre-013 schema used by migration-order test fixtures."""
    connection.executescript("""
        DELETE FROM schema_migration
        WHERE name = '028_add_exam_venue_change_notifications.sql';
        DROP INDEX IF EXISTS absence_report_assignment_active;
        DROP INDEX IF EXISTS absence_report_day_status;
        DROP INDEX IF EXISTS absence_audit_report_created;
        DROP TABLE IF EXISTS absence_audit_event;
        ALTER TABLE absence_report DROP COLUMN exam_day_assignment_id;
        ALTER TABLE absence_report DROP COLUMN reported_by_member_id;
        ALTER TABLE absence_report DROP COLUMN version;
        ALTER TABLE replacement_response DROP COLUMN requested_at;
        ALTER TABLE replacement_response DROP COLUMN expires_at;
        ALTER TABLE replacement_response DROP COLUMN urgent;
        DROP TABLE notification_delivery;
        DROP TABLE push_subscription;
        DROP TABLE notification;
        CREATE TABLE notification (
          id INTEGER PRIMARY KEY,
          exam_round_id INTEGER REFERENCES exam_round(id) ON DELETE CASCADE,
          recipient_member_id INTEGER REFERENCES committee_member(id) ON DELETE SET NULL,
          recipient_email TEXT NOT NULL,
          notification_type TEXT NOT NULL,
          subject TEXT NOT NULL,
          body TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          scheduled_at TEXT,
          sent_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)


def rewind_calendar_migration(connection: sqlite3.Connection) -> None:
    """Restore the pre-014 calendar table used by migration-order fixtures."""
    connection.executescript("""
        DROP TABLE calendar_feed;
        DROP TABLE calendar_event;
        CREATE TABLE calendar_event (
          id INTEGER PRIMARY KEY,
          exam_slot_id INTEGER REFERENCES exam_slot(id) ON DELETE CASCADE,
          exam_day_id INTEGER REFERENCES exam_day(id) ON DELETE CASCADE,
          recipient_member_id INTEGER REFERENCES committee_member(id) ON DELETE SET NULL,
          external_event_id TEXT,
          status TEXT NOT NULL DEFAULT 'pending',
          sent_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CHECK (exam_slot_id IS NOT NULL OR exam_day_id IS NOT NULL)
        );
        CREATE INDEX calendar_event_status ON calendar_event(status);
        """)


def rewind_delivery_claim_migration(connection: sqlite3.Connection) -> None:
    """Restore the pre-016 delivery table while preserving its queued rows."""
    connection.executescript("""
        DROP INDEX notification_delivery_due;
        ALTER TABLE notification_delivery RENAME TO notification_delivery_claimed;
        CREATE TABLE notification_delivery (
          id INTEGER PRIMARY KEY,
          notification_id INTEGER NOT NULL REFERENCES notification(id) ON DELETE CASCADE,
          channel TEXT NOT NULL CHECK (channel IN ('web_push', 'email', 'sink')),
          target_key TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN (
            'pending', 'technically_confirmed', 'temporarily_failed',
            'permanently_failed', 'unavailable'
          )),
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          next_attempt_at TEXT,
          technical_confirmed_at TEXT,
          error_code TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE (notification_id, channel, target_key)
        );
        INSERT INTO notification_delivery (
          id, notification_id, channel, target_key, status, attempt_count,
          next_attempt_at, technical_confirmed_at, error_code, created_at, updated_at
        )
        SELECT
          id, notification_id, channel, target_key, status, attempt_count,
          next_attempt_at, technical_confirmed_at, error_code, created_at, updated_at
        FROM notification_delivery_claimed;
        DROP TABLE notification_delivery_claimed;
        CREATE INDEX notification_delivery_due
          ON notification_delivery(status, next_attempt_at);
        DELETE FROM schema_migration_checksum
          WHERE name = '016_claim_notification_deliveries.sql';
        DELETE FROM schema_migration
          WHERE name = '016_claim_notification_deliveries.sql';
    """)


def rewind_exam_protocol_migration(
    connection: sqlite3.Connection, *, remove_history: bool = False
) -> None:
    """Restore the pre-017 schema for migration-order and data tests."""
    rewind_exam_result_migration(connection)
    connection.executescript("""
        DROP TABLE IF EXISTS exam_protocol_response;
        DROP TABLE IF EXISTS exam_protocol_entry;
        DROP TABLE IF EXISTS exam_protocol_retention;
        DROP TABLE IF EXISTS exam_protocol_correction_request;
        DROP TABLE IF EXISTS exam_protocol_revision;
        DROP TABLE IF EXISTS exam_protocol_participant;
        DROP TABLE IF EXISTS exam_protocol;
    """)
    if remove_history:
        connection.execute(
            "DELETE FROM schema_migration_checksum WHERE name = ?",
            ("017_add_exam_protocols.sql",),
        )
        connection.execute(
            "DELETE FROM schema_migration WHERE name = ?",
            ("017_add_exam_protocols.sql",),
        )


def rewind_exam_result_migration(connection: sqlite3.Connection) -> None:
    """Restore the pre-018 result schema without leaving a history gap."""
    rewind_exam_day_closure_migration(connection)
    connection.executescript("""
        DROP TABLE IF EXISTS result_export;
        DROP TABLE IF EXISTS result_retention;
        DROP TABLE IF EXISTS result_communication;
        DROP TABLE IF EXISTS result_correction;
        DROP TABLE IF EXISTS result_record_confirmation;
        DROP TABLE IF EXISTS result_determination;
        DROP TABLE IF EXISTS result_calculation;
        DROP TABLE IF EXISTS external_exam_result;
        DROP TABLE IF EXISTS committee_assessment;
        DROP TABLE IF EXISTS assessment_disclosure;
        DROP TABLE IF EXISTS individual_assessment;
        DROP TABLE IF EXISTS exam_result;
        DROP TABLE IF EXISTS exam_round_assessment_binding;
        DROP TABLE IF EXISTS assessment_model_version;
        ALTER TABLE committee DROP COLUMN ihk;
        DELETE FROM schema_migration
          WHERE name = '018_add_exam_results.sql';
    """)
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("schema_migration_checksum",),
    ).fetchone():
        connection.execute(
            "DELETE FROM schema_migration_checksum WHERE name = ?",
            ("018_add_exam_results.sql",),
        )


def rewind_plan_consequence_migration(connection: sqlite3.Connection) -> None:
    """Restore notification tables and history to their pre-021 contract."""
    rewind_exam_round_lifecycle_migration(connection)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(notification)")}
    connection.executescript("""
        DROP TABLE IF EXISTS plan_consequence;
        DROP TABLE IF EXISTS plan_consequence_batch;
    """)
    if "superseded_at" in columns:
        connection.executescript("""
            DROP INDEX notification_delivery_due;
            DROP INDEX notification_recipient_created;
            DROP INDEX notification_committee_created;
            ALTER TABLE notification_delivery RENAME TO notification_delivery_latest;
            ALTER TABLE notification RENAME TO notification_latest;
            CREATE TABLE notification (
              id INTEGER PRIMARY KEY,
              committee_id INTEGER NOT NULL REFERENCES committee(id) ON DELETE CASCADE,
              exam_round_id INTEGER REFERENCES exam_round(id) ON DELETE CASCADE,
              recipient_member_id INTEGER NOT NULL
                REFERENCES committee_member(id) ON DELETE CASCADE,
              event_type TEXT NOT NULL,
              origin_key TEXT NOT NULL,
              title TEXT NOT NULL,
              message TEXT NOT NULL,
              action_path TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE (recipient_member_id, event_type, origin_key)
            );
            INSERT INTO notification (
              id, committee_id, exam_round_id, recipient_member_id, event_type,
              origin_key, title, message, action_path, created_at
            )
            SELECT
              id, committee_id, exam_round_id, recipient_member_id, event_type,
              origin_key, title, message, action_path, created_at
            FROM notification_latest
            WHERE event_type != 'plan_changed';
            CREATE TABLE notification_delivery (
              id INTEGER PRIMARY KEY,
              notification_id INTEGER NOT NULL
                REFERENCES notification(id) ON DELETE CASCADE,
              channel TEXT NOT NULL,
              target_key TEXT NOT NULL,
              status TEXT NOT NULL,
              attempt_count INTEGER NOT NULL DEFAULT 0,
              next_attempt_at TEXT,
              technical_confirmed_at TEXT,
              error_code TEXT,
              claim_token TEXT,
              claimed_at TEXT,
              claim_expires_at TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE (notification_id, channel, target_key)
            );
            INSERT INTO notification_delivery (
              id, notification_id, channel, target_key, status, attempt_count,
              next_attempt_at, technical_confirmed_at, error_code,
              claim_token, claimed_at, claim_expires_at, created_at, updated_at
            )
            SELECT
              delivery.id, delivery.notification_id, delivery.channel,
              delivery.target_key, delivery.status, delivery.attempt_count,
              delivery.next_attempt_at, delivery.technical_confirmed_at,
              delivery.error_code, delivery.claim_token, delivery.claimed_at,
              delivery.claim_expires_at, delivery.created_at, delivery.updated_at
            FROM notification_delivery_latest AS delivery
            JOIN notification ON notification.id = delivery.notification_id;
            DROP TABLE notification_delivery_latest;
            DROP TABLE notification_latest;
            CREATE INDEX notification_recipient_created
              ON notification(recipient_member_id, created_at DESC, id DESC);
            CREATE INDEX notification_committee_created
              ON notification(committee_id, created_at DESC, id DESC);
            CREATE INDEX notification_delivery_due
              ON notification_delivery(status, next_attempt_at, claim_expires_at, id);
        """)
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("schema_migration_checksum",),
    ).fetchone():
        connection.execute(
            "DELETE FROM schema_migration_checksum WHERE name = ?",
            ("022_add_plan_consequences.sql",),
        )
    connection.execute(
        "DELETE FROM schema_migration WHERE name = ?",
        ("022_add_plan_consequences.sql",),
    )


def rewind_backup_recipient_migration(connection: sqlite3.Connection) -> None:
    """Remove the post-024 recipient configuration before older rewinds."""
    connection.executescript("""
        DROP INDEX IF EXISTS backup_recipient_audit_occurred;
        DROP TABLE IF EXISTS backup_recipient_audit;
        DROP TABLE IF EXISTS backup_recipient;
        DELETE FROM schema_migration
          WHERE name = '026_add_backup_recipient.sql';
    """)
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("schema_migration_checksum",),
    ).fetchone():
        connection.execute(
            "DELETE FROM schema_migration_checksum WHERE name = ?",
            ("026_add_backup_recipient.sql",),
        )


def rewind_artifact_operation_migration(connection: sqlite3.Connection) -> None:
    """Restore the pre-024 instance schema without leaving a history gap."""
    rewind_backup_recipient_migration(connection)
    rewind_exam_venue_migration(connection)
    connection.executescript("""
        DROP INDEX IF EXISTS artifact_operation_occurred;
        DROP TABLE IF EXISTS artifact_operation;
        DROP TABLE IF EXISTS instance_metadata;
        DELETE FROM schema_migration
          WHERE name = '024_add_artifact_operations.sql';
    """)
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("schema_migration_checksum",),
    ).fetchone():
        connection.execute(
            "DELETE FROM schema_migration_checksum WHERE name = ?",
            ("024_add_artifact_operations.sql",),
        )


def rewind_exam_round_lifecycle_migration(connection: sqlite3.Connection) -> None:
    """Restore the pre-023 round schema without leaving a history gap."""
    rewind_artifact_operation_migration(connection)
    if not connection.execute(
        "SELECT 1 FROM schema_migration WHERE name = ?",
        ("023_add_exam_round_lifecycle.sql",),
    ).fetchone():
        return
    connection.executescript("""
        DROP TRIGGER IF EXISTS exam_round_decision_immutable_update;
        DROP TRIGGER IF EXISTS exam_round_decision_immutable_delete;
        DROP TABLE IF EXISTS exam_round_export;
        DROP TABLE IF EXISTS exam_round_ihk_status;
        DROP TABLE IF EXISTS exam_round_task;
        DROP TABLE IF EXISTS exam_round_audit_event;
        DROP TABLE IF EXISTS exam_round_reopening;
        DROP TABLE IF EXISTS exam_round_decision;
        DROP TABLE IF EXISTS exam_round_migration_evidence;
        DROP TABLE IF EXISTS exam_half_year_migration_evidence;
        ALTER TABLE round_candidate DROP COLUMN terminal_at;
        ALTER TABLE round_candidate DROP COLUMN ihk_decision_reference;
        ALTER TABLE round_candidate DROP COLUMN postponed_until;
        ALTER TABLE round_candidate DROP COLUMN effective_new_round_id;
        ALTER TABLE round_candidate DROP COLUMN terminal_reason;
        ALTER TABLE round_candidate DROP COLUMN terminal_status;
        ALTER TABLE exam_round DROP COLUMN legacy_status;
        ALTER TABLE exam_round DROP COLUMN lifecycle_status;
        ALTER TABLE exam_round DROP COLUMN revision;
        ALTER TABLE exam_half_year DROP COLUMN legacy_status;
        DELETE FROM schema_migration
          WHERE name = '023_add_exam_round_lifecycle.sql';
    """)
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("schema_migration_checksum",),
    ).fetchone():
        connection.execute(
            "DELETE FROM schema_migration_checksum WHERE name = ?",
            ("023_add_exam_round_lifecycle.sql",),
        )


def rewind_exam_day_closure_migration(connection: sqlite3.Connection) -> None:
    """Restore the pre-019 day schema without leaving a history gap."""
    rewind_committee_bootstrap_migration(connection)
    connection.executescript("""
        DROP TABLE IF EXISTS confirmed_plan_revision;
        DROP TABLE IF EXISTS exam_day_export;
        DROP TABLE IF EXISTS exam_day_audit_event;
        DROP TABLE IF EXISTS exam_day_task;
        DROP TABLE IF EXISTS exam_day_reopening;
        DROP TABLE IF EXISTS exam_day_closure;
        ALTER TABLE exam_day DROP COLUMN closure_status;
        ALTER TABLE exam_day DROP COLUMN revision;
        DELETE FROM schema_migration
          WHERE name IN (
            '019_add_exam_day_closures.sql',
            '020_add_confirmed_plan_revisions.sql',
            '022_add_plan_consequences.sql'
          );
    """)
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("schema_migration_checksum",),
    ).fetchone():
        connection.execute(
            "DELETE FROM schema_migration_checksum WHERE name IN (?, ?, ?)",
            (
                "019_add_exam_day_closures.sql",
                "020_add_confirmed_plan_revisions.sql",
                "022_add_plan_consequences.sql",
            ),
        )


def rewind_committee_bootstrap_migration(connection: sqlite3.Connection) -> None:
    """Restore the pre-021 committee schema without leaving a history gap."""
    rewind_plan_consequence_migration(connection)
    connection.executescript("""
        DROP TRIGGER IF EXISTS committee_admin_operation_immutable_update;
        DROP TRIGGER IF EXISTS committee_admin_operation_immutable_delete;
        DROP TABLE IF EXISTS committee_admin_operation;
        ALTER TABLE committee DROP COLUMN bootstrap_state;
        ALTER TABLE committee DROP COLUMN is_active;
        DELETE FROM schema_migration
          WHERE name = '021_add_committee_bootstrap.sql';
    """)
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("schema_migration_checksum",),
    ).fetchone():
        connection.execute(
            "DELETE FROM schema_migration_checksum WHERE name = ?",
            ("021_add_committee_bootstrap.sql",),
        )


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
                    "exam_venue",
                    "exam_room",
                    "exam_venue_contact",
                    "exam_venue_contact_room",
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
                "committee": ADAPTER_COUNTS["seed"]["committees"],
                "committee_member": ADAPTER_COUNTS["seed"]["memberships"],
                "exam_venue": ADAPTER_COUNTS["seed"]["locations"],
                "exam_room": ADAPTER_COUNTS["seed"]["rooms"],
                "exam_venue_contact": ADAPTER_COUNTS["seed"]["location_contacts"],
                "exam_venue_contact_room": 1,
                "candidate": ADAPTER_COUNTS["seed"]["candidates"],
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
                        "ihk_exam_number": CANDIDATE_EXAM_NUMBERS[
                            f"{FIXTURE_ROOT}.candidate.planchange"
                        ],
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
                    text("INSERT INTO committee (id, name, occupation) VALUES (99, 'Alt', 'FI')")
                )

            initialize(db_path, seed_sql=development_seed_sql(), reset=True)

            with connect(db_path) as connection:
                ids = [
                    row[0]
                    for row in connection.execute(text("SELECT id FROM committee ORDER BY id"))
                ]

        expected_ids = sorted(
            fixture["id"]
            for fixture in FIXTURE_IDS.values()
            if fixture["entity_type"] == "committees"
        )
        self.assertEqual(expected_ids, ids)

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
                rewind_exam_protocol_migration(connection)
                rewind_notification_migration(connection)
                rewind_calendar_migration(connection)
                connection.execute("DROP INDEX user_account_one_operator")
                connection.execute(
                    "DELETE FROM schema_migration WHERE name IN (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "009_harden_migration_history.sql",
                        "010_add_operator_auth_tokens.sql",
                        "011_add_local_password_totp_auth.sql",
                        "012_add_plan_revision.sql",
                        "013_add_notifications.sql",
                        "014_add_personal_calendars.sql",
                        "015_add_absence_replacement_process.sql",
                        "016_claim_notification_deliveries.sql",
                        "017_add_exam_protocols.sql",
                    ),
                )
                connection.execute("DROP TABLE auth_token")
                connection.execute("DROP TABLE auth_recovery_code")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_enabled")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_last_step")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_secret_encrypted")
                connection.execute("ALTER TABLE exam_round DROP COLUMN plan_revision")
                connection.commit()

            before = migration_status(db_path)
            self.assertEqual("migration_required", before["state"])
            self.assertEqual("008_add_authentication_sessions.sql", before["current"])
            initialize(db_path)
            after = migration_status(db_path)
            self.assertEqual("ready", after["state"])
            self.assertEqual("028_add_exam_venue_change_notifications.sql", after["current"])
            self.assertTrue(list(db_path.parent.joinpath("backups").glob("*.sqlite")))

            history_before = after["history"]
            initialize(db_path)
            self.assertEqual(history_before, migration_status(db_path)["history"])

    def test_initialize_applies_pending_migrations_before_the_seed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "seeded.sqlite3"

            initialize(db_path, seed_sql=development_seed_sql())

            with closing(sqlite3.connect(db_path)) as connection:
                committee = connection.execute(
                    "SELECT is_active, bootstrap_state FROM committee WHERE id = 1"
                ).fetchone()
                evidence = connection.execute(
                    "SELECT result, occurred_at, technical_source "
                    "FROM committee_admin_operation WHERE committee_id = 1"
                ).fetchone()
                revision_table = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'confirmed_plan_revision'"
                ).fetchone()

            self.assertEqual((1, "ready"), committee)
            self.assertEqual(
                ("ready", "2026-01-01T00:00:00+00:00", "migration"),
                evidence,
            )
            self.assertEqual(("confirmed_plan_revision",), revision_table)
            self.assertEqual(
                "028_add_exam_venue_change_notifications.sql",
                migration_status(db_path)["current"],
            )

    def test_exam_venue_audit_accepts_operator_promotion_events_and_remains_immutable(
        self,
    ) -> None:
        with TempDatabase() as db_path, closing(sqlite3.connect(db_path)) as connection:
            cursor = connection.execute(
                """
                INSERT INTO exam_venue_audit_event (
                  venue_id, entity_type, entity_id, entity_revision, change_type,
                  actor_kind, technical_actor, reason
                )
                VALUES (1, 'venue', 1, 1, 'promotion_requested', 'operator', ?, ?)
                """,
                ("account:99", "Prüfung"),
            )
            connection.commit()

            with self.assertRaisesRegex(sqlite3.IntegrityError, "audit is immutable"):
                connection.execute(
                    "UPDATE exam_venue_audit_event SET reason = 'Geändert' WHERE id = ?",
                    (cursor.lastrowid,),
                )

    def test_initialize_runs_multiple_pending_migrations_in_order(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("DROP TABLE schema_migration_checksum")
                rewind_exam_protocol_migration(connection)
                rewind_notification_migration(connection)
                rewind_calendar_migration(connection)
                connection.execute("DROP TABLE auth_session")
                connection.execute("DROP TABLE auth_token")
                connection.execute("DROP TABLE auth_recovery_code")
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
                    "DELETE FROM schema_migration WHERE name IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "008_add_authentication_sessions.sql",
                        "009_harden_migration_history.sql",
                        "010_add_operator_auth_tokens.sql",
                        "011_add_local_password_totp_auth.sql",
                        "012_add_plan_revision.sql",
                        "013_add_notifications.sql",
                        "014_add_personal_calendars.sql",
                        "015_add_absence_replacement_process.sql",
                        "016_claim_notification_deliveries.sql",
                        "017_add_exam_protocols.sql",
                    ),
                )
                connection.execute("ALTER TABLE exam_round DROP COLUMN plan_revision")
                connection.commit()

            initialize(db_path)
            status = migration_status(db_path)
            self.assertEqual("ready", status["state"])
            self.assertEqual(
                [
                    "009_harden_migration_history.sql",
                    "010_add_operator_auth_tokens.sql",
                    "011_add_local_password_totp_auth.sql",
                    "012_add_plan_revision.sql",
                    "013_add_notifications.sql",
                    "014_add_personal_calendars.sql",
                    "015_add_absence_replacement_process.sql",
                    "016_claim_notification_deliveries.sql",
                    "017_add_exam_protocols.sql",
                    "018_add_exam_results.sql",
                    "019_add_exam_day_closures.sql",
                    "020_add_confirmed_plan_revisions.sql",
                    "021_add_committee_bootstrap.sql",
                    "022_add_plan_consequences.sql",
                    "023_add_exam_round_lifecycle.sql",
                    "024_add_artifact_operations.sql",
                    "025_model_exam_venues.sql",
                    "026_add_backup_recipient.sql",
                    "027_expand_exam_venue_audit.sql",
                    "028_add_exam_venue_change_notifications.sql",
                ],
                [entry["name"] for entry in status["history"][-20:]],
            )

    def test_committee_bootstrap_migration_classifies_legacy_committees_without_changing_ids(
        self,
    ) -> None:
        with TempDatabase() as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                original_ids = {
                    "committee": connection.execute(
                        "SELECT group_concat(id, ',') FROM committee"
                    ).fetchone()[0],
                    "person": connection.execute(
                        "SELECT group_concat(id, ',') FROM person"
                    ).fetchone()[0],
                    "membership": connection.execute(
                        "SELECT group_concat(id, ',') FROM committee_member"
                    ).fetchone()[0],
                }
                rewind_committee_bootstrap_migration(connection)
                connection.commit()

            initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                migrated_ids = {
                    "committee": connection.execute(
                        "SELECT group_concat(id, ',') FROM committee"
                    ).fetchone()[0],
                    "person": connection.execute(
                        "SELECT group_concat(id, ',') FROM person"
                    ).fetchone()[0],
                    "membership": connection.execute(
                        "SELECT group_concat(id, ',') FROM committee_member"
                    ).fetchone()[0],
                }
                committee = connection.execute(
                    "SELECT is_active, bootstrap_state FROM committee WHERE id = 1"
                ).fetchone()
                evidence = connection.execute(
                    "SELECT operation_type, result, technical_source, idempotency_key "
                    "FROM committee_admin_operation WHERE committee_id = 1"
                ).fetchone()

            self.assertEqual(original_ids, migrated_ids)
            self.assertEqual((1, "ready"), committee)
            self.assertEqual(
                ("legacy_assessment", "ready", "migration", None),
                evidence,
            )

    def test_committee_bootstrap_migration_marks_missing_and_conflicting_chairs(self) -> None:
        for expected_state, prepare in (
            (
                "needs_clarification",
                lambda connection: connection.execute(
                    "UPDATE committee_member SET committee_role = 'member' "
                    "WHERE committee_role = 'chair'"
                ),
            ),
            (
                "conflict",
                lambda connection: connection.executescript("""
                    DROP INDEX committee_member_one_chair_per_committee;
                    UPDATE committee_member
                    SET committee_role = 'chair'
                    WHERE id = 2;
                """),
            ),
        ):
            with self.subTest(state=expected_state), TempDatabase() as db_path:
                with closing(sqlite3.connect(db_path)) as connection:
                    rewind_committee_bootstrap_migration(connection)
                    prepare(connection)
                    connection.commit()

                initialize(db_path)

                with closing(sqlite3.connect(db_path)) as connection:
                    state = connection.execute(
                        "SELECT bootstrap_state FROM committee WHERE id = 1"
                    ).fetchone()[0]
                    chair_ids = [
                        row[0]
                        for row in connection.execute(
                            "SELECT id FROM committee_member "
                            "WHERE committee_role = 'chair' AND is_active = 1 ORDER BY id"
                        )
                    ]
                self.assertEqual(expected_state, state)
                expected_chair_ids = []
                if expected_state == "conflict":
                    expected_chair_ids = sorted(
                        FIXTURE_IDS[f"{FIXTURE_ROOT}.{suffix}"]["id"]
                        for suffix in (
                            "membership.chair.athen",
                            "membership.deputy.athen",
                            "membership.chair.feenwald",
                        )
                    )
                self.assertEqual(
                    expected_chair_ids,
                    chair_ids,
                )

    def test_committee_bootstrap_migration_accepts_an_empty_instance(self) -> None:
        with TempDatabase(with_seed=False) as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                rewind_committee_bootstrap_migration(connection)
                connection.commit()

            initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                self.assertEqual(
                    0,
                    connection.execute("SELECT count(*) FROM committee_admin_operation").fetchone()[
                        0
                    ],
                )
            self.assertEqual("ready", migration_status(db_path)["state"])

    def test_delivery_claim_migration_preserves_queued_deliveries(self) -> None:
        with TempDatabase() as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                rewind_exam_protocol_migration(connection, remove_history=True)
                connection.execute("""
                    INSERT INTO notification (
                      committee_id, exam_round_id, recipient_member_id, event_type,
                      origin_key, title, message, action_path
                    )
                    VALUES (
                      1, 1, 1, 'synthetic_test', 'migration:claim-preservation',
                      'Migration test', 'No external content', '/notifications'
                    )
                """)
                notification_id = connection.execute(
                    "SELECT id FROM notification WHERE origin_key = 'migration:claim-preservation'"
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO notification_delivery "
                    "(notification_id, channel, target_key, status, attempt_count) "
                    "VALUES (?, 'sink', 'migration-sink', 'temporarily_failed', 2)",
                    (notification_id,),
                )
                rewind_delivery_claim_migration(connection)
                connection.commit()

            initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(notification_delivery)")
                }
                delivery = connection.execute(
                    "SELECT status, attempt_count, claim_token, claimed_at, claim_expires_at "
                    "FROM notification_delivery WHERE notification_id = ?",
                    (notification_id,),
                ).fetchone()

            self.assertTrue({"claim_token", "claimed_at", "claim_expires_at"}.issubset(columns))
            self.assertEqual(("temporarily_failed", 2, None, None, None), delivery)
            self.assertEqual(
                "028_add_exam_venue_change_notifications.sql",
                migration_status(db_path)["current"],
            )

    def test_plan_consequence_migration_preserves_notifications_and_calendar_identity(
        self,
    ) -> None:
        with TempDatabase() as db_path:
            planning = PlanningService(db_path)
            planning.generate_proposal(1)
            planning.confirm_plan(1)
            plan = planning.get_confirmed_plan(1)
            planning.save_confirmed_plan(
                ConfirmedPlanChange(plan, "Bestehende Revision nicht nachträglich versenden"),
                actor_member_id=1,
            )
            CalendarService(db_path).sync_round(1)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                notification_id = connection.execute(
                    "INSERT INTO notification "
                    "(committee_id, exam_round_id, recipient_member_id, event_type, "
                    " origin_key, title, message, action_path) "
                    "VALUES (1, 1, 1, 'synthetic_test', 'migration:021', "
                    "        'Migration', 'Synthetic', '/notifications')"
                ).lastrowid
                connection.execute(
                    "INSERT INTO notification_delivery "
                    "(notification_id, channel, target_key, status, attempt_count, error_code) "
                    "VALUES (?, 'sink', 'migration-sink', 'temporarily_failed', 2, 'offline')",
                    (notification_id,),
                )
                calendar_before = connection.execute(
                    "SELECT id, external_event_id, version FROM calendar_event ORDER BY id LIMIT 1"
                ).fetchone()
                rewind_plan_consequence_migration(connection)
                connection.commit()

            initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                notification_after = connection.execute(
                    "SELECT id, event_type, superseded_at FROM notification WHERE id = ?",
                    (notification_id,),
                ).fetchone()
                delivery_after = connection.execute(
                    "SELECT status, attempt_count, error_code FROM notification_delivery "
                    "WHERE notification_id = ?",
                    (notification_id,),
                ).fetchone()
                calendar_after = connection.execute(
                    "SELECT id, external_event_id, version FROM calendar_event ORDER BY id LIMIT 1"
                ).fetchone()
                consequence_count = connection.execute(
                    "SELECT COUNT(*) FROM plan_consequence"
                ).fetchone()[0]
                batch = connection.execute(
                    "SELECT status, attempt_count, error_code FROM plan_consequence_batch"
                ).fetchone()

        self.assertEqual((notification_id, "synthetic_test", None), notification_after)
        self.assertEqual(("temporarily_failed", 2, "offline"), delivery_after)
        self.assertEqual(calendar_before, calendar_after)
        self.assertEqual(0, consequence_count)
        self.assertEqual(("succeeded", 0, "migration_not_replayed"), batch)

    def test_exam_result_migration_marks_only_completed_history_without_invented_values(
        self,
    ) -> None:
        with TempDatabase() as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                rewind_exam_result_migration(connection)
                connection.executescript("""
                    INSERT INTO exam_day (
                      id, exam_round_id, location_id, date, status,
                      lunch_break_enabled, created_from_proposal
                    ) VALUES
                      (1, 1, 1, '2026-11-16', 'completed', 1, 1),
                      (2, 1, 1, '2026-11-17', 'confirmed', 1, 1),
                      (3, 1, 1, '2026-11-18', 'proposed', 1, 1);
                    INSERT INTO exam_slot (
                      id, exam_day_id, round_candidate_id, slot_type, starts_at, ends_at,
                      sequence_number, status, actual_started_at, execution_status,
                      actual_completed_at
                    ) VALUES
                      (
                        1, 1, 1, 'regular', '2026-11-16T09:00:00+01:00',
                        '2026-11-16T10:00:00+01:00', 1, 'completed',
                        '2026-11-16T09:03:00+01:00', 'completed',
                        '2026-11-16T10:00:00+01:00'
                      ),
                      (
                        2, 2, 2, 'regular', '2026-11-17T09:00:00+01:00',
                        '2026-11-17T10:00:00+01:00', 1, 'confirmed',
                        '2026-11-17T09:02:00+01:00', 'running', NULL
                      ),
                      (
                        3, 3, 3, 'regular', '2026-11-18T09:00:00+01:00',
                        '2026-11-18T10:00:00+01:00', 1, 'proposed',
                        NULL, 'open', NULL
                      );
                """)
                connection.commit()

            initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                migrated = connection.execute(
                    "SELECT round_candidate_id, source, legacy_status "
                    "FROM exam_result ORDER BY round_candidate_id"
                ).fetchall()
                invented = sum(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "assessment_model_version",
                        "exam_round_assessment_binding",
                        "individual_assessment",
                        "committee_assessment",
                        "external_exam_result",
                        "result_calculation",
                        "result_determination",
                    )
                )

            self.assertEqual(
                [
                    (
                        1,
                        "migration",
                        "no_result_data_in_lzug",
                    )
                ],
                migrated,
            )
            self.assertEqual(0, invented)

    def test_exam_day_closure_migration_preserves_legacy_states_without_invented_evidence(
        self,
    ) -> None:
        with TempDatabase() as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                rewind_exam_day_closure_migration(connection)
                connection.executescript("""
                    INSERT INTO exam_day (
                      id, exam_round_id, location_id, date, status,
                      lunch_break_enabled, created_from_proposal
                    ) VALUES
                      (1, 1, 1, '2026-11-16', 'confirmed', 1, 1),
                      (2, 1, 1, '2026-11-17', 'confirmed', 1, 1),
                      (3, 1, 1, '2026-11-18', 'completed', 1, 1),
                      (4, 1, 1, '2026-11-19', 'cancelled', 1, 1),
                      (5, 1, 1, '2026-11-20', 'confirmed', 1, 1);
                    INSERT INTO exam_slot (
                      id, exam_day_id, round_candidate_id, slot_type, starts_at, ends_at,
                      sequence_number, status, actual_started_at, execution_status,
                      actual_completed_at, status_reason
                    ) VALUES
                      (1, 1, 1, 'regular', '2026-11-16T09:00:00+01:00',
                       '2026-11-16T10:00:00+01:00', 1, 'confirmed', NULL, 'open', NULL, NULL),
                      (2, 2, 2, 'regular', '2026-11-17T09:00:00+01:00',
                       '2026-11-17T10:00:00+01:00', 1, 'confirmed',
                       '2026-11-17T09:02:00+01:00', 'running', NULL, NULL),
                      (3, 3, 3, 'regular', '2026-11-18T09:00:00+01:00',
                       '2026-11-18T10:00:00+01:00', 1, 'completed',
                       '2026-11-18T09:01:00+01:00', 'completed',
                       '2026-11-18T10:00:00+01:00', NULL),
                      (4, 4, 4, 'regular', '2026-11-19T09:00:00+01:00',
                       '2026-11-19T10:00:00+01:00', 1, 'cancelled', NULL, 'cancelled', NULL,
                       'Synthetischer Altbestand'),
                      (5, 5, 5, 'regular', '2026-11-20T09:00:00+01:00',
                       '2026-11-20T10:00:00+01:00', 1, 'completed', NULL, 'completed', NULL,
                       NULL);
                """)
                connection.commit()

            initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                days = connection.execute(
                    "SELECT id, revision, closure_status FROM exam_day ORDER BY id"
                ).fetchall()
                invented = sum(
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "exam_day_closure",
                        "exam_day_reopening",
                        "exam_day_task",
                        "exam_day_audit_event",
                        "exam_day_export",
                    )
                )

            self.assertEqual(
                [
                    (1, 1, "open"),
                    (2, 1, "open"),
                    (3, 1, "historical"),
                    (4, 1, "historical"),
                    (5, 1, "open"),
                ],
                days,
            )
            self.assertEqual(0, invented)

    def test_exam_round_lifecycle_migration_preserves_legacy_meaning_without_evidence(
        self,
    ) -> None:
        with TempDatabase() as db_path:
            with closing(sqlite3.connect(db_path)) as connection:
                rewind_exam_round_lifecycle_migration(connection)
                connection.execute("UPDATE exam_half_year SET status = 'completed' WHERE id = 1")
                connection.execute("UPDATE exam_round SET status = 'completed' WHERE id = 1")
                connection.commit()

            initialize(db_path)

            with closing(sqlite3.connect(db_path)) as connection:
                half_year = connection.execute(
                    "SELECT status, legacy_status FROM exam_half_year WHERE id = 1"
                ).fetchone()
                exam_round = connection.execute(
                    "SELECT lifecycle_status, legacy_status FROM exam_round WHERE id = 1"
                ).fetchone()
                half_year_evidence = connection.execute(
                    "SELECT previous_status, resulting_status "
                    "FROM exam_half_year_migration_evidence WHERE exam_half_year_id = 1"
                ).fetchone()
                round_evidence = connection.execute(
                    "SELECT previous_status, resulting_lifecycle_status, "
                    "clarification_required FROM exam_round_migration_evidence "
                    "WHERE exam_round_id = 1"
                ).fetchone()
                invented = connection.execute(
                    "SELECT count(*) FROM exam_round_decision"
                ).fetchone()[0]

        self.assertEqual(("archived", "completed"), half_year)
        self.assertEqual(("historical", "completed"), exam_round)
        self.assertEqual(("completed", "archived"), half_year_evidence)
        self.assertEqual(("completed", "historical", 0), round_evidence)
        self.assertEqual(0, invented)

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
                rewind_exam_protocol_migration(connection)
                rewind_notification_migration(connection)
                rewind_calendar_migration(connection)
                connection.execute("DROP INDEX user_account_one_operator")
                connection.execute(
                    "DELETE FROM schema_migration WHERE name IN (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "009_harden_migration_history.sql",
                        "010_add_operator_auth_tokens.sql",
                        "011_add_local_password_totp_auth.sql",
                        "012_add_plan_revision.sql",
                        "013_add_notifications.sql",
                        "014_add_personal_calendars.sql",
                        "015_add_absence_replacement_process.sql",
                        "016_claim_notification_deliveries.sql",
                        "017_add_exam_protocols.sql",
                    ),
                )
                connection.execute("DROP TABLE auth_token")
                connection.execute("DROP TABLE auth_recovery_code")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_enabled")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_last_step")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_secret_encrypted")
                connection.execute("ALTER TABLE exam_round DROP COLUMN plan_revision")
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
            for migration in Path("backend/db/migrations").glob("*.sql"):
                shutil.copy(migration, migration_directory / migration.name)
            (migration_directory / "009_harden_migration_history.sql").write_text(
                "BEGIN; ALTER TABLE missing_table ADD COLUMN broken TEXT; COMMIT;",
                encoding="utf-8",
            )
            initialize(db_path, reset=True)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute("DROP TABLE schema_migration_checksum")
                rewind_exam_protocol_migration(connection)
                rewind_notification_migration(connection)
                rewind_calendar_migration(connection)
                connection.execute("DROP INDEX user_account_one_operator")
                connection.execute(
                    "DELETE FROM schema_migration WHERE name IN (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "009_harden_migration_history.sql",
                        "010_add_operator_auth_tokens.sql",
                        "011_add_local_password_totp_auth.sql",
                        "012_add_plan_revision.sql",
                        "013_add_notifications.sql",
                        "014_add_personal_calendars.sql",
                        "015_add_absence_replacement_process.sql",
                        "016_claim_notification_deliveries.sql",
                        "017_add_exam_protocols.sql",
                    ),
                )
                connection.execute("DROP TABLE auth_token")
                connection.execute("DROP TABLE auth_recovery_code")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_enabled")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_last_step")
                connection.execute("ALTER TABLE user_account DROP COLUMN totp_secret_encrypted")
                connection.execute("ALTER TABLE exam_round DROP COLUMN plan_revision")
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
                Path("backend/db/migrations/009_harden_migration_history.sql"),
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
