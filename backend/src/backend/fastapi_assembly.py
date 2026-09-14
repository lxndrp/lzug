"""Canonical FastAPI application assembly for product and demo runtimes."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI

from .application import ApplicationServices, ReadApplication
from .application.admin import AdminApplication, AdminServices
from .fastapi_app import (
    FastAPIConfig,
    register_application_routes,
    register_transport_and_errors,
)
from .fastapi_dependencies import BoundedBodyRoute
from .fastapi_http import APPLICATION_ERROR_RESPONSES
from .fastapi_runtime import RuntimeAdmissionMiddleware
from .identity.admin_service import OperatorAuthService
from .identity.committee_admin import CommitteeAdminService
from .integrations.notifications import NotificationService
from .operations.backup_recipients import BackupRecipientRepository
from .operations.backup_restore import ArtifactService
from .operations.diagnostics import run_diagnostics
from .operations.lifecycle import LifecycleService
from .persistence.database import PersistencePaths, database_readiness, persistence_paths
from .planning.plan_consequences import PlanConsequenceService
from .runtime import RuntimeCoordinator
from .security import RequestRateLimiter
from .settings import RuntimeSettings

__all__ = ["FastAPIConfig", "create_admin_application", "create_app"]


def create_admin_application(
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
    """Compose the administrator application for the authoritative backend."""
    active_settings = settings
    if active_settings is None:
        try:
            active_settings = RuntimeSettings.from_environment()
        except ValueError:
            # Diagnostic commands report invalid configuration themselves.
            pass
    resolved_paths = paths or (
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

    services = AdminServices(
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
    return AdminApplication(resolved_paths, services, runtime=runtime)


def create_app(
    config: FastAPIConfig | None = None,
    services: ApplicationServices | None = None,
    *,
    runtime: RuntimeCoordinator | None = None,
) -> FastAPI:
    """Create the single FastAPI application used by product and demo images."""
    resolved = config or FastAPIConfig.from_environment()
    if runtime is not None and runtime.db_path != resolved.db_path.resolve():
        raise ValueError("HTTP and runtime must share persistence")
    application = ReadApplication(resolved.db_path, services)
    if runtime is not None:
        application.runtime = runtime
    app = FastAPI(
        title="lzug API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        responses=APPLICATION_ERROR_RESPONSES,
    )
    app.router.route_class = BoundedBodyRoute
    app.state.lzug_config = resolved
    app.state.runtime = runtime
    app.state.auth_rate_limiter = resolved.auth_rate_limiter or RequestRateLimiter(
        resolved.auth_rate_limit, resolved.auth_rate_window
    )
    app.state.observability_rate_limiter = RequestRateLimiter(30, timedelta(minutes=1))
    app.state.observability_global_rate_limiter = RequestRateLimiter(120, timedelta(minutes=1))
    read_security: dict[str, object] = {}
    write_security: dict[str, object] = {}

    registration = (
        register_transport_and_errors,
        register_application_routes,
    )
    if runtime is not None:
        app.add_middleware(RuntimeAdmissionMiddleware, runtime=runtime)
    for registrar in registration:
        registrar(
            app,
            resolved,
            application,
            read_security,
            write_security,
        )

    return app
