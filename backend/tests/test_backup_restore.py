from __future__ import annotations

import hashlib
import io
import json
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing, redirect_stdout
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pyotp
from cryptography.fernet import Fernet
from sqlalchemy import text

from backend.admin import EXIT_RECIPIENT_KEY, run
from backend.admin_service import OperatorAuthService
from backend.auth import AuthenticationRepository
from backend.backup_restore import (
    ARTIFACT_MAGIC,
    BACKUP_PUBLIC_KEY_ENV,
    FULL_EXPORT_SCHEMA,
    ArtifactError,
    ArtifactService,
    _available_migrations,
    _database_record_count,
    _parse_private_key,
    _parse_public_key,
    _read_header,
    _sha256,
    _totp_key_binding,
    generate_recipient_keypair,
)
from backend.database import PersistencePaths, initialize, session_scope
from backend.document_storage import FilesystemDocumentStorage
from backend.documents import DocumentService
from backend.local_auth import (
    PASSWORD_HASHER,
    LocalAuthService,
    authentication_key,
)

PASSWORD = "correct horse battery staple"
TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


class BackupRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.public_key, self.private_key = generate_recipient_keypair()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def runtime(
        self,
        name: str,
        *,
        seed: bool,
        environment: dict[str, str] | None = None,
        fault_injector=None,
    ) -> tuple[PersistencePaths, ArtifactService]:
        data = self.root / name
        paths = PersistencePaths(
            data_dir=data,
            database=data / "lzug.sqlite",
            documents=data / "documents",
            backups=data / "backups",
        )
        paths.documents.mkdir(parents=True)
        paths.backups.mkdir(parents=True)
        initialize(paths.database, with_seed=seed, reset=True, backup_dir=paths.backups)
        values = {BACKUP_PUBLIC_KEY_ENV: self.public_key}
        values.update(environment or {})
        return paths, ArtifactService(
            paths,
            environment=values,
            fault_injector=fault_injector,
        )

    def prepare_source(self) -> tuple[PersistencePaths, ArtifactService, str]:
        paths, service = self.runtime("source", seed=True)
        key = authentication_key(paths.database)
        encrypted = Fernet(key).encrypt(TOTP_SECRET.encode("ascii")).decode("ascii")
        with closing(sqlite3.connect(paths.database)) as connection:
            connection.execute(
                "UPDATE user_account SET password_hash = ?, passkey_enabled = 1, "
                "totp_secret_encrypted = ?, totp_enabled = 1 WHERE id = 1",
                (PASSWORD_HASHER.hash(PASSWORD), encrypted),
            )
            connection.execute(
                "INSERT INTO auth_token (account_id, kind, token_hash, expires_at) "
                "VALUES (1, 'recovery', ?, ?)",
                (
                    hashlib.sha256(b"pending-recovery-secret").hexdigest(),
                    (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                ),
            )
            connection.execute(
                "INSERT INTO auth_recovery_code (account_id, code_hash) VALUES (1, ?)",
                (PASSWORD_HASHER.hash("RECOVERY1"),),
            )
            connection.execute(
                "INSERT INTO calendar_feed (person_id, token_hash) VALUES (1, ?)",
                (hashlib.sha256(b"calendar-feed-secret").hexdigest(),),
            )
            connection.execute(
                "INSERT INTO push_subscription (person_id, endpoint) VALUES (1, ?)",
                ("https://push.example.invalid/secret-endpoint",),
            )
            connection.execute(
                "INSERT INTO notification (committee_id, exam_round_id, recipient_member_id, "
                "event_type, origin_key, title, message, action_path) "
                "VALUES (1, 1, 1, 'synthetic_test', 'backup-test', 'Title', 'Message', '/')"
            )
            notification_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
            connection.execute(
                "INSERT INTO notification_delivery (notification_id, channel, target_key, status, "
                "claim_token, claimed_at, claim_expires_at) VALUES (?, 'email', 'target', "
                "'pending', 'claim-secret', ?, ?)",
                (
                    notification_id,
                    datetime.now(UTC).isoformat(),
                    (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                ),
            )
            connection.commit()
        credentials = AuthenticationRepository(paths.database).create_session(1)
        DocumentService(FilesystemDocumentStorage(paths.documents), paths.database).create(
            b"document-content",
            original_filename="evidence.txt",
            media_type="text/plain",
        )
        return paths, service, credentials.token

    def copy_artifact(
        self, source_paths: PersistencePaths, target_paths: PersistencePaths, name: str
    ) -> None:
        shutil.copy2(source_paths.backups / name, target_paths.backups / name)

    def rewrite_backup(
        self,
        paths: PersistencePaths,
        service: ArtifactService,
        artifact_name: str,
        mutate,
        *,
        omit: set[str] | None = None,
        valid_database: bool = True,
    ) -> str:
        private_key = _parse_private_key(self.private_key)
        with service._loaded_artifact(paths.backups / artifact_name, private_key) as loaded:
            manifest = deepcopy(loaded.manifest)
            manifest["artifact_id"] = str(uuid4())
            mutate(loaded.root / "payload/database.sqlite", manifest)
            omitted = omit or set()
            manifest["contents"] = [
                entry for entry in manifest["contents"] if entry["path"] not in omitted
            ]
            entries = {entry["path"]: loaded.root / entry["path"] for entry in manifest["contents"]}
            for entry in manifest["contents"]:
                source = entries[entry["path"]]
                entry["size_bytes"] = source.stat().st_size
                entry["checksum_sha256"] = _sha256(source)
            if valid_database:
                database = loaded.root / "payload/database.sqlite"
                key = (loaded.root / "payload/keys/key-1.bin").read_bytes()
                manifest["counts"]["database_records"] = _database_record_count(database)
                manifest["authentication_key_binding"] = _totp_key_binding(database, key)
            replacement = service._publish_package(
                "fixture",
                manifest["artifact_id"],
                manifest,
                entries,
                _parse_public_key(self.public_key),
            )
        return replacement.name

    def test_backup_has_minimal_preamble_and_non_mutating_verification(self) -> None:
        paths, service, _token = self.prepare_source()
        backup = service.create_backup()
        artifact = paths.backups / backup["artifact"]
        protected = artifact.read_bytes()

        self.assertTrue(protected.startswith(ARTIFACT_MAGIC))
        self.assertNotIn(b"evidence.txt", protected)
        self.assertNotIn(TOTP_SECRET.encode(), protected)
        with artifact.open("rb") as source:
            header, _frame = _read_header(source)
        self.assertEqual(
            {
                "format",
                "format_version",
                "protection",
                "recipient_key_fingerprint",
                "ephemeral_public_key",
                "nonce",
                "tag_length",
            },
            set(header),
        )

        before = hashlib.sha256(paths.database.read_bytes()).hexdigest()
        report = service.verify(backup["artifact"], self.private_key)
        after = hashlib.sha256(paths.database.read_bytes()).hexdigest()

        self.assertEqual(before, after)
        self.assertEqual("backup", report["artifact_type"])
        self.assertEqual(1, report["documents"])
        self.assertEqual(1, report["totp_secrets_verified"])

    def test_backup_of_previous_release_schema_is_verified_before_upgrade(self) -> None:
        paths, service = self.runtime("previous-release", seed=False)
        authentication_key(paths.database)
        with closing(sqlite3.connect(paths.database)) as connection:
            connection.execute("DROP TABLE artifact_operation")
            connection.execute("DROP TABLE instance_metadata")
            connection.execute(
                "DELETE FROM schema_migration_checksum WHERE name = ?",
                ("024_add_artifact_operations.sql",),
            )
            connection.execute(
                "DELETE FROM schema_migration WHERE name = ?",
                ("024_add_artifact_operations.sql",),
            )
            connection.commit()

        backup = service.create_backup()
        report = service.verify(backup["artifact"], self.private_key)

        self.assertEqual("023_add_exam_round_lifecycle.sql", report["source_schema_version"])
        self.assertEqual(["024_add_artifact_operations.sql"], report["pending_migrations"])
        self.assertEqual("backup", report["artifact_type"])

    def test_wrong_key_and_ciphertext_tampering_are_rejected(self) -> None:
        paths, service, _token = self.prepare_source()
        backup = service.create_backup()
        _other_public, other_private = generate_recipient_keypair()
        with self.assertRaises(ArtifactError) as mismatch:
            service.verify(backup["artifact"], other_private)
        self.assertEqual("recipient_key_mismatch", mismatch.exception.code)

        original = paths.backups / backup["artifact"]
        tampered_name = "tampered.lzug"
        tampered = bytearray(original.read_bytes())
        tampered[len(tampered) // 2] ^= 1
        (paths.backups / tampered_name).write_bytes(tampered)
        with self.assertRaises(ArtifactError) as integrity:
            service.verify(tampered_name, self.private_key)
        self.assertIn(
            integrity.exception.code,
            {"artifact_integrity_failed", "artifact_content_invalid"},
        )

    def test_verification_detects_protected_content_corruption(self) -> None:
        paths, service, _token = self.prepare_source()
        backup = service.create_backup()
        document_name = next(
            f"payload/documents/{entry.name}" for entry in paths.documents.iterdir()
        )
        missing_document = self.rewrite_backup(
            paths,
            service,
            backup["artifact"],
            lambda _database, _manifest: None,
            omit={document_name},
        )
        with self.assertRaises(ArtifactError) as missing:
            service.verify(missing_document, self.private_key)
        self.assertEqual("artifact_content_invalid", missing.exception.code)

        def corrupt_database(database: Path, _manifest: dict) -> None:
            database.write_bytes(b"not a sqlite database")

        corrupt = self.rewrite_backup(
            paths,
            service,
            backup["artifact"],
            corrupt_database,
            valid_database=False,
        )
        with self.assertRaises(ArtifactError) as invalid:
            service.verify(corrupt, self.private_key)
        self.assertEqual("schema_incompatible", invalid.exception.code)

    def test_missing_and_orphan_documents_abort_without_publishing(self) -> None:
        paths, service, _token = self.prepare_source()
        document = next(paths.documents.iterdir())
        document.unlink()
        with self.assertRaises(ArtifactError) as missing:
            service.create_backup()
        self.assertEqual("document_relation_failed", missing.exception.code)
        self.assertEqual([], [path for path in paths.backups.glob("backup-*.lzug")])

        document.write_bytes(b"document-content")
        (paths.documents / ("f" * 32)).write_bytes(b"orphan")
        with self.assertRaises(ArtifactError) as orphan:
            service.create_full_export(self.public_key)
        self.assertEqual("document_relation_failed", orphan.exception.code)

    def test_full_export_is_protected_open_and_excludes_all_system_secrets(self) -> None:
        paths, service, _token = self.prepare_source()
        exported = service.create_full_export(self.public_key)
        service.verify(exported["artifact"], self.private_key)

        private_key = _parse_private_key(self.private_key)
        with service._loaded_artifact(paths.backups / exported["artifact"], private_key) as loaded:
            data = (loaded.root / "export/data.json").read_text(encoding="utf-8")
            documents = json.loads(
                (loaded.root / "export/documents.json").read_text(encoding="utf-8")
            )
            self.assertIn("candidate", json.loads(data)["tables"])
            for forbidden in (
                "user_account",
                "auth_session",
                "auth_token",
                "push_subscription",
                "calendar_feed",
                "notification_delivery",
                "password_hash",
                "totp_secret_encrypted",
                "claim-secret",
                "secret-endpoint",
            ):
                self.assertNotIn(forbidden, data)
            self.assertEqual("evidence.txt", documents["documents"][0]["original_filename"])
            self.assertTrue((loaded.root / "export/full-export-v1.schema.json").is_file())
            repository_schema = json.loads(
                (
                    Path(__file__).parents[2]
                    / "docs/developers/reference/full-export-v1.schema.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(FULL_EXPORT_SCHEMA, repository_schema)

    def test_empty_restore_resets_short_lived_state_and_supports_real_totp_login(self) -> None:
        source_paths, source, old_session = self.prepare_source()
        backup = source.create_backup()
        target_paths, target = self.runtime("target", seed=False)
        self.copy_artifact(source_paths, target_paths, backup["artifact"])

        report = target.restore(backup["artifact"], self.private_key)

        self.assertEqual("ready", report["readiness"])
        self.assertGreaterEqual(report["reset_security_state"]["sessions"], 1)
        with closing(sqlite3.connect(target_paths.database)) as connection:
            self.assertEqual(
                0, connection.execute("SELECT count(*) FROM auth_session").fetchone()[0]
            )
            self.assertEqual(0, connection.execute("SELECT count(*) FROM auth_token").fetchone()[0])
            self.assertEqual(
                0, connection.execute("SELECT count(*) FROM auth_recovery_code").fetchone()[0]
            )
            self.assertEqual(
                1, connection.execute("SELECT count(*) FROM calendar_feed").fetchone()[0]
            )
            self.assertEqual(
                1, connection.execute("SELECT count(*) FROM push_subscription").fetchone()[0]
            )
            claim = connection.execute("SELECT claim_token FROM notification_delivery").fetchone()[
                0
            ]
            passkey = connection.execute(
                "SELECT passkey_enabled FROM user_account WHERE id = 1"
            ).fetchone()[0]
        self.assertIsNone(claim)
        self.assertEqual(1, passkey)
        self.assertIsNone(AuthenticationRepository(target_paths.database).authenticate(old_session))

        now = datetime.now(UTC)
        code = pyotp.TOTP(TOTP_SECRET).at(int(now.timestamp()))
        login = LocalAuthService(target_paths.database).login(
            "demo.alpha@example.invalid",
            PASSWORD,
            code,
            now=now,
        )
        self.assertEqual(1, login.account_id)

    def test_replace_mode_rolls_back_activation_failure(self) -> None:
        source_paths, source, _token = self.prepare_source()
        backup = source.create_backup()

        def fail_activation(phase: str) -> None:
            if phase == "activation":
                raise RuntimeError("injected")

        target_paths, target = self.runtime("target", seed=True, fault_injector=fail_activation)
        with closing(sqlite3.connect(target_paths.database)) as connection:
            connection.execute("UPDATE candidate SET first_name = 'TargetOnly' WHERE id = 1")
            connection.commit()
        self.copy_artifact(source_paths, target_paths, backup["artifact"])

        with self.assertRaises(ArtifactError) as failure:
            target.restore(backup["artifact"], self.private_key, replace=True)

        self.assertEqual("activation_failed", failure.exception.code)
        with closing(sqlite3.connect(target_paths.database)) as connection:
            self.assertEqual(
                "TargetOnly",
                connection.execute("SELECT first_name FROM candidate WHERE id = 1").fetchone()[0],
            )
        safety = list(target_paths.backups.glob("pre-restore-*.lzug"))
        self.assertEqual(1, len(safety))

    def test_replace_mode_keeps_a_protected_safety_artifact(self) -> None:
        source_paths, source, _token = self.prepare_source()
        backup = source.create_backup()
        target_paths, target = self.runtime("target", seed=True)
        self.copy_artifact(source_paths, target_paths, backup["artifact"])

        report = target.restore(backup["artifact"], self.private_key, replace=True)

        self.assertIsNotNone(report["safety_artifact"])
        safety = target_paths.backups / report["safety_artifact"]
        self.assertTrue(safety.read_bytes().startswith(ARTIFACT_MAGIC))
        target.verify(safety.name, self.private_key)

    def test_restore_failure_in_each_phase_leaves_target_unchanged(self) -> None:
        source_paths, source, _token = self.prepare_source()
        backup = source.create_backup()

        for phase in (
            "precheck",
            "prepared_restore",
            "migration",
            "postcheck",
            "activation",
        ):
            with self.subTest(phase=phase):

                def fail(current: str, expected: str = phase) -> None:
                    if current == expected:
                        raise RuntimeError("injected")

                target_paths, target = self.runtime(
                    f"target-{phase}", seed=True, fault_injector=fail
                )
                with closing(sqlite3.connect(target_paths.database)) as connection:
                    connection.execute(
                        "UPDATE candidate SET first_name = 'TargetOnly' WHERE id = 1"
                    )
                    connection.commit()
                self.copy_artifact(source_paths, target_paths, backup["artifact"])

                with self.assertRaises(ArtifactError) as failure:
                    target.restore(backup["artifact"], self.private_key, replace=True)

                self.assertEqual(phase, failure.exception.phase)
                with closing(sqlite3.connect(target_paths.database)) as connection:
                    self.assertEqual(
                        "TargetOnly",
                        connection.execute(
                            "SELECT first_name FROM candidate WHERE id = 1"
                        ).fetchone()[0],
                    )

    def test_supported_forward_migration_and_schema_boundaries(self) -> None:
        source_paths, source, _token = self.prepare_source()
        backup = source.create_backup()
        current = _available_migrations()[-1]
        previous = _available_migrations()[-2]

        def make_previous(database: Path, manifest: dict) -> None:
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("DROP TABLE artifact_operation")
                connection.execute("DROP TABLE instance_metadata")
                connection.execute(
                    "DELETE FROM schema_migration_checksum WHERE name = ?", (current,)
                )
                connection.execute("DELETE FROM schema_migration WHERE name = ?", (current,))
                connection.commit()
            manifest["schema_version"] = previous

        older = self.rewrite_backup(source_paths, source, backup["artifact"], make_previous)
        target_paths, target = self.runtime("migration-target", seed=False)
        self.copy_artifact(source_paths, target_paths, older)
        migrated = target.restore(older, self.private_key)
        self.assertEqual([current], migrated["migrations"])
        self.assertEqual(current, migrated["target_schema_version"])

        def make_newer(database: Path, manifest: dict) -> None:
            name = "999_future_schema.sql"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("INSERT INTO schema_migration (name) VALUES (?)", (name,))
                connection.commit()
            manifest["schema_version"] = name

        newer = self.rewrite_backup(source_paths, source, backup["artifact"], make_newer)
        with self.assertRaises(ArtifactError) as future:
            source.verify(newer, self.private_key)
        self.assertEqual("source_newer", future.exception.code)

        def make_unsupported(database: Path, manifest: dict) -> None:
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "DELETE FROM schema_migration WHERE CAST(substr(name, 1, 3) AS INTEGER) > 8"
                )
                connection.commit()
            manifest["schema_version"] = "008_add_authentication_sessions.sql"

        unsupported = self.rewrite_backup(
            source_paths, source, backup["artifact"], make_unsupported
        )
        with self.assertRaises(ArtifactError) as obsolete:
            source.verify(unsupported, self.private_key)
        self.assertEqual("source_unsupported", obsolete.exception.code)

    def test_restore_reports_required_and_optional_configuration(self) -> None:
        source_paths, source = self.runtime(
            "configured-source",
            seed=True,
            environment={
                "LZUG_REQUIRED_EXTERNAL_CONFIG": "LZUG_OIDC_CLIENT_SECRET",
                "LZUG_OIDC_CLIENT_SECRET": "source-only-secret",
                "LZUG_SMTP_HOST": "smtp.example.invalid",
            },
        )
        backup = source.create_backup()

        missing_paths, missing = self.runtime(
            "missing-config",
            seed=False,
            environment={"LZUG_REQUIRED_EXTERNAL_CONFIG": "LZUG_OIDC_CLIENT_SECRET"},
        )
        self.copy_artifact(source_paths, missing_paths, backup["artifact"])
        not_ready = missing.restore(backup["artifact"], self.private_key)
        self.assertEqual("not_ready", not_ready["readiness"])
        self.assertEqual(
            ["LZUG_OIDC_CLIENT_SECRET"],
            not_ready["configuration"]["missing_required"],
        )

        restricted_paths, restricted = self.runtime(
            "restricted-config",
            seed=False,
            environment={
                "LZUG_REQUIRED_EXTERNAL_CONFIG": "LZUG_OIDC_CLIENT_SECRET",
                "LZUG_OIDC_CLIENT_SECRET": "replacement-secret",
            },
        )
        self.copy_artifact(source_paths, restricted_paths, backup["artifact"])
        limited = restricted.restore(backup["artifact"], self.private_key)
        self.assertEqual("restricted", limited["readiness"])
        self.assertEqual(["email"], limited["configuration"]["restricted_channels"])

    def test_interrupted_publication_cleans_up_and_can_restart(self) -> None:
        paths, service, _token = self.prepare_source()
        with patch(
            "backend.backup_restore._encrypt_file",
            side_effect=ArtifactError("artifact_write_failed", "injected"),
        ):
            with self.assertRaises(ArtifactError):
                service.create_backup()
        self.assertEqual([], list(paths.backups.glob("backup-*.lzug")))
        self.assertEqual([], list(paths.backups.glob(".lzug-*")))

        created = service.create_backup()
        self.assertEqual(
            "backup", service.verify(created["artifact"], self.private_key)["artifact_type"]
        )

    def test_large_document_is_streamed_through_backup_and_verification(self) -> None:
        paths, service = self.runtime("large-document", seed=True)
        content = b"large-document-block" * 300_000
        DocumentService(FilesystemDocumentStorage(paths.documents), paths.database).create(
            content,
            original_filename="large-evidence.bin",
            media_type="text/plain",
        )

        backup = service.create_backup()
        report = service.verify(backup["artifact"], self.private_key)

        self.assertEqual(1, report["documents"])
        self.assertGreater((paths.backups / backup["artifact"]).stat().st_size, len(content))

    def test_snapshot_waits_for_a_running_write_and_contains_the_commit(self) -> None:
        paths, service, _token = self.prepare_source()
        inserted = threading.Event()
        release = threading.Event()
        completed = threading.Event()
        failures: list[Exception] = []

        def writer() -> None:
            try:
                with session_scope(paths.database) as session:
                    session.execute(
                        text(
                            "INSERT INTO candidate (first_name, last_name, ihk_exam_number, "
                            "specialization, training_company) VALUES "
                            "('Concurrent', 'Writer', 'CONCURRENT-1', "
                            "'application_development', 'Test')"
                        )
                    )
                    inserted.set()
                    release.wait(5)
            except Exception as error:
                failures.append(error)

        result: dict[str, object] = {}

        def backup() -> None:
            try:
                result.update(service.create_backup())
            except Exception as error:
                failures.append(error)
            finally:
                completed.set()

        writer_thread = threading.Thread(target=writer)
        writer_thread.start()
        if not inserted.wait(15):
            self.fail(f"Writer did not reach its transaction: {failures!r}")
        backup_thread = threading.Thread(target=backup)
        backup_thread.start()
        time.sleep(0.2)
        self.assertFalse(completed.is_set())
        release.set()
        writer_thread.join(5)
        backup_thread.join(10)

        self.assertEqual([], failures)
        self.assertTrue(completed.is_set())
        private_key = _parse_private_key(self.private_key)
        with service._loaded_artifact(
            paths.backups / str(result["artifact"]), private_key
        ) as loaded:
            with closing(sqlite3.connect(loaded.root / "payload/database.sqlite")) as connection:
                self.assertEqual(
                    1,
                    connection.execute(
                        "SELECT count(*) FROM candidate WHERE ihk_exam_number = 'CONCURRENT-1'"
                    ).fetchone()[0],
                )

    def test_insufficient_space_and_admin_private_key_leak_contract(self) -> None:
        paths, service, _token = self.prepare_source()
        usage = shutil.disk_usage(paths.backups)
        with patch(
            "backend.backup_restore.shutil.disk_usage",
            return_value=usage._replace(free=0),
        ):
            with self.assertRaises(ArtifactError) as storage:
                service.create_backup()
        self.assertEqual("insufficient_storage", storage.exception.code)

        backup = service.create_backup()
        _other_public, wrong_private = generate_recipient_keypair()
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(
                json.dumps(
                    {
                        "version": 1,
                        "command": "artifact-verify",
                        "arguments": {
                            "artifact": backup["artifact"],
                            "recipient_private_key": wrong_private,
                        },
                    }
                ).encode(),
                service=OperatorAuthService(paths.database),
                artifacts=service,
            )
        stdout.flush()
        self.assertEqual(EXIT_RECIPIENT_KEY, code)
        response = json.loads(output.getvalue())
        self.assertEqual("precheck", response["error"]["phase"])
        self.assertNotIn(wrong_private, output.getvalue().decode())


if __name__ == "__main__":
    unittest.main()
