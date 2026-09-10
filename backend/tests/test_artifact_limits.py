"""Resource ceilings for socket package staging, including SQLite growth."""

import io
import sqlite3
import struct
import unittest
import zipfile
from unittest.mock import patch

from backend.operations.artifact_packages import MAX_PACKAGE_METADATA, ClearArtifactService
from backend.operations.backup_restore import MANIFEST_NAME, ArtifactError, _database_connection
from backend.persistence.artifact_limits import artifact_database_limit
from backend.persistence.database import engine_for
from backend.tests import test_backup_restore as packages


class ArtifactLimitsTests(unittest.TestCase):
    setUp = packages.BackupRestoreTests.setUp
    tearDown = packages.BackupRestoreTests.tearDown
    runtime = packages.BackupRestoreTests.runtime
    prepare_source = packages.BackupRestoreTests.prepare_source
    write_package = packages.BackupRestoreTests.write_package

    def test_bounded_service_roundtrip_and_quota_rejection_cleanup(self):
        paths, source, _ = self.prepare_source()
        package, _ = self.write_package(source, "backup.zip")
        bounded = ClearArtifactService(paths, environment={}, package_limit=32 * 1024 * 1024)
        self.assertEqual("backup", bounded.verify_package(package)["artifact_type"])
        bounded.package_limit = package.stat().st_size - 1
        with self.assertRaises(ArtifactError) as failure:
            bounded.verify_package(package)
        self.assertEqual("artifact_limit_exceeded", failure.exception.code)
        self.assertEqual([], list(paths.backups.glob(".lzug-*")))
        bounded.package_limit = 1
        with self.assertRaises(ArtifactError) as failure:
            bounded.write_backup_package(io.BytesIO(), packages.FINGERPRINT)
        self.assertEqual("artifact_limit_exceeded", failure.exception.code)
        self.assertEqual([], list(paths.backups.glob(".lzug-*")))

    def test_central_directory_budget_checked_before_zipfile_allocation(self):
        paths, _ = self.runtime("source", seed=False)
        service = ClearArtifactService(paths, environment={}, package_limit=16 * 1024 * 1024)
        for name, trailer in (
            ("members", struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 4097, 4097, 1, 0, 0)),
            (
                "directory",
                struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 1, 1, MAX_PACKAGE_METADATA + 1, 0, 0),
            ),
            (
                "zip64",
                b"PK\x06\x07"
                + b"\x00" * 16
                + struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 1, 1, 1, 0, 0),
            ),
        ):
            package = self.root / name
            package.write_bytes(trailer)
            with patch("backend.operations.artifact_packages.zipfile.ZipFile") as open_zip:
                with self.assertRaises(ArtifactError):
                    service.verify_package(package)
                open_zip.assert_not_called()

    def test_oversize_metadata_and_compressed_payload_never_extract(self):
        paths, _ = self.runtime("source", seed=False)
        service = ClearArtifactService(paths, environment={}, package_limit=32 * 1024 * 1024)
        for compression, content in (
            (zipfile.ZIP_DEFLATED, b"compressed"),
            (zipfile.ZIP_STORED, b"x" * (MAX_PACKAGE_METADATA + 1)),
        ):
            package = self.root / "invalid.zip"
            with zipfile.ZipFile(package, "w", compression=compression) as archive:
                archive.writestr(MANIFEST_NAME, content)
            with self.assertRaises(ArtifactError):
                service.verify_package(package)
            self.assertEqual([], list(paths.backups.glob(".lzug-*")))

    def test_cleanup_failure_is_explicit_and_does_not_claim_success(self):
        paths, _ = self.runtime("source", seed=False)
        service = ClearArtifactService(paths, environment={}, package_limit=1024 * 1024)
        root = self.root / "cleanup"
        root.mkdir()
        with patch(
            "backend.operations.artifact_packages.shutil.rmtree",
            side_effect=PermissionError("private-path"),
        ):
            with self.assertRaises(ArtifactError) as failure:
                service._cleanup_workspace(root)
        self.assertEqual("artifact_cleanup_failed", failure.exception.code)
        self.assertEqual("cleanup", failure.exception.phase)
        self.assertNotIn("private-path", str(failure.exception))
        service._cleanup_workspace(root)

    def test_sqlite_limit_covers_raw_and_sqlalchemy_connections_and_is_scoped(self):
        root = self.root / "stage"
        root.mkdir()
        for name, sqlalchemy in (("raw", False), ("orm", True)):
            path = root / (name + ".sqlite")
            with artifact_database_limit(root, 64 * 1024):
                if sqlalchemy:
                    engine = engine_for(path)
                    connection = engine.raw_connection()
                else:
                    engine = None
                    connection = _database_connection(path, read_only=False)
                try:
                    connection.execute("CREATE TABLE content(value BLOB)")
                    with self.assertRaises(sqlite3.DatabaseError):
                        connection.execute("INSERT INTO content VALUES (zeroblob(131072))")
                finally:
                    connection.close()
                    if engine is not None:
                        engine.dispose()
            self.assertLessEqual(path.stat().st_size, 64 * 1024)
        outside = self.root / "outside.sqlite"
        with artifact_database_limit(root, 64 * 1024):
            connection = _database_connection(outside, read_only=False)
            try:
                connection.execute("CREATE TABLE content(value BLOB)")
                connection.execute("INSERT INTO content VALUES (zeroblob(131072))")
                connection.commit()
            finally:
                connection.close()
        self.assertGreater(outside.stat().st_size, 64 * 1024)
