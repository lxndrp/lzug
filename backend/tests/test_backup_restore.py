from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pyotp
from cryptography.fernet import Fernet

from backend.artifact_packages import ClearArtifactService
from backend.artifact_stream import run as run_stream
from backend.auth import AuthenticationRepository
from backend.backup_restore import FULL_EXPORT_SCHEMA, ArtifactError
from backend.database import PersistencePaths, initialize
from backend.document_storage import FilesystemDocumentStorage
from backend.documents import DocumentService
from backend.exam_venues import ExamVenueService
from backend.local_auth import PASSWORD_HASHER, LocalAuthService, authentication_key
from demo.synthetic_fixtures_generated import DEMO_ROLES

PASSWORD = "correct horse battery staple"
TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
FINGERPRINT = "sha256:" + "a" * 64


class NonSeekableOutput(io.BytesIO):
    """Exercise the same write contract as stdout and a container pipe."""

    def seekable(self) -> bool:
        return False

    def seek(self, *_args, **_kwargs):
        raise io.UnsupportedOperation("stream is not seekable")

    def tell(self):
        raise io.UnsupportedOperation("stream position is unavailable")


class BackupRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def runtime(
        self,
        name: str,
        *,
        seed: bool,
        environment: dict[str, str] | None = None,
        fault_injector=None,
    ) -> tuple[PersistencePaths, ClearArtifactService]:
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
        return paths, ClearArtifactService(
            paths,
            environment=environment or {},
            fault_injector=fault_injector,
        )

    def prepare_source(self) -> tuple[PersistencePaths, ClearArtifactService, str]:
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
            connection.commit()
        credentials = AuthenticationRepository(paths.database).create_session(1)
        DocumentService(FilesystemDocumentStorage(paths.documents), paths.database).create(
            b"document-content",
            original_filename="evidence.txt",
            media_type="text/plain",
        )
        return paths, service, credentials.token

    @staticmethod
    def copy_package(source: Path, target: Path) -> None:
        target.write_bytes(source.read_bytes())

    def write_package(
        self,
        service: ClearArtifactService,
        name: str,
        *,
        export: bool = False,
    ) -> tuple[Path, dict[str, object]]:
        target = self.root / name
        with target.open("wb") as output:
            result = (
                service.write_export_package(output, FINGERPRINT)
                if export
                else service.write_backup_package(output, FINGERPRINT)
            )
        return target, result

    def test_backup_package_is_verified_and_removed_after_stream_scope(self) -> None:
        paths, service, _token = self.prepare_source()
        package, result = self.write_package(service, "backup.zip")
        self.assertEqual("backup", result["artifact_type"])
        self.assertEqual(FINGERPRINT, result["recipient_key_fingerprint"])
        with closing(sqlite3.connect(paths.database)) as connection:
            before_verification = connection.execute(
                "SELECT count(*) FROM artifact_operation"
            ).fetchone()[0]
        report = service.verify_package(package, expected_type="backup")
        self.assertEqual(1, report["documents"])
        self.assertEqual(1, report["totp_secrets_verified"])
        with closing(sqlite3.connect(paths.database)) as connection:
            after_verification = connection.execute(
                "SELECT count(*) FROM artifact_operation"
            ).fetchone()[0]
        self.assertEqual(before_verification, after_verification)
        self.assertEqual([], list(paths.backups.glob(".lzug-clear-package-*")))

    def test_export_package_excludes_runtime_secrets(self) -> None:
        _paths, service, _token = self.prepare_source()
        package, result = self.write_package(service, "export.zip", export=True)
        self.assertEqual("full_export", result["artifact_type"])
        service.verify_package(package, expected_type="full_export")
        with zipfile.ZipFile(package) as archive:
            data = archive.read("export/data.json").decode()
            schema = json.loads(archive.read("export/full-export-v1.schema.json"))
        self.assertEqual(FULL_EXPORT_SCHEMA, schema)
        self.assertIn("candidate", json.loads(data)["tables"])
        for forbidden in (
            "user_account",
            "auth_session",
            "auth_token",
            "password_hash",
            "totp_secret_encrypted",
        ):
            self.assertNotIn(forbidden, data)

    def test_exam_venue_data_preserves_identity_in_export_backup_and_restore(self) -> None:
        source_paths, source = self.runtime("venue-source", seed=True)
        venues = ExamVenueService(source_paths.database)
        venue = venues.create_venue(
            {
                "scope": "committee",
                "committee_id": 1,
                "name": "Prüfungszentrum Backup",
                "street": "Archivweg 1",
                "postal_code": "20095",
                "city": "Hamburg",
                "country": "Deutschland",
                "accessibility_status": "confirmed",
                "is_accessible": True,
                "coordinate_status": "missing",
                "is_active": False,
            },
            actor_member_id=1,
        )
        room = venues.create_room(
            venue["id"],
            {"name": "Archivraum", "capacity": 18, "is_active": True},
            actor_member_id=1,
        )
        venue = venues.update_venue(
            venue["id"],
            {"expected_revision": venue["revision"], "is_active": True},
            actor_member_id=1,
        )
        assert venue is not None
        contact = venues.create_contact(
            venue["id"],
            {
                "label": "Hausdienst Backup",
                "email": "hausdienst@example.invalid",
                "room_ids": [room["id"]],
            },
            actor_member_id=1,
        )

        exported, _result = self.write_package(source, "venue-export.zip", export=True)
        with zipfile.ZipFile(exported) as archive:
            export_data = json.loads(archive.read("export/data.json"))

        backup, _result = self.write_package(source, "venue-backup.zip")
        target_paths, target = self.runtime("venue-target", seed=False)
        target.restore_package(
            backup,
            replace=False,
            safety_artifact=None,
            recipient_fingerprint=FINGERPRINT,
        )
        with closing(sqlite3.connect(target_paths.database)) as connection:
            restored = connection.execute(
                "SELECT venue.id, room.id, contact.id, contact_room.room_id "
                "FROM exam_venue AS venue "
                "JOIN exam_room AS room ON room.venue_id = venue.id "
                "JOIN exam_venue_contact AS contact ON contact.venue_id = venue.id "
                "JOIN exam_venue_contact_room AS contact_room "
                "ON contact_room.contact_id = contact.id "
                "WHERE venue.id = ?",
                (venue["id"],),
            ).fetchone()

        self.assertTrue(
            {
                "exam_venue",
                "exam_room",
                "exam_venue_contact",
                "exam_venue_contact_room",
                "exam_venue_audit_event",
                "exam_venue_migration_report",
                "legacy_location_room_mapping",
            }.issubset(export_data["tables"])
        )
        self.assertEqual((venue["id"], room["id"], contact["id"], room["id"]), restored)

    def test_empty_restore_resets_sessions_and_keeps_real_totp_login(self) -> None:
        _source_paths, source, old_session = self.prepare_source()
        target_paths, target = self.runtime("target", seed=False)
        package_copy, _result = self.write_package(source, "backup.zip")

        report = target.restore_package(
            package_copy,
            replace=False,
            safety_artifact=None,
            recipient_fingerprint=FINGERPRINT,
        )

        self.assertEqual("ready", report["readiness"])
        self.assertGreaterEqual(report["reset_security_state"]["sessions"], 1)
        self.assertIsNone(AuthenticationRepository(target_paths.database).authenticate(old_session))
        now = datetime.now(UTC)
        code = pyotp.TOTP(TOTP_SECRET).at(int(now.timestamp()))
        login = LocalAuthService(target_paths.database).login(
            DEMO_ROLES["chair"]["account_email"], PASSWORD, code, now=now
        )
        self.assertEqual(1, login.account_id)

    def test_replacement_requires_external_safety_artifact_evidence(self) -> None:
        _source_paths, source, _token = self.prepare_source()
        _target_paths, target = self.runtime("target", seed=True)
        package_copy, _result = self.write_package(source, "backup.zip")

        with self.assertRaises(ArtifactError) as raised:
            target.restore_package(
                package_copy,
                replace=True,
                safety_artifact=None,
                recipient_fingerprint=FINGERPRINT,
            )
        self.assertEqual("safety_artifact_required", raised.exception.code)

        restored = target.restore_package(
            package_copy,
            replace=True,
            safety_artifact="/operator/pre-restore.lzug",
            recipient_fingerprint=FINGERPRINT,
        )
        self.assertEqual("/operator/pre-restore.lzug", restored["safety_artifact"])

    def test_activation_failure_leaves_existing_target_unchanged(self) -> None:
        _source_paths, source, _token = self.prepare_source()

        def fail(phase: str) -> None:
            if phase == "activation":
                raise RuntimeError("injected")

        target_paths, target = self.runtime("target", seed=True, fault_injector=fail)
        with closing(sqlite3.connect(target_paths.database)) as connection:
            connection.execute("UPDATE candidate SET first_name = 'TargetOnly' WHERE id = 1")
            connection.commit()
        package_copy, _result = self.write_package(source, "backup.zip")

        with self.assertRaises(ArtifactError) as raised:
            target.restore_package(
                package_copy,
                replace=True,
                safety_artifact="/operator/pre-restore.lzug",
                recipient_fingerprint=FINGERPRINT,
            )
        self.assertEqual("activation_failed", raised.exception.code)
        with closing(sqlite3.connect(target_paths.database)) as connection:
            self.assertEqual(
                "TargetOnly",
                connection.execute("SELECT first_name FROM candidate WHERE id = 1").fetchone()[0],
            )

    def test_corrupt_and_wrong_type_packages_are_rejected(self) -> None:
        _paths, service, _token = self.prepare_source()
        package, _result = self.write_package(service, "export.zip", export=True)
        with self.assertRaises(ArtifactError) as wrong_type:
            service.verify_package(package, expected_type="backup")
        self.assertEqual("artifact_type_mismatch", wrong_type.exception.code)

        corrupt = self.root / "corrupt.zip"
        corrupt.write_bytes(b"not-a-package")
        with self.assertRaises(ArtifactError) as invalid:
            service.verify_package(corrupt)
        self.assertEqual("artifact_content_invalid", invalid.exception.code)

    def test_stream_protocol_produces_binary_package_and_secret_free_control(self) -> None:
        paths, _service = self.runtime("stream", seed=True)
        request = (
            json.dumps(
                {
                    "version": 2,
                    "command": "backup-package-create",
                    "arguments": {"recipient_key_fingerprint": FINGERPRINT},
                }
            ).encode()
            + b"\n"
        )
        output = NonSeekableOutput()
        control = io.BytesIO()
        with patch("backend.artifact_stream.persistence_paths", return_value=paths):
            code = run_stream("produce", io.BytesIO(request), output, control)
        self.assertEqual(0, code)
        self.assertTrue(output.getvalue().startswith(b"PK"))
        response = json.loads(control.getvalue())
        self.assertTrue(response["ok"])
        self.assertNotIn("private", control.getvalue().decode())
        self.assertEqual([], list(paths.backups.glob(".lzug-clear-package-*")))

    def test_insufficient_space_aborts_without_cleartext_residue(self) -> None:
        paths, service, _token = self.prepare_source()
        usage = __import__("shutil").disk_usage(paths.backups)
        with patch(
            "backend.backup_restore.shutil.disk_usage",
            return_value=usage._replace(free=0),
        ):
            with self.assertRaises(ArtifactError) as raised:
                service.write_backup_package(io.BytesIO(), FINGERPRINT)
        self.assertEqual("insufficient_storage", raised.exception.code)
        self.assertEqual([], list(paths.backups.glob(".lzug-*")))


if __name__ == "__main__":
    unittest.main()
