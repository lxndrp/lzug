"""Release-bound upgrade and rollback orchestration for the local admin protocol."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .backup_restore import ArtifactService
from .build_metadata import BuildMetadata
from .database import (
    PersistencePaths,
    apply_migrations,
    database_readiness,
    migration_status,
    persistence_paths,
)
from .version import build_metadata

MAINTENANCE_ENV = "LZUG_LIFECYCLE_MAINTENANCE"
_CANONICAL_IMAGE = re.compile(r"^ghcr\.io/lxndrp/lzug@sha256:[0-9a-f]{64}$")


def _dedicated_maintenance_process() -> bool:
    process_entries = False
    for command_path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            command = command_path.read_bytes().split(b"\0")
        except OSError:
            continue
        process_entries = True
        if b"backend.server" in command:
            return False
    return process_entries


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
        self.code = code
        self.phase = phase
        self.details = dict(details or {})


class LifecycleService:
    """Coordinate existing release, backup, and migration contracts."""

    def __init__(
        self,
        paths: PersistencePaths | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        artifacts: ArtifactService | None = None,
        metadata: BuildMetadata | None = None,
        migration_runner: Callable[[Path, Path | None], None] = apply_migrations,
        maintenance_probe: Callable[[], bool] = _dedicated_maintenance_process,
    ) -> None:
        self.paths = paths or persistence_paths()
        self.environment = environment if environment is not None else os.environ
        self.artifacts = artifacts or ArtifactService(self.paths, environment=self.environment)
        self.metadata = metadata or build_metadata()
        self.migration_runner = migration_runner
        self.maintenance_probe = maintenance_probe

    def upgrade(
        self,
        target: Mapping[str, Any],
        recipient_private_key: str,
        *,
        confirm_irreversible: bool,
    ) -> dict[str, Any]:
        release = self._release_precheck(target)
        before = migration_status(self.paths.database)
        if before["state"] not in {"ready", "migration_required"}:
            raise LifecycleError(
                "schema_incompatible",
                "Database schema is not compatible with the target release",
            )
        pending = before.get("pending")
        if not isinstance(pending, list):
            raise LifecycleError("schema_incompatible", "Migration plan is unavailable")
        if pending and not confirm_irreversible:
            raise LifecycleError(
                "irreversible_confirmation_required",
                "Pending migrations require explicit irreversible-step confirmation",
            )

        backup = self.artifacts.create_backup()
        verification = self.artifacts.verify(str(backup.get("artifact", "")), recipient_private_key)
        self._verified_upgrade_backup(verification, before)

        if pending:
            try:
                self.migration_runner(self.paths.database, self.paths.backups)
            except Exception as error:
                raise LifecycleError(
                    "migration_failed",
                    "Target migrations failed; the target runtime must not be started",
                    phase="migration",
                    details=self._backup_details(backup, before),
                ) from error

        after = database_readiness(self.paths.database)
        if after.get("ready") is not True:
            raise LifecycleError(
                "migration_failed",
                "Post-upgrade schema verification failed; the target runtime must not be started",
                phase="postcheck",
                details=self._backup_details(backup, before),
            )
        migration = after.get("migration")
        target_schema = migration.get("target") if isinstance(migration, Mapping) else None
        return {
            "operation": "upgrade",
            "target": release,
            "source_schema_version": before.get("current"),
            "target_schema_version": target_schema,
            "migrations": pending,
            "irreversible": bool(pending),
            "backup": {
                "artifact": backup["artifact"],
                "artifact_id": backup["artifact_id"],
                "snapshot_at": backup["snapshot_at"],
                "recipient_key_fingerprint": backup["recipient_key_fingerprint"],
                "verified": True,
            },
            "phases": ["release_precheck", "schema_precheck", "backup", "backup_verify"]
            + (["migration"] if pending else [])
            + ["postcheck"],
        }

    def rollback(self, target: Mapping[str, Any]) -> dict[str, Any]:
        release = self._release_precheck(target)
        status = migration_status(self.paths.database)
        if status.get("state") != "ready":
            raise LifecycleError(
                "rollback_not_supported",
                "Database schema is not directly compatible with the rollback release",
            )
        return {
            "operation": "rollback",
            "target": release,
            "schema_version": status.get("current"),
            "mutated": False,
            "phases": ["release_precheck", "schema_precheck", "approved"],
        }

    def _release_precheck(self, target: Mapping[str, Any]) -> dict[str, str]:
        if (
            self.environment.get(MAINTENANCE_ENV, "").strip().lower() != "true"
            or not self.maintenance_probe()
        ):
            raise LifecycleError(
                "maintenance_required",
                f"{MAINTENANCE_ENV} must be true in a dedicated maintenance container",
            )
        if set(target) != {"identity", "image", "release", "revision", "tag"}:
            raise LifecycleError(
                "release_artifact_unverified", "Target release metadata is invalid"
            )
        try:
            candidate = BuildMetadata.create(str(target.get("revision")), target.get("tag"))
        except (TypeError, ValueError) as error:
            raise LifecycleError(
                "release_artifact_unverified", "Target release metadata is invalid"
            ) from error
        image = target.get("image")
        if (
            not candidate.release
            or target.get("release") is not True
            or target.get("identity") != candidate.identity
            or not isinstance(image, str)
            or _CANONICAL_IMAGE.fullmatch(image) is None
            or candidate != self.metadata
        ):
            raise LifecycleError(
                "release_artifact_unverified",
                "Target container is not the matching canonical release artifact",
            )
        return {
            "identity": candidate.identity,
            "image": image,
            "revision": candidate.revision,
            "tag": candidate.tag or "",
        }

    @staticmethod
    def _verified_upgrade_backup(
        verification: Mapping[str, Any], before: Mapping[str, Any]
    ) -> None:
        pending = before.get("pending")
        if (
            verification.get("artifact_type") != "backup"
            or verification.get("source_schema_version") != before.get("current")
            or verification.get("pending_migrations") != pending
            or verification.get("readiness") == "not_ready"
        ):
            raise LifecycleError(
                "upgrade_backup_invalid",
                "Verified backup is not suitable for this instance and target release",
                phase="backup_verify",
            )

    @staticmethod
    def _backup_details(backup: Mapping[str, Any], before: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "backup_artifact": backup.get("artifact"),
            "backup_artifact_id": backup.get("artifact_id"),
            "source_schema_version": before.get("current"),
            "target_schema_version": before.get("target"),
        }
