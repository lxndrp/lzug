"""Compatibility stdin/stdout adapter for the administrator application core."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO

from backend.application.admin import _EXIT_CODES as _EXIT_CODES
from backend.application.admin import (
    EXIT_ARTIFACT_INVALID,
    EXIT_ARTIFACT_OPERATION,
    EXIT_AUTHORIZATION,
    EXIT_CONFLICT,
    EXIT_INCOMPATIBLE,
    EXIT_INSUFFICIENT_STORAGE,
    EXIT_INTERNAL,
    EXIT_INVALID_REQUEST,
    EXIT_NOT_FOUND,
    EXIT_NOT_READY,
    EXIT_OK,
    EXIT_PERSISTENCE,
    EXIT_RECIPIENT_KEY,
    EXIT_REPLACE_REQUIRED,
    EXIT_TOKEN_INVALID,
    MAX_REQUEST_BYTES,
    PROTOCOL_VERSION,
    AdminActorContext,
    AdminApplication,
    AdminApplicationResult,
    AdminServices,
    invalid_protocol_result,
)
from backend.application.admin import _response as _structured_response
from backend.identity.admin_service import OperatorAuthService
from backend.identity.committee_admin import CommitteeAdminService
from backend.integrations.notifications import NotificationService
from backend.operations.backup_recipients import BackupRecipientRepository
from backend.operations.backup_restore import ArtifactService
from backend.operations.diagnostics import run_diagnostics
from backend.operations.lifecycle import LifecycleService
from backend.persistence.database import (
    PersistencePaths,
    database_readiness,
    persistence_paths,
)
from backend.planning.plan_consequences import PlanConsequenceService
from backend.runtime import RuntimeCoordinator
from backend.settings import RuntimeSettings

__all__ = [
    "EXIT_ARTIFACT_INVALID",
    "EXIT_ARTIFACT_OPERATION",
    "EXIT_AUTHORIZATION",
    "EXIT_CONFLICT",
    "EXIT_INCOMPATIBLE",
    "EXIT_INSUFFICIENT_STORAGE",
    "EXIT_INTERNAL",
    "EXIT_INVALID_REQUEST",
    "EXIT_NOT_FOUND",
    "EXIT_NOT_READY",
    "EXIT_OK",
    "EXIT_PERSISTENCE",
    "EXIT_RECIPIENT_KEY",
    "EXIT_REPLACE_REQUIRED",
    "EXIT_TOKEN_INVALID",
    "run",
]

LOCAL_PROCESS_ACTOR = AdminActorContext(
    technical_identity="container-exec",
    is_authorized=True,
)


def _application(
    *,
    service: OperatorAuthService | None = None,
    notifications: NotificationService | None = None,
    committee_service: CommitteeAdminService | None = None,
    consequences: PlanConsequenceService | None = None,
    artifacts: ArtifactService | None = None,
    lifecycle: LifecycleService | None = None,
    settings: RuntimeSettings | None = None,
    paths: PersistencePaths | None = None,
    runtime: RuntimeCoordinator | None = None,
) -> AdminApplication:
    active_settings = settings
    if active_settings is None:
        try:
            active_settings = RuntimeSettings.from_environment()
        except ValueError:
            # Diagnostic commands own their safe invalid-configuration reporting.
            # Other commands trigger the same error again through their factories.
            pass
    paths = paths or (
        persistence_paths(settings=active_settings.persistence)
        if active_settings is not None
        else PersistencePaths()
    )

    def require_settings() -> RuntimeSettings:
        return active_settings or RuntimeSettings.from_environment()

    def ready(db_path: Path) -> Mapping[str, object]:
        if service is not None:
            return {"ready": True}
        require_settings()
        return database_readiness(db_path)

    configured_services = AdminServices(
        diagnostics=lambda command, client: run_diagnostics(command, client),
        readiness_probe=ready,
        operator_auth_factory=lambda db_path: service or OperatorAuthService(db_path),
        notification_factory=lambda db_path: notifications
        or NotificationService(db_path, settings=require_settings()),
        committee_factory=lambda db_path: committee_service
        or CommitteeAdminService(Path(service.db_path) if service is not None else db_path),
        consequence_factory=lambda db_path, notification_service: consequences
        or PlanConsequenceService(db_path, notification_service),
        artifact_factory=lambda persistence: artifacts
        or ArtifactService(persistence, settings=require_settings()),
        recipient_repository_factory=lambda artifact_service: BackupRecipientRepository(
            artifact_service.paths.database,
            environment=artifact_service.environment,
        ),
        lifecycle_factory=lambda persistence: lifecycle
        or LifecycleService(persistence, settings=require_settings()),
    )
    return AdminApplication(paths, configured_services, runtime=runtime)


def _write(result: AdminApplicationResult, output: BinaryIO) -> int:
    output.write(result.encode())
    output.flush()
    return result.exit_code


def _response(
    *,
    ok: bool,
    result: Any = None,
    error: dict[str, Any] | None = None,
) -> bytes:
    """Encode the shared response contract for the legacy stream adapter."""
    return AdminApplicationResult(
        _structured_response(ok=ok, result=result, error=error),
        EXIT_OK,
    ).encode()


def run(
    payload: bytes,
    *,
    actor: AdminActorContext = LOCAL_PROCESS_ACTOR,
    output: BinaryIO | None = None,
    service: OperatorAuthService | None = None,
    notifications: NotificationService | None = None,
    committee_service: CommitteeAdminService | None = None,
    consequences: PlanConsequenceService | None = None,
    artifacts: ArtifactService | None = None,
    lifecycle: LifecycleService | None = None,
    settings: RuntimeSettings | None = None,
) -> int:
    """Adapt one legacy byte-stream request to the transport-neutral core."""
    application = _application(
        service=service,
        notifications=notifications,
        committee_service=committee_service,
        consequences=consequences,
        artifacts=artifacts,
        lifecycle=lifecycle,
        settings=settings,
    )
    result = application.handle(payload, actor)
    return _write(result, output or sys.stdout.buffer)


def main(
    *,
    argv: list[str] | None = None,
    source: BinaryIO | None = None,
    output: BinaryIO | None = None,
) -> int:
    """Read one legacy request without reflecting it to output or logs."""
    destination = output or sys.stdout.buffer
    if (argv if argv is not None else sys.argv[1:]) != [
        "--protocol",
        str(PROTOCOL_VERSION),
    ]:
        return _write(invalid_protocol_result(), destination)
    payload = (source or sys.stdin.buffer).read(MAX_REQUEST_BYTES + 1)
    return run(payload, output=destination)


if __name__ == "__main__":
    raise SystemExit(main())
