"""FastAPI route handlers and shared transport registrations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from html import escape
from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import Response
from sqlalchemy.exc import SQLAlchemyError

from backend.application.transport import (
    RequestTooLargeError,
    UnsupportedMediaTypeError,
)
from backend.assessment.exam_results import ExamResultConflictError
from backend.execution.exam_day_closures import ExamDayConflictError, ExamDayValidationError
from backend.execution.exam_protocols import ExamProtocolConflictError
from backend.execution.exam_round_lifecycle import ExamRoundConflictError, ExamRoundValidationError
from backend.identity.local_auth import LocalAuthError
from backend.integrations.map_provider import (
    MapProviderConfig,
    MapProviderDisabledError,
    MapProviderUnavailableError,
)
from backend.persistence.database import persistence_paths
from backend.planning import ConfirmedPlanConflictError, PlanConflictError, PlanValidationError
from backend.planning.exam_venues import (
    ExamVenueConfirmationRequiredError,
    ExamVenueConflictError,
    ExamVenueInUseError,
)

from .api_contracts import (
    ApiRootResponse,
    AssessmentModelBindingRequest,
    CalendarEventCollectionResponse,
    CalendarFeedActivationRequest,
    CalendarFeedActivationResponse,
    CalendarFeedRevocationResponse,
    CalendarStatusResponse,
    ConfirmedPlanChangeRequest,
    DemoScenarioOverviewResponse,
    DemoScenarioResetResponse,
    DomainCollectionResponse,
    DomainResourceResponse,
    DomainResourceWrite,
    ErrorResponse,
    ExamAttendanceUpdateRequest,
    ExamProtocolContentRequest,
    ExamProtocolResponseRequest,
    ExamRoomCreateRequest,
    ExamRoomResponse,
    ExamRoomUpdateRequest,
    ExamSlotStartRequest,
    ExamSlotStatusUpdateRequest,
    ExamVenueCollectionResponse,
    ExamVenueContactCreateRequest,
    ExamVenueContactResponse,
    ExamVenueContactUpdateRequest,
    ExamVenueCreateRequest,
    ExamVenueDuplicateCheckRequest,
    ExamVenueGeocodeRequest,
    ExamVenueGeocodeResponse,
    ExamVenuePromotionDecisionRequest,
    ExamVenuePromotionRequest,
    ExamVenueResponse,
    ExamVenueUpdateRequest,
    FactorActivationRequest,
    FrontendErrorRequest,
    HealthResponse,
    IndividualAssessmentRequest,
    LegacyLocationCollectionResponse,
    LegacyLocationResponse,
    LoginRequest,
    NotificationChannelsResponse,
    NotificationCollectionResponse,
    PlanningProposalAssignmentPayload,
    PlanningProposalDayPayload,
    PlanningProposalResponse,
    PlanningProposalResultResponse,
    PlanningProposalSlotPayload,
    PlanningProposalWriteRequest,
    PlanningRoundRequest,
    PushConfirmationResponse,
    PushSubscriptionRequest,
    PushSubscriptionResponse,
    RevisionDeleteRequest,
    SessionResponse,
    SessionRotationResponse,
    TokenRequest,
)
from .application import (
    ApplicationResult,
    ApplicationServices,
    AuthenticationRequiredError,
    ForbiddenRequestError,
    database_error_result,
)
from .fastapi_assessment import create_assessment_router
from .fastapi_dependencies import (
    ReadContext,
    WriteContext,
    validate_body_headers,
)
from .fastapi_execution import create_execution_router
from .fastapi_http import finish as _finish
from .fastapi_http import json_response as _json_response
from .fastapi_http import not_found as _not_found
from .fastapi_http import plain_text as _plain_text
from .fastapi_http import same_origin as _same_origin
from .fastapi_master_data import MIGRATED_DOMAIN_RESOURCES as MIGRATED_DOMAIN_RESOURCES
from .fastapi_master_data import register_master_data_routes
from .fastapi_planning_router import register_planning_router
from .observability import emit_event, safe_http_path
from .runtime_policy import ProductRuntimePolicy, RuntimePolicy
from .security import RequestRateLimiter, RuntimeSecurityConfig
from .settings import RuntimeSettings

__all__ = [
    "ApiRootResponse",
    "AssessmentModelBindingRequest",
    "CalendarEventCollectionResponse",
    "CalendarFeedActivationRequest",
    "CalendarFeedActivationResponse",
    "CalendarFeedRevocationResponse",
    "CalendarStatusResponse",
    "DemoScenarioOverviewResponse",
    "DemoScenarioResetResponse",
    "DomainCollectionResponse",
    "DomainResourceResponse",
    "DomainResourceWrite",
    "ErrorResponse",
    "ExamAttendanceUpdateRequest",
    "ExamProtocolContentRequest",
    "ExamProtocolResponseRequest",
    "ExamRoomCreateRequest",
    "ExamRoomResponse",
    "ExamRoomUpdateRequest",
    "ExamVenueCollectionResponse",
    "ExamVenueContactCreateRequest",
    "ExamVenueContactResponse",
    "ExamVenueContactUpdateRequest",
    "ExamVenueCreateRequest",
    "ExamVenueDuplicateCheckRequest",
    "ExamVenueGeocodeRequest",
    "ExamVenueGeocodeResponse",
    "ExamVenuePromotionDecisionRequest",
    "ExamVenuePromotionRequest",
    "ExamVenueResponse",
    "ExamVenueUpdateRequest",
    "FactorActivationRequest",
    "FrontendErrorRequest",
    "HealthResponse",
    "IndividualAssessmentRequest",
    "LegacyLocationCollectionResponse",
    "LegacyLocationResponse",
    "LoginRequest",
    "NotificationChannelsResponse",
    "NotificationCollectionResponse",
    "PushConfirmationResponse",
    "PushSubscriptionRequest",
    "PushSubscriptionResponse",
    "ConfirmedPlanChangeRequest",
    "PlanningProposalAssignmentPayload",
    "PlanningProposalDayPayload",
    "PlanningProposalResponse",
    "PlanningProposalResultResponse",
    "PlanningProposalSlotPayload",
    "PlanningProposalWriteRequest",
    "PlanningRoundRequest",
    "RevisionDeleteRequest",
    "SessionResponse",
    "SessionRotationResponse",
    "ExamSlotStartRequest",
    "ExamSlotStatusUpdateRequest",
    "TokenRequest",
]


@dataclass(frozen=True)
class FastAPIConfig:
    """Startup configuration kept separate from database and service dependencies."""

    db_path: Path
    session_cookie_name: str
    csrf_cookie_name: str = "lzug_csrf"
    cookie_secure: bool = True
    https_only: bool = True
    cors_allowed_origins: frozenset[str] = frozenset()
    max_request_bytes: int = 1024 * 1024
    session_ttl: timedelta = timedelta(hours=8)
    static_dir: Path | None = None
    runtime_policy: RuntimePolicy = ProductRuntimePolicy()
    auth_rate_limit: int = 20
    auth_rate_window: timedelta = timedelta(minutes=1)
    auth_rate_limiter: RequestRateLimiter | None = None
    map_provider: MapProviderConfig = MapProviderConfig()
    runtime_settings: RuntimeSettings | None = None

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> FastAPIConfig:
        return cls.from_settings(RuntimeSettings.from_environment(environment))

    @classmethod
    def from_settings(
        cls,
        settings: RuntimeSettings,
        *,
        db_path: Path | None = None,
        static_dir: Path | None = None,
    ) -> FastAPIConfig:
        security = RuntimeSecurityConfig.from_settings(settings.security)
        paths = persistence_paths(settings=settings.persistence)
        configured_static_dir = static_dir if static_dir is not None else settings.server.static_dir
        return cls(
            db_path=db_path or paths.database,
            session_cookie_name="__Host-lzug_session" if security.https_only else "lzug_session",
            cookie_secure=security.https_only,
            https_only=security.https_only,
            cors_allowed_origins=security.cors_allowed_origins,
            max_request_bytes=security.max_request_bytes,
            session_ttl=security.session_ttl,
            static_dir=configured_static_dir,
            auth_rate_limit=security.auth_rate_limit,
            auth_rate_window=security.auth_rate_window,
            map_provider=MapProviderConfig.from_settings(settings.integrations),
            runtime_settings=settings,
        )


def _security_headers(config: FastAPIConfig, request: Request) -> dict[str, str]:
    frame_source = {
        "osm": "https://www.openstreetmap.org",
        "google": "https://www.google.com",
    }.get(config.map_provider.mode, "'none'")
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": (
            "strict-origin-when-cross-origin"
            if config.map_provider.mode == "osm"
            else "no-referrer"
        ),
        "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "X-Permitted-Cross-Domain-Policies": "none",
        "Content-Security-Policy": (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
            f"img-src 'self' data:; connect-src 'self'; frame-src {frame_source}"
        ),
    }
    if config.https_only:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    origin = request.headers.get("Origin")
    if origin in config.cors_allowed_origins:
        headers.update(
            {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Vary": "Origin",
            }
        )
    return headers


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


async def _transport_guard(request: Request, call_next, config: FastAPIConfig) -> Response:
    origin = request.headers.get("Origin")
    cross_origin = (
        origin is not None
        and not _same_origin(request, origin)
        and origin not in config.cors_allowed_origins
    )
    if cross_origin:
        response = _json_response(
            ApplicationResult(
                {"error": "Cross-origin request is not allowed."}, HTTPStatus.FORBIDDEN
            )
        )
    elif request.method == "OPTIONS":
        if not _is_api_path(request.url.path) or not origin:
            response = _not_found()
        else:
            response = Response(status_code=HTTPStatus.NO_CONTENT)
            response.headers.update(
                {
                    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, X-CSRF-Token",
                    "Access-Control-Max-Age": "600",
                }
            )
    else:
        try:
            validate_body_headers(request)
        except RequestTooLargeError as error:
            response = _json_response(
                ApplicationResult({"error": str(error)}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            )
        except ValueError as error:
            response = _json_response(
                ApplicationResult({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            )
        else:
            response = await call_next(request)
    for name, value in _security_headers(config, request).items():
        if name.lower() not in response.headers:
            response.headers[name] = value
    response.headers.setdefault("Cache-Control", "no-store")
    emit_event(
        "http_request",
        method=request.method,
        path=safe_http_path(request.url.path),
        status=response.status_code,
        bytes=len(getattr(response, "body", b"") or b""),
    )
    return response


@lru_cache(maxsize=8)
def _static_assets(root: Path) -> dict[str, tuple[bytes, str]]:
    content_types = {
        ".css": "text/css",
        ".html": "text/html",
        ".htm": "text/html",
        ".js": "text/javascript",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".ico": "image/x-icon",
        ".txt": "text/plain",
        ".webp": "image/webp",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".webmanifest": "application/manifest+json",
    }
    trusted = root.resolve(strict=True)
    result: dict[str, tuple[bytes, str]] = {}
    for path in trusted.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            path.resolve(strict=True).relative_to(trusted)
            result["/" + path.relative_to(trusted).as_posix()] = (
                path.read_bytes(),
                content_types.get(path.suffix.lower(), "application/octet-stream"),
            )
        except OSError, ValueError:
            continue
    return result


def _static_response(config: FastAPIConfig, request: Request) -> Response:
    if config.static_dir is None:
        return _not_found()
    try:
        decoded = unquote(request.url.path)
        if (
            not decoded.startswith("/")
            or any(ord(c) < 32 or ord(c) == 127 for c in decoded)
            or any(part in {".", ".."} for part in decoded.split("/"))
        ):
            raise ValueError
        assets = _static_assets(config.static_dir)
    except OSError, ValueError:
        return _not_found()
    asset = assets.get(decoded)
    serves_index = decoded == "/index.html"
    asset_path = (
        decoded in {"/favicon.ico", "/favicon.svg", "/robots.txt"}
        or decoded == "/assets"
        or decoded.startswith("/assets/")
        or "." in decoded.rsplit("/", 1)[-1]
    )
    if asset is None and not asset_path:
        asset = assets.get("/index.html")
        serves_index = asset is not None
    if asset is None:
        return _not_found()
    body, media_type = asset
    if serves_index:
        google_key = config.map_provider.browser_runtime_contract().get("googleMapsEmbedKey")
        if google_key:
            marker = b"<app-root></app-root>"
            replacement = (
                '<app-root data-google-maps-embed-key="'
                f'{escape(google_key, quote=True)}"></app-root>'
            ).encode()
            body = body.replace(marker, replacement, 1)
    return Response(
        body,
        headers={
            "Content-Type": media_type,
            "Cache-Control": (
                "no-cache" if serves_index else "public, max-age=31536000, immutable"
            ),
        },
    )


def _register_transport_guard(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    @app.middleware("http")
    async def transport_guard(request: Request, call_next):
        return await _transport_guard(request, call_next, resolved)


def _register_authentication_errors(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    @app.exception_handler(AuthenticationRequiredError)
    def auth_required(_request: Request, _error: AuthenticationRequiredError):
        return _json_response(
            ApplicationResult({"error": "Authentication required."}, HTTPStatus.UNAUTHORIZED)
        )

    @app.exception_handler(ForbiddenRequestError)
    def forbidden(_request: Request, error: ForbiddenRequestError):
        return _json_response(ApplicationResult({"error": str(error)}, HTTPStatus.FORBIDDEN))

    @app.exception_handler(PermissionError)
    def permission_denied(_request: Request, error: PermissionError):
        return _json_response(ApplicationResult({"error": str(error)}, HTTPStatus.FORBIDDEN))

    @app.exception_handler(RequestTooLargeError)
    def too_large(_request: Request, error: RequestTooLargeError):
        return _json_response(
            ApplicationResult({"error": str(error)}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        )

    @app.exception_handler(UnsupportedMediaTypeError)
    def unsupported_media(_request: Request, error: UnsupportedMediaTypeError):
        return _json_response(
            ApplicationResult({"error": str(error)}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        )

    @app.exception_handler(LocalAuthError)
    def local_auth(_request: Request, error: LocalAuthError):
        status = (
            HTTPStatus.TOO_MANY_REQUESTS
            if error.code == "rate_limited"
            else HTTPStatus.UNAUTHORIZED
        )
        if error.code in {"invalid_factor", "token_invalid"}:
            status = HTTPStatus.BAD_REQUEST
        response = _json_response(ApplicationResult({"error": str(error)}, status))
        if error.retry_after is not None:
            response.headers["Retry-After"] = str(error.retry_after)
        return response


def _register_planning_errors(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    @app.exception_handler(PlanValidationError)
    def plan_validation(_request: Request, error: PlanValidationError):
        payload = {
            "error": {
                "code": "planning_proposal_invalid",
                "message": "Planning proposal violates mandatory rules.",
                "violations": [
                    {
                        "code": item.code,
                        "message": item.message,
                        "day_id": item.day_id,
                        "slot_id": item.slot_id,
                        "member_id": item.member_id,
                    }
                    for item in error.issues
                ],
            }
        }
        return _json_response(ApplicationResult(payload, HTTPStatus.UNPROCESSABLE_ENTITY))

    @app.exception_handler(PlanConflictError)
    def plan_conflict(_request: Request, error: PlanConflictError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "planning_proposal_conflict", "message": str(error)}},
                HTTPStatus.CONFLICT,
            )
        )

    @app.exception_handler(ConfirmedPlanConflictError)
    def confirmed_plan_conflict(_request: Request, error: ConfirmedPlanConflictError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "confirmed_plan_conflict", "message": str(error)}},
                HTTPStatus.CONFLICT,
            )
        )


def _register_execution_errors(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    @app.exception_handler(ExamRoundConflictError)
    def exam_round_conflict(_request: Request, error: ExamRoundConflictError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "exam_round_conflict", "message": str(error)}},
                HTTPStatus.CONFLICT,
            )
        )

    @app.exception_handler(ExamRoundValidationError)
    def exam_round_validation(_request: Request, error: ExamRoundValidationError):
        return _json_response(
            ApplicationResult(
                {
                    "error": {
                        "code": "exam_round_prerequisites_failed",
                        "message": str(error),
                        "findings": error.findings,
                    }
                },
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        )

    @app.exception_handler(ExamProtocolConflictError)
    def exam_protocol_conflict(_request: Request, error: ExamProtocolConflictError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "exam_protocol_conflict", "message": str(error)}},
                HTTPStatus.CONFLICT,
            )
        )

    @app.exception_handler(ExamResultConflictError)
    def exam_result_conflict(_request: Request, error: ExamResultConflictError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "exam_result_conflict", "message": str(error)}},
                HTTPStatus.CONFLICT,
            )
        )

    @app.exception_handler(ExamDayConflictError)
    def exam_day_conflict(_request: Request, error: ExamDayConflictError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "exam_day_conflict", "message": str(error)}},
                HTTPStatus.CONFLICT,
            )
        )

    @app.exception_handler(ExamDayValidationError)
    def exam_day_validation(_request: Request, error: ExamDayValidationError):
        return _json_response(
            ApplicationResult(
                {
                    "error": {
                        "code": "exam_day_closure_invalid",
                        "message": str(error),
                        "findings": error.findings,
                    }
                },
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        )


def _register_request_errors(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    @app.exception_handler(ExamVenueConflictError)
    def exam_venue_conflict(_request: Request, error: ExamVenueConflictError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "exam_venue_conflict", "message": str(error)}},
                HTTPStatus.CONFLICT,
            )
        )

    @app.exception_handler(ExamVenueConfirmationRequiredError)
    def exam_venue_confirmation_required(
        _request: Request, error: ExamVenueConfirmationRequiredError
    ):
        return _json_response(
            ApplicationResult(
                {
                    "error": {
                        "code": "exam_venue_confirmation_required",
                        "message": str(error),
                    }
                },
                HTTPStatus.CONFLICT,
            )
        )

    @app.exception_handler(ExamVenueInUseError)
    def exam_venue_in_use(_request: Request, error: ExamVenueInUseError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "exam_venue_in_use", "message": str(error)}},
                HTTPStatus.CONFLICT,
            )
        )

    @app.exception_handler(MapProviderDisabledError)
    def map_provider_disabled(_request: Request, error: MapProviderDisabledError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "map_provider_disabled", "message": str(error)}},
                HTTPStatus.CONFLICT,
            )
        )

    @app.exception_handler(MapProviderUnavailableError)
    def map_provider_unavailable(_request: Request, error: MapProviderUnavailableError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "map_provider_unavailable", "message": str(error)}},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        )

    @app.exception_handler(SQLAlchemyError)
    def database_error(_request: Request, error: SQLAlchemyError):
        return _json_response(database_error_result(error))

    @app.exception_handler(ValueError)
    def invalid_request(_request: Request, error: ValueError):
        return _json_response(
            ApplicationResult({"error": str(error) or "Invalid request"}, HTTPStatus.BAD_REQUEST)
        )


def _register_transport_and_errors(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    _register_transport_guard(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )
    _register_authentication_errors(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )
    _register_planning_errors(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )
    _register_execution_errors(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )
    _register_request_errors(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )


def _register_operations_router(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    from .fastapi_operations_routes import create_operations_router

    router = create_operations_router(resolved, application, read_security, write_security)
    app.router.routes.extend(router.routes)


def _register_integration_router(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    from .fastapi_integration_routes import create_integration_router

    app.router.routes.extend(create_integration_router().routes)


def _register_exam_round_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    @app.get("/api/exam-rounds/{id}/lifecycle", openapi_extra=read_security)
    def exam_round_lifecycle(context: ReadContext, id: str):
        result = context.exam_round_lifecycle_service.get(context.authorization_scope, int(id))
        return _not_found() if result is None else _finish(context, context.respond(result))

    @app.post("/api/exam-rounds/{id}/closure", openapi_extra=write_security)
    def close_exam_round(context: WriteContext, id: str):
        result = context.exam_round_lifecycle_service.close(
            context.authorization_scope, int(id), context.read_json()
        )
        return _finish(context, context.respond(result))

    @app.post("/api/exam-rounds/{id}/cancellation", openapi_extra=write_security)
    def cancel_exam_round(context: WriteContext, id: str):
        result = context.exam_round_lifecycle_service.cancel(
            context.authorization_scope, int(id), context.read_json()
        )
        return _finish(context, context.respond(result))

    @app.post("/api/exam-rounds/{id}/reopening-impact", openapi_extra=write_security)
    def exam_round_reopening_impact(context: WriteContext, id: str):
        result = context.exam_round_lifecycle_service.reopening_impact(
            context.authorization_scope, int(id), context.read_json()
        )
        return _finish(context, context.respond(result))

    @app.post("/api/exam-rounds/{id}/reopenings", openapi_extra=write_security)
    def reopen_exam_round(context: WriteContext, id: str):
        result = context.exam_round_lifecycle_service.reopen(
            context.authorization_scope, int(id), context.read_json()
        )
        return _finish(context, context.respond(result))

    @app.put(
        "/api/exam-rounds/{id}/candidates/{candidate_id}/terminal-status",
        openapi_extra=write_security,
    )
    def set_exam_round_candidate_terminal_status(context: WriteContext, id: str, candidate_id: str):
        result = context.exam_round_lifecycle_service.set_candidate_terminal_status(
            context.authorization_scope,
            int(id),
            int(candidate_id),
            context.read_json(),
        )
        return _finish(context, context.respond(result))

    @app.put(
        "/api/exam-rounds/{id}/results/{result_id}/ihk-status",
        openapi_extra=write_security,
    )
    def document_exam_round_ihk_status(context: WriteContext, id: str, result_id: str):
        result = context.exam_round_lifecycle_service.document_ihk_status(
            context.authorization_scope,
            int(id),
            int(result_id),
            context.read_json(),
        )
        return _finish(context, context.respond(result))

    @app.get(
        "/api/exam-rounds/{id}/lifecycle/export.json",
        openapi_extra=read_security,
    )
    def export_exam_round_json(context: ReadContext, id: str):
        result = context.exam_round_lifecycle_service.machine_export(
            context.authorization_scope, int(id)
        )
        return _finish(context, context.respond(result))

    @app.get(
        "/api/exam-rounds/{id}/lifecycle/export.txt",
        response_class=Response,
        openapi_extra=read_security,
    )
    def export_exam_round_text(context: ReadContext, id: str):
        result = context.exam_round_lifecycle_service.human_export(
            context.authorization_scope, int(id)
        )
        return _plain_text(context, result, f"pruefungsrunde-{int(id)}-nachweis.txt")


def _register_exam_day_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    @app.get(
        "/api/confirmed-plan-days/{id}/closure",
        openapi_extra=read_security,
    )
    def exam_day_closure(context: ReadContext, id: str):
        result = context.exam_day_closure_service.get(context.authorization_scope, int(id))
        return _not_found() if result is None else _finish(context, context.respond(result))

    @app.post(
        "/api/confirmed-plan-days/{id}/closure",
        openapi_extra=write_security,
    )
    def close_exam_day(context: WriteContext, id: str):
        result = context.exam_day_closure_service.close(
            context.authorization_scope, int(id), context.read_json()
        )
        return _finish(context, context.respond(result))

    @app.post(
        "/api/confirmed-plan-days/{id}/reopening-impact",
        openapi_extra=write_security,
    )
    def exam_day_reopening_impact(context: WriteContext, id: str):
        result = context.exam_day_closure_service.reopening_impact(
            context.authorization_scope, int(id), context.read_json()
        )
        return _finish(context, context.respond(result))

    @app.post(
        "/api/confirmed-plan-days/{id}/reopenings",
        openapi_extra=write_security,
    )
    def reopen_exam_day(context: WriteContext, id: str):
        result = context.exam_day_closure_service.reopen(
            context.authorization_scope, int(id), context.read_json()
        )
        return _finish(context, context.respond(result))

    @app.get(
        "/api/confirmed-plan-days/{id}/closure/export.json",
        openapi_extra=read_security,
    )
    def export_exam_day_json(context: ReadContext, id: str):
        result = context.exam_day_closure_service.machine_export(
            context.authorization_scope, int(id)
        )
        return _finish(context, context.respond(result))

    @app.get(
        "/api/confirmed-plan-days/{id}/closure/export.txt",
        response_class=Response,
        openapi_extra=read_security,
    )
    def export_exam_day_text(context: ReadContext, id: str):
        result = context.exam_day_closure_service.human_export(context.authorization_scope, int(id))
        return _plain_text(context, result, f"pruefungstag-{int(id)}-abschluss.txt")


def _register_round_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    _register_exam_round_routes(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )
    _register_exam_day_routes(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )


def _register_planning_router(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    register_planning_router(
        app,
        read_security,
        write_security,
        finish=_finish,
        not_found=_not_found,
    )


def _register_execution_assessment_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    app.include_router(
        create_execution_router(
            finish=_finish,
            not_found=_not_found,
            plain_text=_plain_text,
            read_security=read_security,
            write_security=write_security,
        )
    )
    app.include_router(
        create_assessment_router(
            finish=_finish,
            not_found=_not_found,
            plain_text=_plain_text,
            read_security=read_security,
            write_security=write_security,
        )
    )


def _register_static_route(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def static_or_not_found(request: Request, path: str):
        return (
            _static_response(resolved, request)
            if not _is_api_path(request.url.path)
            else _not_found()
        )


def register_transport_and_errors(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    """Register the shared HTTP guard and exception translation boundary."""
    _register_transport_and_errors(
        app, resolved, application, read_security, write_security, venue_write_openapi
    )


def register_application_routes(
    app, resolved, application, read_security, write_security, venue_write_openapi
):
    """Register all product and runtime routes with the assembled application."""
    registrars = (
        _register_operations_router,
        _register_integration_router,
        _register_round_routes,
        _register_planning_router,
        _register_execution_assessment_routes,
        register_master_data_routes,
        _register_static_route,
    )
    for registrar in registrars:
        registrar(
            app,
            resolved,
            application,
            read_security,
            write_security,
            venue_write_openapi,
        )


def create_app(
    config: FastAPIConfig | None = None, services: ApplicationServices | None = None
) -> FastAPI:
    """Compatibility entry point for the canonical application factory."""
    from .fastapi_assembly import create_app as assemble_app

    return assemble_app(config, services)
