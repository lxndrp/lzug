"""Approved migration, backup binding and recovery in the authoritative process."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.admin import _application
from backend.application.admin import AdminActorContext
from backend.build_metadata import BuildMetadata
from backend.fastapi_assembly import FastAPIConfig, create_app
from backend.identity.local_auth import authentication_key
from backend.operations.artifact_packages import ClearArtifactService
from backend.operations.backup_recipients import BackupRecipientRepository, recipient_fingerprint
from backend.operations.backup_restore import ArtifactError
from backend.operations.lifecycle import LifecycleError, LifecycleService
from backend.persistence.database import database_readiness, initialize, persistence_paths
from backend.runtime import RuntimeConflictError, RuntimeCoordinator
from backend.tests.test_backup_recipients import RECIPIENT

LAST = "028_add_exam_venue_change_notifications.sql"


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.paths = persistence_paths(data_dir=Path(temporary.name) / "data", environment={})
        self.paths.documents.mkdir(parents=True)
        self.paths.backups.mkdir()
        initialize(self.paths.database)
        authentication_key(self.paths.database)
        self.fingerprint = recipient_fingerprint(RECIPIENT)
        BackupRecipientRepository(self.paths.database).set(RECIPIENT, self.fingerprint)
        with closing(sqlite3.connect(self.paths.database)) as db, db:
            db.execute("DELETE FROM schema_migration_checksum WHERE name = ?", (LAST,))
            db.execute("DELETE FROM schema_migration WHERE name = ?", (LAST,))
        self.runtime = RuntimeCoordinator(
            self.paths.database, lambda: database_readiness(self.paths.database)
        )
        self.runtime.start()
        self.addCleanup(self.runtime.stop)
        self.service = LifecycleService(
            self.paths, environment={}, metadata=BuildMetadata.create("a" * 40, "v0.9.0")
        )
        self.artifacts = ClearArtifactService(self.paths, environment={})
        self.job_id = str(uuid4())
        self.plan = self.service.status()["plan_id"]
        self.package = self.paths.backups / "test.zip"

    def backup(self):
        with self.runtime.inspect_storage():
            with self.package.open("wb") as target:
                result = self.artifacts.write_backup_package(target, self.fingerprint)
            digest = hashlib.sha256(self.package.read_bytes()).hexdigest()
            self.service.backup_created(digest, self.fingerprint)
        return result

    def apply(self, **changes):
        arguments = dict(
            plan_id=self.plan,
            fingerprint=self.fingerprint,
            confirm_irreversible=True,
            job_id=self.job_id,
        )
        arguments.update(changes)
        return self.service.apply_package(self.package, self.artifacts, **arguments)

    def assert_unmutated(self):
        self.assertEqual("migration_required", self.runtime.snapshot()["state"])
        self.assertIsNone(self.runtime.snapshot()["job"])
        with self.runtime.inspect_storage():
            self.assertFalse(database_readiness(self.paths.database)["ready"])

    def test_real_backup_migration_and_health_use_one_owner(self):
        before = self.backup()
        config = FastAPIConfig(
            db_path=self.paths.database, session_cookie_name="session", https_only=False
        )
        with TestClient(create_app(config, runtime=self.runtime)) as client:
            self.assertEqual(200, client.get("/api/health").status_code)
            self.assertEqual(503, client.get("/api/ready").status_code)
            result = self.apply()
            self.assertEqual(200, client.get("/api/ready").status_code)
        self.assertEqual([LAST], result["migrations"])
        self.assertEqual(before["artifact_id"], result["backup_artifact_id"])
        self.assertEqual(self.job_id, result["job_id"])
        self.assertEqual("succeeded", result["runtime"]["job"]["status"])
        with self.assertRaises(LifecycleError):
            self.apply()
        self.runtime.stop()
        self.runtime.start()
        self.assertTrue(self.runtime.snapshot()["ready"])
        self.assertEqual(self.job_id, self.runtime.snapshot()["job"]["id"])

    def test_status_is_nonmutating_and_explains_restore_boundary(self):
        with patch(
            "backend.persistence.database.engine_for", side_effect=AssertionError("storage read")
        ):
            status = self.service.status()
        self.assertTrue(status["supported"])
        self.assertEqual("0.9.0", status["application"]["identity"])
        self.assertIn("restore", status["rollback_boundary"])
        self.assertEqual("lzug-admin upgrade apply", status["approval_command"])
        self.assert_unmutated()

    def test_missing_confirmation_or_backup_never_starts_a_job(self):
        with self.assertRaises(LifecycleError) as error:
            self.apply(confirm_irreversible=False)
        self.assertEqual("irreversible_confirmation_required", error.exception.code)
        self.package.write_bytes(b"forged-backup")
        with self.assertRaises(LifecycleError) as error:
            self.apply()
        self.assertEqual("upgrade_backup_invalid", error.exception.code)
        self.assert_unmutated()

    def test_corrupt_backup_wrong_plan_and_wrong_recipient_are_rejected(self):
        self.backup()
        original = self.package.read_bytes()
        for changes in ({"plan_id": "0" * 64}, {"fingerprint": "sha256:" + "0" * 64}):
            with self.subTest(changes=changes), self.assertRaises(LifecycleError):
                self.apply(**changes)
            self.assert_unmutated()
        self.package.write_bytes(original[:-10])
        with self.assertRaises(LifecycleError) as error:
            self.apply()
        self.assertEqual("upgrade_backup_invalid", error.exception.code)
        self.assert_unmutated()

    def test_full_package_verification_is_required_even_with_server_receipt(self):
        self.backup()
        with patch.object(
            self.artifacts,
            "verify_package",
            return_value={
                "source_schema_version": "wrong",
                "pending_migrations": [],
                "readiness": "ready",
            },
        ):
            with self.assertRaises(LifecycleError) as error:
                self.apply()
        self.assertEqual("upgrade_backup_invalid", error.exception.code)
        self.assert_unmutated()

    def test_missing_recipient_and_development_build_fail_closed(self):
        with (
            self.runtime.inspect_storage(),
            closing(sqlite3.connect(self.paths.database)) as db,
            db,
        ):
            db.execute("DELETE FROM backup_recipient")
        with self.runtime.inspect_storage(), self.assertRaises(LifecycleError) as error:
            self.service.recipient()
        self.assertEqual("recipient_not_configured", error.exception.code)
        development = LifecycleService(
            self.paths, environment={}, metadata=BuildMetadata.create("b" * 40)
        )
        self.assertFalse(development.status()["supported"])
        self.assert_unmutated()

    def test_migration_failure_is_secret_free_and_stays_not_ready_after_restart(self):
        self.backup()
        self.service.migration_runner = lambda *_: (_ for _ in ()).throw(
            ValueError("PRIVATE-KEY password secret")
        )
        with self.assertRaises(LifecycleError) as error:
            self.apply()
        self.assertEqual("migration_failed", error.exception.code)
        self.assertNotIn("PRIVATE", str(error.exception))
        self.assertEqual("failed", self.runtime.snapshot()["job"]["status"])
        self.assertEqual("error", self.runtime.snapshot()["state"])
        self.runtime.stop()
        self.runtime.start()
        self.assertEqual("error", self.runtime.snapshot()["state"])
        self.assertEqual(self.job_id, self.runtime.snapshot()["job"]["id"])
        self.assertEqual("interrupted", self.runtime.snapshot()["job"]["status"])
        with self.assertRaises(RuntimeConflictError):
            with self.runtime.admit():
                self.fail("business operation admitted")

    def test_rollback_and_forged_control_approval_never_mutate(self):
        application = _application(paths=self.paths, runtime=self.runtime)
        actor = AdminActorContext("operator", True)
        rollback = application.execute(
            {"version": 1, "command": "rollback", "arguments": {}}, actor
        )
        self.assertEqual(28, rollback.exit_code)
        self.assertIn("container platform", rollback.response["error"]["message"])
        forged = application.execute(
            {
                "version": 1,
                "command": "upgrade",
                "arguments": {"backup": {"verified": True}, "confirm_irreversible": True},
            },
            actor,
        )
        self.assertEqual(20, forged.exit_code)
        self.assert_unmutated()

    def test_restart_discards_backup_receipt(self):
        self.backup()
        self.runtime.stop()
        self.runtime.start()
        self.service = LifecycleService(self.paths, environment={}, metadata=self.service.metadata)
        with self.assertRaises(LifecycleError) as error:
            self.apply()
        self.assertEqual("upgrade_backup_invalid", error.exception.code)
        self.assert_unmutated()

    def test_cleanup_failure_precedes_migration(self):
        self.backup()

        def cleanup():
            raise ArtifactError("artifact_cleanup_failed", "Cleanup failed", phase="cleanup")

        with self.assertRaises(ArtifactError):
            self.apply(release_package=cleanup)
        self.assert_unmutated()

    def test_postcheck_failure_never_becomes_ready(self):
        self.backup()
        self.service.migration_runner = lambda *_: None
        with self.assertRaises(LifecycleError) as error:
            self.apply()
        self.assertEqual("migration_failed", error.exception.code)
        self.assertEqual("error", self.runtime.snapshot()["state"])
        self.assertEqual("failed", self.runtime.snapshot()["job"]["status"])
