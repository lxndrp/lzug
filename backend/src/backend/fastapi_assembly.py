"""Canonical FastAPI application assembly for product and demo runtimes."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import timedelta
from functools import partial
from pathlib import Path

from fastapi import FastAPI

from .application import ApplicationServices, ReadApplication
from .application.admin import AdminApplication, AdminServices
from .application.calendar_ports import CalendarApplicationPort
from .application.consequence_ports import ApplicationConsequenceStoreFactory
from .application.plan_consequences import PlanConsequenceService
from .application.resource_access import ResourceAccessQueryFactory
from .assessment.service import ExamResultService
from .composition import SQLiteAssessmentLifecycleAdapter
from .composition import application_consequence_store as compose_application_consequence_store
from .composition import (
    assessment_unit_of_work_factory as compose_assessment_unit_of_work_factory,
)
from .composition import authentication_repository as compose_authentication_repository
from .composition import authorization_service as compose_authorization_service
from .composition import (
    calendar_lifecycle_work_factory as compose_calendar_lifecycle_work_factory,
)
from .composition import calendar_service as compose_calendar_service
from .composition import (
    candidate_day_service as compose_candidate_day_service,
)
from .composition import committee_admin_service as compose_committee_admin_service
from .composition import (
    exam_lifecycle_unit_of_work_factory as compose_exam_lifecycle_unit_of_work_factory,
)
from .composition import exam_protocol_service as compose_exam_protocol_service
from .composition import exam_result_service as compose_exam_result_service
from .composition import execution_service as compose_execution_service
from .composition import (
    identity_lifecycle_work_factory as compose_identity_lifecycle_work_factory,
)
from .composition import identity_service as compose_identity_service
from .composition import local_auth_service as compose_local_auth_service
from .composition import notification_service as compose_notification_service
from .composition import operator_auth_service as compose_operator_auth_service
from .composition import (
    planning_lifecycle_work_factory as compose_planning_lifecycle_work_factory,
)
from .composition import (
    planning_resource_unit_of_work_factory as compose_planning_resource_unit_of_work_factory,
)
from .composition import planning_service as compose_planning_service
from .execution.exam_protocols import ExamProtocolService
from .execution.slot_service import ExecutionService
from .fastapi_app import (
    FastAPIConfig,
    register_application_routes,
    register_transport_and_errors,
)
from .fastapi_dependencies import (
    BoundedBodyRoute,
    bind_session_cookie,
    reset_session_cookie_binding,
)
from .fastapi_http import APPLICATION_ERROR_RESPONSES
from .fastapi_runtime import RuntimeAdmissionMiddleware
from .identity.admin_service import OperatorAuthService
from .identity.authorization import AuthorizationService
from .identity.committee_admin import CommitteeAdminService
from .identity.people import IdentityService
from .notifications.service import NotificationService
from .operations.backup_recipients import BackupRecipientRepository
from .operations.backup_restore import ArtifactService
from .operations.diagnostics import run_diagnostics
from .operations.lifecycle import LifecycleService
from .persistence.auth import SQLiteAuthenticationRepository
from .persistence.database import PersistencePaths, database_readiness, persistence_paths
from .persistence.resource_access import SQLiteResourceAccessQueryFactory
from .planning import PlanningService
from .planning.candidate_days import CandidateDayService
from .planning.resources import PlanningResourceUnitOfWorkFactory
from .runtime import RuntimeCoordinator
from .security import RequestRateLimiter
from .settings import RuntimeSettings

__all__ = ["FastAPIConfig", "create_admin_application", "create_app", "export_openapi_document"]


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
        operator_auth_factory=lambda db_path: service or compose_operator_auth_service(db_path),
        notification_factory=lambda db_path: (
            notifications or compose_notification_service(db_path, settings=require_settings())
        ),
        committee_factory=lambda db_path: (
            committee_service or compose_committee_admin_service(db_path)
        ),
        consequence_factory=lambda db_path, notification_service: (
            consequences
            or PlanConsequenceService(
                db_path,
                notification_service=notification_service,
                calendar_service=compose_calendar_service(db_path, settings=require_settings()),
                planning_service=compose_planning_service(db_path),
                consequence_store=compose_application_consequence_store(db_path),
            )
        ),
        artifact_factory=lambda persistence: (
            artifacts or ArtifactService(persistence, settings=require_settings())
        ),
        recipient_repository_factory=lambda artifact_service: BackupRecipientRepository(
            artifact_service.paths.database,
            environment=artifact_service.environment,
        ),
        lifecycle_factory=lambda persistence: (
            lifecycle or LifecycleService(persistence, settings=require_settings())
        ),
    )
    return AdminApplication(resolved_paths, services, runtime=runtime)


def create_app(
    config: FastAPIConfig | None = None,
    services: ApplicationServices | None = None,
    *,
    runtime: RuntimeCoordinator | None = None,
    planning_service_factory: Callable[[Path], PlanningService] | None = None,
    execution_service_factory: Callable[[Path], ExecutionService] | None = None,
    exam_protocol_service_factory: Callable[[Path], ExamProtocolService] | None = None,
    candidate_day_service_factory: Callable[[Path], CandidateDayService] | None = None,
    planning_resource_unit_of_work_factory: (
        Callable[[Path], PlanningResourceUnitOfWorkFactory] | None
    ) = None,
    resource_access_query_factory: Callable[[Path], ResourceAccessQueryFactory] | None = None,
    identity_service_factory: Callable[[Path], IdentityService] | None = None,
    authorization_service_factory: Callable[[Path], AuthorizationService] | None = None,
    committee_admin_service_factory: Callable[[Path], CommitteeAdminService] | None = None,
    exam_result_service_factory: Callable[[Path], ExamResultService] | None = None,
    calendar_service_factory: Callable[[Path], CalendarApplicationPort] | None = None,
    consequence_store_factory: ApplicationConsequenceStoreFactory | None = None,
    assessment_lifecycle: object | None = None,
) -> FastAPI:
    """Create the single FastAPI application used by product and demo images."""
    resolved = config or FastAPIConfig.from_environment()
    if runtime is not None and runtime.db_path != resolved.db_path.resolve():
        raise ValueError("HTTP and runtime must share persistence")
    active_authorization_factory = (
        authorization_service_factory
        or (services.authorization_factory if services is not None else None)
        or compose_authorization_service
    )
    application_services = services or ApplicationServices()
    active_authentication_factory = (
        application_services.authentication_factory or compose_authentication_repository
    )
    if application_services.authentication_factory is None:
        application_services = replace(
            application_services, authentication_factory=active_authentication_factory
        )
    if application_services.authorization_factory is None:
        application_services = replace(
            application_services, authorization_factory=active_authorization_factory
        )
    application = ReadApplication(resolved.db_path, application_services)
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
    app.state.planning_service_factory = planning_service_factory or partial(
        compose_planning_service,
        require_confirmed_coordinates=resolved.map_provider.active,
    )
    app.state.execution_service_factory = execution_service_factory or compose_execution_service
    app.state.exam_protocol_service_factory = (
        exam_protocol_service_factory or compose_exam_protocol_service
    )
    app.state.exam_result_service_factory = (
        exam_result_service_factory or compose_exam_result_service
    )
    app.state.exam_lifecycle_unit_of_work_factory = compose_exam_lifecycle_unit_of_work_factory(
        resolved.db_path
    )
    app.state.planning_lifecycle_work_factory = compose_planning_lifecycle_work_factory()
    app.state.identity_lifecycle_work_factory = compose_identity_lifecycle_work_factory()
    app.state.calendar_lifecycle_work_factory = compose_calendar_lifecycle_work_factory()
    app.state.assessment_lifecycle = assessment_lifecycle or SQLiteAssessmentLifecycleAdapter(
        compose_assessment_unit_of_work_factory(resolved.db_path)
    )
    app.state.assessment_round_queries = app.state.assessment_lifecycle
    app.state.candidate_day_service_factory = (
        candidate_day_service_factory or compose_candidate_day_service
    )
    app.state.planning_resource_unit_of_work_factory = (
        planning_resource_unit_of_work_factory
        or partial(
            compose_planning_resource_unit_of_work_factory,
            require_confirmed_coordinates=resolved.map_provider.active,
        )
    )
    app.state.resource_access_query_factory = (
        resource_access_query_factory or SQLiteResourceAccessQueryFactory
    )
    app.state.identity_service_factory = identity_service_factory or compose_identity_service
    app.state.authorization_service_factory = active_authorization_factory
    app.state.authentication_repository_factory = active_authentication_factory
    app.state.committee_admin_service_factory = (
        committee_admin_service_factory or compose_committee_admin_service
    )
    local_authentication_factory = application_services.local_authentication_factory
    if local_authentication_factory is None:

        def local_authentication_factory(db_path, **kwargs):
            authentication = active_authentication_factory(db_path)
            if not isinstance(authentication, SQLiteAuthenticationRepository):
                raise ValueError(
                    "A custom authentication repository must provide a matching "
                    "local-authentication factory"
                )
            return compose_local_auth_service(db_path, **kwargs)

    app.state.local_auth_service_factory = local_authentication_factory
    app.state.calendar_service_factory = calendar_service_factory or partial(
        compose_calendar_service,
        settings=resolved.runtime_settings,
    )
    app.state.consequence_store_factory = consequence_store_factory or partial(
        compose_application_consequence_store
    )
    app.state.notification_service_factory = lambda db_path: compose_notification_service(
        db_path,
        external_delivery_enabled=resolved.runtime_policy.external_notifications_enabled(),
        settings=resolved.runtime_settings,
    )
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
    cookie_binding = bind_session_cookie(resolved.session_cookie_name)
    try:
        for registrar in registration:
            registrar(
                app,
                resolved,
                application,
                read_security,
                write_security,
            )
    finally:
        reset_session_cookie_binding(cookie_binding)

    return app


def export_openapi_document(output: Path, *, profile: str = "publication") -> None:
    """Write the canonical publication or transport OpenAPI document to ``output``."""

    if profile not in {"publication", "transport"}:
        raise ValueError(f"unsupported OpenAPI profile: {profile}")
    transport = profile == "transport"

    document = create_app(
        FastAPIConfig(
            db_path=Path(":memory:"),
            session_cookie_name="lzug_session" if transport else "__Host-lzug_session",
            cookie_secure=not transport,
            https_only=not transport,
        )
    ).openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    """Export the canonical application OpenAPI document for the publication."""

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("output", type=Path, help="destination OpenAPI JSON file")
    parser.add_argument("--profile", choices=("publication", "transport"), default="publication")
    args = parser.parse_args()
    export_openapi_document(args.output, profile=args.profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
