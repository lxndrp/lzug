"""FastAPI routers for runtime, authentication, and observability operations."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel

from . import hateoas
from .api_contracts import (
    ApiRootResponse,
    DemoScenarioOverviewResponse,
    DemoScenarioResetResponse,
    FactorActivationRequest,
    FrontendErrorRequest,
    HealthResponse,
    LoginRequest,
    SessionResponse,
    SessionRotationResponse,
    TokenRequest,
)
from .application import AuthenticationRequiredError, ForbiddenRequestError
from .fastapi_dependencies import BodyContext, Context, SessionContext, SessionWriteContext
from .fastapi_http import finish, json_response, not_found, same_origin
from .observability import emit_event
from .transport import RequestContext, RequestTooLargeError

if TYPE_CHECKING:
    from .application import ReadApplication
    from .fastapi_app import FastAPIConfig


def _request_body(
    model: type[BaseModel], security: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        **(security or {}),
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": {"$ref": f"#/components/schemas/{model.__name__}"}}
            },
        },
    }


def create_runtime_router(application: ReadApplication) -> APIRouter:
    """Build public health and protected API discovery routes."""
    router = APIRouter()

    @router.get("/api/health", response_model=HealthResponse)
    def health():
        return json_response(application.health())

    @router.get(
        "/api/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}}
    )
    def ready():
        return json_response(application.readiness())

    @router.get(
        "/api", response_model=ApiRootResponse, openapi_extra={"security": [{"sessionCookie": []}]}
    )
    def api_root(context: SessionContext):
        return finish(context, context.respond(hateoas.api_root()))

    @router.get(
        "/api/openapi.json",
        response_model=dict[str, object],
        openapi_extra={"security": [{"sessionCookie": []}]},
    )
    def openapi_document(request: Request, context: SessionContext):
        return finish(context, context.respond(request.app.openapi()))

    @router.get("/api/docs", include_in_schema=False)
    def api_docs(context: SessionContext):
        return Response(
            "<!doctype html><html lang='de'><head><meta charset='utf-8'>"
            "<title>lzug API Docs</title></head><body><main><h1>lzug API</h1>"
            "<p>Die maschinenlesbare Beschreibung ist als "
            "<a href='/api/openapi.json'>OpenAPI-Dokument</a> verfügbar.</p>"
            "</main></body></html>",
            media_type="text/html",
        )

    return router


def create_demo_router(
    resolved: FastAPIConfig,
    read_security: dict[str, object],
    write_security: dict[str, object],
) -> APIRouter:
    """Build the product-neutral routes delegated to the active runtime policy."""
    router = APIRouter()

    def runtime_get(context: RequestContext, parts: list[str]):
        return (
            finish(context)
            if resolved.runtime_policy.handle_public_get(context, parts)
            else not_found()
        )

    def runtime_post(context: RequestContext, parts: list[str]):
        return (
            finish(context)
            if resolved.runtime_policy.handle_public_post(context, parts)
            else not_found()
        )

    demo_api_prefix = "/api/" + "demo"

    @router.get(f"{demo_api_prefix}/status", include_in_schema=False)
    def demo_status(context: Context):
        return runtime_get(context, ["demo", "status"])

    @router.post(f"{demo_api_prefix}/session", include_in_schema=False)
    def demo_session(context: BodyContext):
        return runtime_post(context, ["demo", "session"])

    @router.get(
        f"{demo_api_prefix}/scenarios",
        response_model=DemoScenarioOverviewResponse,
        openapi_extra=read_security,
    )
    def demo_scenarios(context: Context):
        return runtime_get(context, ["demo", "scenarios"])

    @router.post(
        f"{demo_api_prefix}/reset",
        response_model=DemoScenarioResetResponse,
        openapi_extra={
            **write_security,
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"type": "object", "additionalProperties": False}
                    }
                },
            },
        },
    )
    def demo_reset(context: BodyContext):
        return runtime_post(context, ["demo", "reset"])

    return router


def create_login_router(resolved: FastAPIConfig) -> APIRouter:
    """Build the local password and second-factor login route."""
    router = APIRouter()

    @router.post(
        "/api/auth/login",
        response_model=dict[str, object],
        openapi_extra=_request_body(LoginRequest),
    )
    def login(context: BodyContext):
        if not resolved.runtime_policy.allow_product_auth():
            raise ForbiddenRequestError("Forbidden.")
        if not context.allow_public_auth_request(["auth", "login"]):
            return finish(context)
        payload = context.read_json()
        result = context.local_auth_service.login(
            payload.get("email", "") if isinstance(payload.get("email", ""), str) else "",
            (payload.get("password", "") if isinstance(payload.get("password", ""), str) else ""),
            (
                payload.get("second_factor", "")
                if isinstance(payload.get("second_factor", ""), str)
                else ""
            ),
            remote_key=context.client_key,
        )
        context.issue_session_cookies(result.credentials)
        return finish(
            context,
            context.respond(
                {
                    "authenticated": True,
                    "account_id": result.account_id,
                    "expires_at": result.credentials.expires_at,
                }
            ),
        )

    return router


def create_token_auth_router(resolved: FastAPIConfig) -> APIRouter:
    """Build invitation and recovery token routes."""
    router = APIRouter()

    def auth_route(name: str, action: str):
        def endpoint(context: BodyContext):
            if not resolved.runtime_policy.allow_product_auth():
                raise ForbiddenRequestError("Forbidden.")
            if not context.allow_public_auth_request(["auth", name, action]):
                return finish(context)
            payload = context.read_json()
            service = context.local_auth_service
            if name == "invitation" and action == "prepare":
                item = service.prepare_invitation(payload.get("token", ""))
                result = {
                    "email": item.email,
                    "expires_at": item.expires_at,
                    "totp_secret": item.totp_secret,
                }
            elif name == "invitation":
                account, codes = service.activate_invitation(
                    payload.get("token", ""),
                    payload.get("password", ""),
                    payload.get("totp_secret", ""),
                    payload.get("totp_code", ""),
                )
                result = {"activated": True, "account": account, "recovery_codes": codes}
            elif action == "prepare":
                item = service.prepare_recovery(payload.get("token", ""))
                result = {
                    "email": item.email,
                    "expires_at": item.expires_at,
                    "totp_secret": item.totp_secret,
                }
            else:
                account, codes = service.complete_recovery(
                    payload.get("token", ""),
                    payload.get("password", ""),
                    payload.get("totp_secret", ""),
                    payload.get("totp_code", ""),
                )
                result = {"recovered": True, "account": account, "recovery_codes": codes}
            return finish(context, context.respond(result))

        return endpoint

    for path, name, action, model in (
        ("/api/auth/invitation/prepare", "invitation", "prepare", TokenRequest),
        ("/api/auth/invitation/activate", "invitation", "activate", FactorActivationRequest),
        ("/api/auth/recovery/prepare", "recovery", "prepare", TokenRequest),
        ("/api/auth/recovery/complete", "recovery", "complete", FactorActivationRequest),
    ):
        router.add_api_route(
            path,
            auth_route(name, action),
            methods=["POST"],
            response_model=dict[str, object],
            openapi_extra=_request_body(model),
            name=f"auth_{name}_{action}",
        )

    return router


def create_session_router(resolved: FastAPIConfig) -> APIRouter:
    """Build authenticated session inspection, rotation, and logout routes."""
    router = APIRouter()

    @router.get(
        "/api/session",
        response_model=SessionResponse,
        openapi_extra={"security": [{"sessionCookie": []}]},
    )
    def session(context: SessionContext):
        auth = context.auth_context
        return finish(
            context,
            context.respond(
                {
                    "authenticated": True,
                    "account_id": auth.account_id,
                    "person_id": auth.person_id,
                    "committee_member_id": auth.committee_member_id,
                    "is_operator": auth.is_operator,
                    **resolved.runtime_policy.session_view(context, auth),
                }
            ),
        )

    @router.post(
        "/api/session/rotate",
        response_model=SessionRotationResponse,
        openapi_extra={"security": [{"sessionCookie": [], "csrfHeader": []}]},
    )
    def rotate_session(context: SessionWriteContext):
        credentials = context.authentication_repository.rotate_session(
            context.session_token, ttl=context.session_ttl
        )
        if credentials is None:
            raise AuthenticationRequiredError
        context.issue_session_cookies(credentials)
        return finish(
            context, context.respond({"status": "rotated", "expires_at": credentials.expires_at})
        )

    @router.post(
        "/api/session/logout",
        status_code=204,
        openapi_extra={"security": [{"sessionCookie": [], "csrfHeader": []}]},
    )
    def logout_session(context: SessionWriteContext):
        session_token = context.session_token
        context.authentication_repository.revoke_session(session_token, reason="logout")
        context.clear_session_cookies()
        resolved.runtime_policy.discard_session(context, session_token)
        return finish(context, context.respond({}, HTTPStatus.NO_CONTENT))

    return router


def create_auth_router(resolved: FastAPIConfig) -> APIRouter:
    """Compose the local authentication and session lifecycle routes."""
    router = APIRouter()
    for owned_router in (
        create_login_router(resolved),
        create_token_auth_router(resolved),
        create_session_router(resolved),
    ):
        router.routes.extend(owned_router.routes)
    return router


def create_observability_router() -> APIRouter:
    """Build the same-origin, rate-limited frontend observability route."""
    router = APIRouter()

    @router.post(
        "/api/observability/frontend-errors",
        status_code=202,
        openapi_extra=_request_body(FrontendErrorRequest),
    )
    def frontend_error(request: Request, context: BodyContext):
        origin = request.headers.get("Origin")
        if (
            origin is None
            or not same_origin(request, origin)
            or request.headers.get("Sec-Fetch-Site") != "same-origin"
        ):
            raise ForbiddenRequestError("Forbidden.")
        retry_after = max(
            context.observability_global_rate_limiter.check("global") or 0,
            context.observability_rate_limiter.check(context.client_key) or 0,
        )
        if retry_after:
            context.add_header("Retry-After", str(retry_after))
            return finish(
                context,
                context.respond({"error": "Too many requests."}, HTTPStatus.TOO_MANY_REQUESTS),
            )
        if len(request.state.raw_body) > 256:
            raise RequestTooLargeError("Observability event exceeds 256 bytes.")
        payload = context.read_json()
        if payload.get("kind") not in {"bootstrap", "http", "runtime"}:
            raise ValueError("Invalid frontend error kind")
        expected_fields = {"kind", "status"} if payload["kind"] == "http" else {"kind"}
        if set(payload) != expected_fields:
            raise ValueError("Invalid frontend error fields")
        status = payload.get("status", 0)
        if not isinstance(status, int) or isinstance(status, bool) or not 0 <= status <= 599:
            raise ValueError("Invalid frontend error status")
        emit_event("frontend_error", severity="error", kind=payload["kind"], status=status)
        return finish(context, context.respond({}, HTTPStatus.ACCEPTED))

    return router


def create_operations_router(
    resolved: FastAPIConfig,
    application: ReadApplication,
    read_security: dict[str, object],
    write_security: dict[str, object],
) -> APIRouter:
    """Compose the routers owned by the operational HTTP boundary."""
    router = APIRouter()
    for owned_router in (
        create_runtime_router(application),
        create_demo_router(resolved, read_security, write_security),
        create_auth_router(resolved),
        create_observability_router(),
    ):
        router.routes.extend(owned_router.routes)
    return router
