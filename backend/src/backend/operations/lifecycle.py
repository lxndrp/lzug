"""Operator-approved data transitions in the already running backend process."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from backend.build_metadata import BuildMetadata
from backend.operations.artifact_packages import ClearArtifactService
from backend.operations.backup_recipients import BackupRecipientRepository
from backend.operations.backup_restore import MIN_SUPPORTED_SCHEMA
from backend.persistence.database import (
    PersistencePaths,
    apply_migrations,
    migration_status,
    persistence_paths,
)
from backend.runtime import Operation, RuntimeCoordinator, runtime_for
from backend.settings import RuntimeSettings
from backend.version import build_metadata

ROLLBACK_BOUNDARY = (
    "No reverse migration is supported. Image replacement belongs to the container platform. "
    "After a data migration, use a complete verified backup with a compatible image for restore, "
    "or a supported forward recovery. An image rollback alone does not restore data."
)


class LifecycleError(RuntimeError):
    """Secret-free lifecycle failure with a stable protocol class and phase."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        phase: str = "precheck",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.phase, self.details = code, phase, dict(details or {})


class LifecycleService:
    """Approve migration using server-owned build, schema and backup evidence.

    The socket keeps one instance for serialized artifact exchanges. Its bounded
    backup receipt is created only after a complete download and consumed once.
    A restart discards it, so an old approval can never replay a mutation.
    """

    def __init__(
        self,
        paths: PersistencePaths | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        settings: RuntimeSettings | None = None,
        metadata: BuildMetadata | None = None,
        migration_runner: Callable[[Path, Path | None], None] = apply_migrations,
    ) -> None:
        self.paths = paths or persistence_paths(
            settings=settings.persistence if settings else None,
            environment=environment,
        )
        self.environment = (
            environment
            if environment is not None
            else (settings or RuntimeSettings.from_environment()).environment_values()
        )
        self.metadata = metadata or build_metadata()
        self.migration_runner = migration_runner
        self._backup: tuple[str, str, str] | None = None

    def _runtime(self) -> RuntimeCoordinator:
        runtime = runtime_for(self.paths.database)
        if runtime is None:
            raise LifecycleError(
                "maintenance_required", "Use the authoritative backend admin socket"
            )
        return runtime

    def status(self) -> dict[str, Any]:
        """Inspect cached schema and running build without accessing persistence."""
        runtime = self._runtime().diagnosis()
        migration = runtime.get("migration")
        plan = {"application": json.loads(self.metadata.to_json()), "migration": migration}
        plan_id = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        supported = (
            runtime["state"] == "migration_required"
            and self.metadata.release
            and isinstance(migration, dict)
            and isinstance(migration.get("current"), str)
            and migration["current"] >= MIN_SUPPORTED_SCHEMA
            and bool(migration.get("pending"))
        )
        return {
            **plan,
            "plan_id": plan_id,
            "runtime": runtime,
            "supported": supported,
            "backup_required": True,
            "confirmation_required": True,
            "rollback_boundary": ROLLBACK_BOUNDARY,
            "approval_command": "lzug-admin upgrade apply",
        }

    def _plan(self, plan_id: str | None = None) -> dict[str, Any]:
        status = self.status()
        if not status["supported"] or (plan_id is not None and plan_id != status["plan_id"]):
            raise LifecycleError(
                "schema_incompatible", "No supported pending migration matches this approval"
            )
        return status

    def recipient(self) -> dict[str, str]:
        """Read the configured recipient without migrating legacy configuration."""
        current = BackupRecipientRepository(
            self.paths.database, environment=self.environment
        ).inspect()
        if current is None:
            raise LifecycleError(
                "recipient_not_configured", "Configure a backup recipient before the image change"
            )
        return current

    def backup_created(self, digest: str, fingerprint: str) -> None:
        """Bind the exact generated package to this process and pending plan."""
        plan = self._plan()
        if self.recipient()["fingerprint"] != fingerprint:
            raise LifecycleError("recipient_key_mismatch", "Backup recipient does not match")
        self._backup = (plan["plan_id"], digest, fingerprint)

    def apply_package(
        self,
        package: Path,
        artifacts: ClearArtifactService,
        *,
        plan_id: str,
        fingerprint: str,
        confirm_irreversible: bool,
        job_id: str,
        release_package: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Verify authenticated backup EOF before entering the central migration lease."""
        if not confirm_irreversible:
            raise LifecycleError(
                "irreversible_confirmation_required",
                "Explicit irreversible-migration approval is required",
            )
        runtime = self._runtime()
        with runtime.inspect_storage():
            plan = self._plan(plan_id)
            with package.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if self._backup != (plan_id, digest, fingerprint):
                raise LifecycleError(
                    "upgrade_backup_invalid",
                    "Backup must be created and decrypted for this running instance",
                    phase="backup_verify",
                )
            if self.recipient()["fingerprint"] != fingerprint:
                raise LifecycleError("recipient_key_mismatch", "Backup recipient changed")
            backup = artifacts.verify_package(package, expected_type="backup")
            before = plan["migration"]
            if (
                backup["source_schema_version"] != before["current"]
                or backup["pending_migrations"] != before["pending"]
                or backup["readiness"] == "not_ready"
            ):
                raise LifecycleError(
                    "upgrade_backup_invalid",
                    "Backup is incompatible with this transition",
                    phase="backup_verify",
                )
            # Remove staged plaintext before any irreversible transition. The
            # socket retains no package that could fail cleanup after ready.
            if release_package is not None:
                release_package()
        # Consume before mutation, including failures. The socket ID is also
        # the durable runtime job ID, observable after disconnect and restart.
        self._backup = None
        try:
            with runtime.operation(Operation.MIGRATION, job_id=job_id):
                current = migration_status(self.paths.database)
                if any(
                    current.get(key) != before.get(key)
                    for key in ("state", "current", "target", "pending")
                ):
                    raise LifecycleError(
                        "schema_incompatible", "Schema changed after backup verification"
                    )
                self.migration_runner(self.paths.database, self.paths.backups)
        except Exception:
            raise LifecycleError(
                "migration_failed",
                "Migration failed; inspect the runtime job and restore boundary",
                phase="migration",
                details={"job_id": job_id, "backup_artifact_id": backup["artifact_id"]},
            ) from None
        return {
            "operation": "upgrade",
            "application": plan["application"],
            "source_schema_version": before["current"],
            "target_schema_version": before["target"],
            "migrations": before["pending"],
            "backup_artifact_id": backup["artifact_id"],
            "job_id": job_id,
            "runtime": runtime.diagnosis(),
            "rollback_boundary": ROLLBACK_BOUNDARY,
        }

    def rollback(self) -> dict[str, Any]:
        """Reject automatic reverse migration or container rollback explicitly."""
        raise LifecycleError("rollback_not_supported", ROLLBACK_BOUNDARY)
