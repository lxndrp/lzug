from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend.admin import EXIT_INCOMPATIBLE, EXIT_OK, EXIT_REPLACE_REQUIRED, run
from backend.backup_restore import ArtifactError
from backend.build_metadata import BuildMetadata
from backend.database import PersistencePaths
from backend.lifecycle import MAINTENANCE_ENV, LifecycleError, LifecycleService


class FakeArtifacts:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.create_error: Exception | None = None
        self.verify_error: Exception | None = None
        self.verification = {
            "artifact_type": "backup",
            "source_schema_version": "023_add_exam_round_lifecycle.sql",
            "pending_migrations": ["024_add_artifact_operations.sql"],
            "readiness": "ready",
        }

    def create_backup(self) -> dict[str, str]:
        self.events.append("backup")
        if self.create_error is not None:
            raise self.create_error
        return {
            "artifact": "backup-contract.lzug",
            "artifact_id": "artifact-id",
            "snapshot_at": "2026-08-30T20:00:00+00:00",
            "recipient_key_fingerprint": "sha256:" + "b" * 64,
        }

    def verify(self, artifact: str, private_key: str) -> dict[str, object]:
        self.events.append("verify")
        if artifact != "backup-contract.lzug" or private_key != "private-key-marker":
            raise AssertionError("unexpected verification arguments")
        if self.verify_error is not None:
            raise self.verify_error
        return dict(self.verification)


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
        self.metadata = BuildMetadata.create("a" * 40, "v0.6.0")
        self.target = {
            "identity": "0.6.0",
            "image": "ghcr.io/lxndrp/lzug@sha256:" + "c" * 64,
            "release": True,
            "revision": "a" * 40,
            "tag": "v0.6.0",
        }
        self.events: list[str] = []
        self.artifacts = FakeArtifacts(self.events)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def record_migration(self, _database: Path, _backups: Path | None) -> None:
        self.events.append("migration")

    def service(self, migration_runner=None) -> LifecycleService:
        return LifecycleService(
            self.paths,
            environment={MAINTENANCE_ENV: "true"},
            artifacts=self.artifacts,
            metadata=self.metadata,
            migration_runner=migration_runner or self.record_migration,
            maintenance_probe=lambda: True,
        )

    @staticmethod
    def before(*, pending: bool = True) -> dict[str, object]:
        migrations = ["024_add_artifact_operations.sql"] if pending else []
        return {
            "state": "migration_required" if pending else "ready",
            "current": "023_add_exam_round_lifecycle.sql",
            "target": "024_add_artifact_operations.sql",
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
                "current": "024_add_artifact_operations.sql",
                "target": "024_add_artifact_operations.sql",
                "pending": [],
            },
        }

    def test_supported_upgrade_verifies_backup_before_migration(self) -> None:
        with (
            patch("backend.lifecycle.migration_status", return_value=self.before()),
            patch("backend.lifecycle.database_readiness", return_value=self.ready()),
        ):
            result = self.service().upgrade(
                self.target,
                "private-key-marker",
                confirm_irreversible=True,
            )

        self.assertEqual(["backup", "verify", "migration"], self.events)
        self.assertTrue(result["backup"]["verified"])
        self.assertEqual(["024_add_artifact_operations.sql"], result["migrations"])
        self.assertEqual("0.6.0", result["target"]["identity"])

    def test_confirmation_is_required_before_irreversible_work(self) -> None:
        with patch("backend.lifecycle.migration_status", return_value=self.before()):
            with self.assertRaises(LifecycleError) as raised:
                self.service().upgrade(
                    self.target,
                    "private-key-marker",
                    confirm_irreversible=False,
                )
        self.assertEqual("irreversible_confirmation_required", raised.exception.code)
        self.assertEqual([], self.events)

    def test_missing_wrong_and_damaged_backup_abort_before_migration(self) -> None:
        failures = (
            ("create_error", ArtifactError("recipient_key_invalid", "Recipient key is invalid")),
            (
                "verify_error",
                ArtifactError("recipient_key_mismatch", "Recipient private key does not match"),
            ),
            (
                "verify_error",
                ArtifactError("artifact_integrity_failed", "Artifact integrity validation failed"),
            ),
        )
        for attribute, failure in failures:
            with self.subTest(code=failure.code):
                self.events.clear()
                self.artifacts.create_error = None
                self.artifacts.verify_error = None
                setattr(self.artifacts, attribute, failure)
                with patch("backend.lifecycle.migration_status", return_value=self.before()):
                    with self.assertRaises(ArtifactError) as raised:
                        self.service().upgrade(
                            self.target,
                            "private-key-marker",
                            confirm_irreversible=True,
                        )
                self.assertEqual(failure.code, raised.exception.code)
                self.assertNotIn("migration", self.events)

    def test_unsuitable_verified_backup_aborts_before_migration(self) -> None:
        self.artifacts.verification["pending_migrations"] = []
        with patch("backend.lifecycle.migration_status", return_value=self.before()):
            with self.assertRaises(LifecycleError) as raised:
                self.service().upgrade(
                    self.target,
                    "private-key-marker",
                    confirm_irreversible=True,
                )
        self.assertEqual("upgrade_backup_invalid", raised.exception.code)
        self.assertEqual(["backup", "verify"], self.events)

    def test_migration_failure_reports_verified_backup_and_stops(self) -> None:
        def fail(_database: Path, _backups: Path | None) -> None:
            self.events.append("migration")
            raise RuntimeError("secret database failure")

        with patch("backend.lifecycle.migration_status", return_value=self.before()):
            with self.assertRaises(LifecycleError) as raised:
                self.service(fail).upgrade(
                    self.target,
                    "private-key-marker",
                    confirm_irreversible=True,
                )
        self.assertEqual("migration_failed", raised.exception.code)
        self.assertEqual("migration", raised.exception.phase)
        self.assertEqual("backup-contract.lzug", raised.exception.details["backup_artifact"])
        self.assertNotIn("secret database failure", str(raised.exception))

    def test_release_and_maintenance_prechecks_fail_before_backup(self) -> None:
        for environment, target in (
            ({}, self.target),
            ({MAINTENANCE_ENV: "true"}, {**self.target, "image": "lzug:latest"}),
            (
                {MAINTENANCE_ENV: "true"},
                {**self.target, "revision": "d" * 40},
            ),
        ):
            with self.subTest(target=target):
                service = LifecycleService(
                    self.paths,
                    environment=environment,
                    artifacts=self.artifacts,
                    metadata=self.metadata,
                    maintenance_probe=lambda: True,
                )
                with self.assertRaises(LifecycleError):
                    service.rollback(target)
        live_server = LifecycleService(
            self.paths,
            environment={MAINTENANCE_ENV: "true"},
            artifacts=self.artifacts,
            metadata=self.metadata,
            maintenance_probe=lambda: False,
        )
        with self.assertRaises(LifecycleError) as raised:
            live_server.rollback(self.target)
        self.assertEqual("maintenance_required", raised.exception.code)
        self.assertEqual([], self.events)

    def test_compatible_rollback_is_non_mutating_and_newer_schema_is_rejected(self) -> None:
        with patch(
            "backend.lifecycle.migration_status",
            return_value={
                **self.before(pending=False),
                "current": "024_add_artifact_operations.sql",
            },
        ):
            allowed = self.service().rollback(self.target)
        self.assertFalse(allowed["mutated"])
        self.assertEqual([], self.events)

        with patch(
            "backend.lifecycle.migration_status",
            return_value={**self.before(), "state": "migration_error", "pending": []},
        ):
            with self.assertRaises(LifecycleError) as raised:
                self.service().rollback(self.target)
        self.assertEqual("rollback_not_supported", raised.exception.code)
        self.assertEqual([], self.events)

    def test_admin_protocol_preserves_json_and_exit_codes(self) -> None:
        class ProtocolLifecycle:
            def upgrade(self, target, key, *, confirm_irreversible):
                self.target = target
                self.key = key
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
                "recipient_private_key": "private-key-marker",
                "confirm_irreversible": True,
            },
        }
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(json.dumps(request).encode(), lifecycle=lifecycle)
        self.assertEqual(EXIT_OK, code)
        self.assertEqual("private-key-marker", lifecycle.key)
        self.assertNotIn("private-key-marker", output.getvalue().decode())

        request["command"] = "rollback"
        request["arguments"] = {"target": self.target}
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(json.dumps(request).encode(), lifecycle=lifecycle)
        self.assertEqual(EXIT_INCOMPATIBLE, code)
        payload = json.loads(output.getvalue())
        self.assertEqual("rollback_not_supported", payload["error"]["class"])

    def test_admin_protocol_maps_irreversible_confirmation(self) -> None:
        class ConfirmationLifecycle:
            def upgrade(self, target, key, *, confirm_irreversible):
                raise LifecycleError("irreversible_confirmation_required", "Confirmation required")

        request = {
            "version": 1,
            "command": "upgrade",
            "arguments": {
                "target": self.target,
                "recipient_private_key": "private-key-marker",
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
