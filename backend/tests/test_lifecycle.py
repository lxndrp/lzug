from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend.admin import EXIT_INCOMPATIBLE, EXIT_OK, EXIT_REPLACE_REQUIRED, run
from backend.build_metadata import BuildMetadata
from backend.database import PersistencePaths
from backend.lifecycle import MAINTENANCE_ENV, LifecycleError, LifecycleService


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = PersistencePaths(
            data_dir=root,
            database=root / "lzug.sqlite",
            documents=root / "documents",
            backups=root / "backups",
        )
        self.paths.documents.mkdir()
        self.paths.backups.mkdir()
        self.metadata = BuildMetadata.create("a" * 40, "v0.7.0")
        self.target = {
            "identity": "0.7.0",
            "image": "ghcr.io/lxndrp/lzug@sha256:" + "c" * 64,
            "release": True,
            "revision": "a" * 40,
            "tag": "v0.7.0",
        }
        self.events: list[str] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def service(self, migration_runner=None) -> LifecycleService:
        return LifecycleService(
            self.paths,
            environment={MAINTENANCE_ENV: "true"},
            metadata=self.metadata,
            migration_runner=migration_runner or self.record_migration,
            maintenance_probe=lambda: True,
        )

    def record_migration(self, _database: Path, _backups: Path | None) -> None:
        self.events.append("migration")

    @staticmethod
    def before(*, pending: bool = True) -> dict[str, object]:
        migrations = ["026_add_backup_recipient.sql"] if pending else []
        return {
            "state": "migration_required" if pending else "ready",
            "current": "024_add_artifact_operations.sql",
            "target": "026_add_backup_recipient.sql",
            "pending": migrations,
            "history": [],
        }

    @staticmethod
    def ready() -> dict[str, object]:
        return {
            "ready": True,
            "reason": "ready",
            "migration": {
                "state": "ready",
                "current": "026_add_backup_recipient.sql",
                "target": "026_add_backup_recipient.sql",
                "pending": [],
            },
        }

    def evidence(self, **changes) -> dict[str, object]:
        evidence: dict[str, object] = {
            "artifact": "/operator/pre-upgrade.lzug",
            "artifact_id": "artifact-id",
            "artifact_type": "backup",
            "snapshot_at": "2026-09-02T10:00:00+00:00",
            "recipient_key_fingerprint": "sha256:" + "b" * 64,
            "protection": "age-x25519-v1",
            "verified": True,
            "source_schema_version": "024_add_artifact_operations.sql",
            "pending_migrations": ["026_add_backup_recipient.sql"],
            "readiness": "ready",
        }
        evidence.update(changes)
        return evidence

    def test_supported_upgrade_requires_verified_evidence_before_migration(self) -> None:
        with (
            patch("backend.lifecycle.migration_status", return_value=self.before()),
            patch("backend.lifecycle.database_readiness", return_value=self.ready()),
        ):
            result = self.service().upgrade(
                self.target,
                self.evidence(),
                confirm_irreversible=True,
            )
        self.assertEqual(["migration"], self.events)
        self.assertTrue(result["backup"]["verified"])
        self.assertEqual(["026_add_backup_recipient.sql"], result["migrations"])
        self.assertNotIn("private", json.dumps(result))

    def test_confirmation_precedes_migration(self) -> None:
        with patch("backend.lifecycle.migration_status", return_value=self.before()):
            with self.assertRaises(LifecycleError) as raised:
                self.service().upgrade(
                    self.target,
                    self.evidence(),
                    confirm_irreversible=False,
                )
        self.assertEqual("irreversible_confirmation_required", raised.exception.code)
        self.assertEqual([], self.events)

    def test_unsuitable_backup_evidence_aborts_before_migration(self) -> None:
        for changes in (
            {"verified": False},
            {"protection": "legacy"},
            {"artifact_type": "full_export"},
            {"pending_migrations": []},
            {"readiness": "not_ready"},
        ):
            with self.subTest(changes=changes):
                with patch("backend.lifecycle.migration_status", return_value=self.before()):
                    with self.assertRaises(LifecycleError) as raised:
                        self.service().upgrade(
                            self.target,
                            self.evidence(**changes),
                            confirm_irreversible=True,
                        )
                self.assertEqual("upgrade_backup_invalid", raised.exception.code)
                self.assertEqual([], self.events)

    def test_migration_failure_returns_only_secret_free_backup_evidence(self) -> None:
        def fail(_database: Path, _backups: Path | None) -> None:
            raise RuntimeError("secret database failure")

        with patch("backend.lifecycle.migration_status", return_value=self.before()):
            with self.assertRaises(LifecycleError) as raised:
                self.service(fail).upgrade(
                    self.target,
                    self.evidence(),
                    confirm_irreversible=True,
                )
        self.assertEqual("migration_failed", raised.exception.code)
        self.assertEqual("/operator/pre-upgrade.lzug", raised.exception.details["backup_artifact"])
        self.assertNotIn("secret database failure", str(raised.exception))

    def test_release_and_maintenance_prechecks_remain_fail_closed(self) -> None:
        service = LifecycleService(
            self.paths,
            environment={},
            metadata=self.metadata,
            maintenance_probe=lambda: True,
        )
        with self.assertRaises(LifecycleError) as raised:
            service.rollback(self.target)
        self.assertEqual("maintenance_required", raised.exception.code)

        with self.assertRaises(LifecycleError) as raised:
            self.service().rollback({**self.target, "image": "lzug:latest"})
        self.assertEqual("release_artifact_unverified", raised.exception.code)

    def test_compatible_rollback_is_non_mutating(self) -> None:
        with patch(
            "backend.lifecycle.migration_status",
            return_value={**self.before(pending=False), "state": "ready"},
        ):
            result = self.service().rollback(self.target)
        self.assertFalse(result["mutated"])

    def test_admin_protocol_accepts_only_secret_free_upgrade_evidence(self) -> None:
        class ProtocolLifecycle:
            def upgrade(self, target, backup, *, confirm_irreversible):
                self.target = target
                self.backup = backup
                self.confirm = confirm_irreversible
                return {"operation": "upgrade"}

            def rollback(self, target):
                raise LifecycleError("rollback_not_supported", "Rollback is not supported")

        lifecycle = ProtocolLifecycle()
        request = {
            "version": 1,
            "command": "upgrade",
            "arguments": {
                "target": self.target,
                "backup": self.evidence(),
                "confirm_irreversible": True,
            },
        }
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(json.dumps(request).encode(), lifecycle=lifecycle)
        stdout.flush()
        self.assertEqual(EXIT_OK, code)
        self.assertEqual(self.evidence(), lifecycle.backup)
        self.assertNotIn("identity", json.dumps(lifecycle.backup))

        request["arguments"]["recipient_private_key"] = "forbidden-secret"
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(json.dumps(request).encode(), lifecycle=lifecycle)
        stdout.flush()
        self.assertEqual(20, code)
        self.assertNotIn("forbidden-secret", output.getvalue().decode())

        request = {
            "version": 1,
            "command": "rollback",
            "arguments": {"target": self.target},
        }
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(json.dumps(request).encode(), lifecycle=lifecycle)
        self.assertEqual(EXIT_INCOMPATIBLE, code)

    def test_admin_protocol_maps_irreversible_confirmation(self) -> None:
        class ConfirmationLifecycle:
            def upgrade(self, target, backup, *, confirm_irreversible):
                raise LifecycleError("irreversible_confirmation_required", "Confirmation required")

        request = {
            "version": 1,
            "command": "upgrade",
            "arguments": {
                "target": self.target,
                "backup": self.evidence(),
                "confirm_irreversible": False,
            },
        }
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(json.dumps(request).encode(), lifecycle=ConfirmationLifecycle())
        self.assertEqual(EXIT_REPLACE_REQUIRED, code)


if __name__ == "__main__":
    unittest.main()
