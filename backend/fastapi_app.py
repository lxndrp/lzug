"""The canonical FastAPI application for the lzug product and demo runtimes."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import FastAPI, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from . import hateoas
from .application import (
    ApplicationResult,
    ApplicationServices,
    AuthenticationRequiredError,
    ForbiddenRequestError,
    ReadApplication,
    database_error_result,
)
from .database import database_path
from .exam_protocols import ExamProtocolConflictError
from .local_auth import LocalAuthError
from .models import CANDIDATE_COMMITTEE_ASSIGNMENT, EXAM_DAY, EXAM_DAY_ASSIGNMENT, EXAM_SLOT
from .observability import emit_event, safe_http_path
from .planning import PlanConflictError, PlanValidationError
from .repositories import PLAN_AGGREGATE_RESOURCES, REST_RESOURCES
from .runtime_policy import ProductRuntimePolicy, RuntimePolicy
from .security import RequestRateLimiter, RuntimeSecurityConfig
from .transport import (
    RequestContext,
    RequestTooLargeError,
    UnsupportedMediaTypeError,
    planning_proposal_from_payload,
)


class ErrorResponse(BaseModel):
    error: str


class HealthResponse(BaseModel):
    status: str
    version: str
    revision: str
    links: dict[str, object] = Field(alias="_links")


class ApiRootResponse(BaseModel):
    version: str
    links: dict[str, object] = Field(alias="_links")


class LoginRequest(BaseModel):
    email: str = ""
    password: str = ""
    second_factor: str = ""


class TokenRequest(BaseModel):
    token: str = ""


class FactorActivationRequest(BaseModel):
    token: str = ""
    password: str = ""
    totp_secret: str = ""
    totp_code: str = ""


class FrontendErrorRequest(BaseModel):
    kind: str
    status: int | None = None


class SessionResponse(BaseModel):
    authenticated: bool
    account_id: int
    person_id: int | None
    committee_member_id: int | None
    is_operator: bool


class SessionRotationResponse(BaseModel):
    status: str
    expires_at: str


class DomainResourceWrite(BaseModel):
    model_config = ConfigDict(extra="allow")


class DomainResourceResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class DomainCollectionResponse(BaseModel):
    items: list[DomainResourceResponse]
    links: dict[str, object] = Field(alias="_links")


MIGRATED_DOMAIN_RESOURCES = (
    "committees",
    "persons",
    "members",
    "memberships",
    "locations",
    "exam-half-years",
    "exam-rounds",
    "round-candidates",
    "candidates",
    "planning-settings",
    "member-availabilities",
)
MIGRATED_PLANNING_RESOURCES = (
    "candidate-exam-days",
    "exam-days",
    "exam-slots",
    "exam-day-assignments",
)


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

    @classmethod
    def from_environment(cls) -> FastAPIConfig:
        security = RuntimeSecurityConfig.from_environment()
        return cls(
            db_path=database_path(),
            session_cookie_name="__Host-lzug_session" if security.https_only else "lzug_session",
            cookie_secure=security.https_only,
            https_only=security.https_only,
            cors_allowed_origins=security.cors_allowed_origins,
            max_request_bytes=security.max_request_bytes,
            session_ttl=security.session_ttl,
            static_dir=(
                Path(os.environ["LZUG_STATIC_DIR"]) if os.environ.get("LZUG_STATIC_DIR") else None
            ),
            auth_rate_limit=security.auth_rate_limit,
            auth_rate_window=security.auth_rate_window,
        )


def _json_response(result: ApplicationResult, context: RequestContext | None = None) -> Response:
    if result.status == HTTPStatus.NO_CONTENT:
        response: Response = Response(status_code=int(result.status))
    else:
        response = Response(
            content=json.dumps(result.payload, ensure_ascii=False),
            status_code=int(result.status),
            media_type="application/json",
            headers={"Cache-Control": "no-store"},
        )
    if context is not None:
        for name, value in context.response_headers:
            response.raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
    return response


def _not_found() -> Response:
    return _json_response(ApplicationResult({"error": "Not found"}, HTTPStatus.NOT_FOUND))


def _context(request: Request, config: FastAPIConfig, body: bytes = b"") -> RequestContext:
    context = RequestContext(
        request=request,
        db_path=config.db_path,
        session_cookie_name=config.session_cookie_name,
        csrf_cookie_name=config.csrf_cookie_name,
        cookie_secure=config.cookie_secure,
        session_ttl=config.session_ttl,
        max_request_bytes=config.max_request_bytes,
        runtime_policy=config.runtime_policy,
        auth_rate_limiter=request.app.state.auth_rate_limiter,
        observability_rate_limiter=request.app.state.observability_rate_limiter,
        observability_global_rate_limiter=request.app.state.observability_global_rate_limiter,
    )
    context.set_body(body)
    return context


def _body(request: Request) -> bytes:
    return getattr(request.state, "raw_body", b"")


def _finish(context: RequestContext, result: ApplicationResult | None = None) -> Response:
    return _json_response(result or context.response_result or ApplicationResult({}), context)


def _text(context: RequestContext, value: str) -> Response:
    response = Response(
        value, media_type="text/calendar; charset=utf-8", headers={"Cache-Control": "no-store"}
    )
    response.headers["Content-Disposition"] = "attachment; filename=pruefungstermine.ics"
    for name, header_value in context.response_headers:
        response.raw_headers.append(
            (name.lower().encode("latin-1"), header_value.encode("latin-1"))
        )
    return response


def _plain_text(context: RequestContext, value: str, filename: str) -> Response:
    response = Response(
        value, media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-store"}
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    for name, header_value in context.response_headers:
        response.raw_headers.append(
            (name.lower().encode("latin-1"), header_value.encode("latin-1"))
        )
    return response


def _security_headers(config: FastAPIConfig, request: Request) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "X-Permitted-Cross-Domain-Policies": "none",
        "Content-Security-Policy": (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
            "img-src 'self' data:; connect-src 'self'"
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


def _normalized_authority(value: str, *, scheme: str | None = None) -> tuple[str, str, int] | None:
    try:
        parsed = urlparse(value if scheme is None else f"{scheme}://{value}")
        port = parsed.port
    except ValueError:
        return None
    expected_scheme = parsed.scheme if scheme is None else scheme
    allowed_paths = {"", "/"} if scheme is not None else {""}
    if (
        expected_scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in allowed_paths
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return None
    return (
        expected_scheme,
        parsed.hostname.lower(),
        port or (443 if expected_scheme == "https" else 80),
    )


def _same_origin(request: Request, origin: str) -> bool:
    parsed = _normalized_authority(origin)
    if parsed is None:
        return False
    scheme, hostname, port = parsed
    return _normalized_authority(request.headers.get("Host", ""), scheme=scheme) == (
        scheme,
        hostname,
        port,
    )


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
    elif request.headers.get("Transfer-Encoding"):
        response = _json_response(
            ApplicationResult(
                {"error": "Transfer-Encoding is not supported"}, HTTPStatus.BAD_REQUEST
            )
        )
    else:
        raw_length = request.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else 0
        except ValueError:
            length = -1
        if length < 0:
            response = _json_response(
                ApplicationResult({"error": "Invalid Content-Length"}, HTTPStatus.BAD_REQUEST)
            )
        elif length > config.max_request_bytes:
            response = _json_response(
                ApplicationResult(
                    {"error": f"Request body exceeds {config.max_request_bytes} bytes."},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
            )
        else:
            request.state.raw_body = await request.body()
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
    asset_path = (
        decoded in {"/favicon.ico", "/favicon.svg", "/robots.txt"}
        or decoded == "/assets"
        or decoded.startswith("/assets/")
        or "." in decoded.rsplit("/", 1)[-1]
    )
    if asset is None and not asset_path:
        asset = assets.get("/index.html")
    if asset is None:
        return _not_found()
    body, media_type = asset
    return Response(
        body,
        headers={
            "Content-Type": media_type,
            "Cache-Control": (
                "no-cache" if decoded == "/index.html" else "public, max-age=31536000, immutable"
            ),
        },
    )


def create_app(
    config: FastAPIConfig | None = None, services: ApplicationServices | None = None
) -> FastAPI:
    """Create the single FastAPI application used by product and demo images."""
    resolved = config or FastAPIConfig.from_environment()
    application = ReadApplication(resolved.db_path, services)
    app = FastAPI(title="lzug API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.lzug_config = resolved
    app.state.auth_rate_limiter = resolved.auth_rate_limiter or RequestRateLimiter(
        resolved.auth_rate_limit, resolved.auth_rate_window
    )
    app.state.observability_rate_limiter = RequestRateLimiter(30, timedelta(minutes=1))
    app.state.observability_global_rate_limiter = RequestRateLimiter(120, timedelta(minutes=1))
    read_security = {"security": [{"sessionCookie": []}]}
    write_security = {"security": [{"sessionCookie": [], "csrfHeader": []}]}

    @app.middleware("http")
    async def transport_guard(request: Request, call_next):
        return await _transport_guard(request, call_next, resolved)

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

    @app.exception_handler(ExamProtocolConflictError)
    def exam_protocol_conflict(_request: Request, error: ExamProtocolConflictError):
        return _json_response(
            ApplicationResult(
                {"error": {"code": "exam_protocol_conflict", "message": str(error)}},
                HTTPStatus.CONFLICT,
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

    @app.get("/api/health", response_model=HealthResponse)
    def health():
        return _json_response(application.health())

    @app.get(
        "/api/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}}
    )
    def ready():
        return _json_response(application.readiness())

    @app.get(
        "/api", response_model=ApiRootResponse, openapi_extra={"security": [{"sessionCookie": []}]}
    )
    def api_root(request: Request):
        context = _context(request, resolved)
        context.require_authenticated(require_actor=False)
        return _finish(context, context.respond(hateoas.api_root()))

    @app.get(
        "/api/openapi.json",
        response_model=dict[str, object],
        openapi_extra={"security": [{"sessionCookie": []}]},
    )
    def openapi_document(request: Request):
        context = _context(request, resolved)
        context.require_authenticated(require_actor=False)
        return _finish(context, context.respond(app.openapi()))

    @app.get("/api/docs", include_in_schema=False)
    def api_docs(request: Request):
        context = _context(request, resolved)
        context.require_authenticated(require_actor=False)
        return Response(
            "<!doctype html><html lang='de'><head><meta charset='utf-8'>"
            "<title>lzug API Docs</title></head><body><main><h1>lzug API</h1>"
            "<p>Die maschinenlesbare Beschreibung ist als "
            "<a href='/api/openapi.json'>OpenAPI-Dokument</a> verfügbar.</p>"
            "</main></body></html>",
            media_type="text/html",
        )

    def runtime_get(request: Request, parts: list[str]):
        context = _context(request, resolved)
        return (
            _finish(context)
            if resolved.runtime_policy.handle_public_get(context, parts)
            else _not_found()
        )

    def runtime_post(request: Request, parts: list[str]):
        context = _context(request, resolved, _body(request))
        return (
            _finish(context)
            if resolved.runtime_policy.handle_public_post(context, parts)
            else _not_found()
        )

    demo_api_prefix = "/api/" + "demo"

    @app.get(f"{demo_api_prefix}/status", include_in_schema=False)
    def demo_status(request: Request):
        return runtime_get(request, ["demo", "status"])

    @app.post(f"{demo_api_prefix}/session", include_in_schema=False)
    def demo_session(request: Request):
        return runtime_post(request, ["demo", "session"])

    @app.post("/api/auth/login", response_model=dict[str, object])
    def login(request: Request):
        context = _context(request, resolved, _body(request))
        if not resolved.runtime_policy.allow_product_auth():
            raise ForbiddenRequestError("Forbidden.")
        if not context.allow_public_auth_request(["auth", "login"]):
            return _finish(context)
        payload = context.read_json()
        result = context.local_auth_service.login(
            payload.get("email", "") if isinstance(payload.get("email", ""), str) else "",
            payload.get("password", "") if isinstance(payload.get("password", ""), str) else "",
            (
                payload.get("second_factor", "")
                if isinstance(payload.get("second_factor", ""), str)
                else ""
            ),
            remote_key=context.client_key,
        )
        context.issue_session_cookies(result.credentials)
        return _finish(
            context,
            context.respond(
                {
                    "authenticated": True,
                    "account_id": result.account_id,
                    "expires_at": result.credentials.expires_at,
                }
            ),
        )

    def auth_route(name: str, action: str):
        def endpoint(request: Request):
            context = _context(request, resolved, _body(request))
            if not resolved.runtime_policy.allow_product_auth():
                raise ForbiddenRequestError("Forbidden.")
            if not context.allow_public_auth_request(["auth", name, action]):
                return _finish(context)
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
            return _finish(context, context.respond(result))

        return endpoint

    for path, name, action in (
        ("/api/auth/invitation/prepare", "invitation", "prepare"),
        ("/api/auth/invitation/activate", "invitation", "activate"),
        ("/api/auth/recovery/prepare", "recovery", "prepare"),
        ("/api/auth/recovery/complete", "recovery", "complete"),
    ):
        app.add_api_route(
            path,
            auth_route(name, action),
            methods=["POST"],
            response_model=dict[str, object],
            name=f"auth_{name}_{action}",
        )

    @app.get(
        "/api/session",
        response_model=SessionResponse,
        openapi_extra={"security": [{"sessionCookie": []}]},
    )
    def session(request: Request):
        context = _context(request, resolved)
        auth = context.require_authenticated(require_actor=False)
        return _finish(
            context,
            context.respond(
                {
                    "authenticated": True,
                    "account_id": auth.account_id,
                    "person_id": auth.person_id,
                    "committee_member_id": auth.committee_member_id,
                    "is_operator": auth.is_operator,
                    **resolved.runtime_policy.session_view(auth),
                }
            ),
        )

    @app.post(
        "/api/session/rotate",
        response_model=SessionRotationResponse,
        openapi_extra={"security": [{"sessionCookie": [], "csrfHeader": []}]},
    )
    def rotate_session(request: Request):
        context = _context(request, resolved)
        auth = context.require_authenticated(require_actor=False, require_csrf=True)
        context.authorize_mutation("POST", ["session", "rotate"], auth)
        credentials = context.authentication_repository.rotate_session(
            context.session_token, ttl=context.session_ttl
        )
        if credentials is None:
            raise AuthenticationRequiredError
        context.issue_session_cookies(credentials)
        return _finish(
            context, context.respond({"status": "rotated", "expires_at": credentials.expires_at})
        )

    @app.post(
        "/api/session/logout",
        status_code=204,
        openapi_extra={"security": [{"sessionCookie": [], "csrfHeader": []}]},
    )
    def logout_session(request: Request):
        context = _context(request, resolved)
        auth = context.require_authenticated(require_actor=False, require_csrf=True)
        context.authorize_mutation("POST", ["session", "logout"], auth)
        context.authentication_repository.revoke_session(context.session_token, reason="logout")
        context.clear_session_cookies()
        return _finish(context, context.respond({}, HTTPStatus.NO_CONTENT))

    @app.post(
        "/api/observability/frontend-errors",
        status_code=202,
    )
    def frontend_error(request: Request):
        context = _context(request, resolved, _body(request))
        origin = request.headers.get("Origin")
        if (
            origin is None
            or not _same_origin(request, origin)
            or request.headers.get("Sec-Fetch-Site") != "same-origin"
        ):
            raise ForbiddenRequestError("Forbidden.")
        retry_after = max(
            context.observability_global_rate_limiter.check("global") or 0,
            context.observability_rate_limiter.check(context.client_key) or 0,
        )
        if retry_after:
            context.add_header("Retry-After", str(retry_after))
            return _finish(
                context,
                context.respond({"error": "Too many requests."}, HTTPStatus.TOO_MANY_REQUESTS),
            )
        if len(_body(request)) > 256:
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
        return _finish(context, context.respond({}, HTTPStatus.ACCEPTED))

    @app.get(
        "/api/round-summary",
        response_model=dict[str, object],
        openapi_extra={"security": [{"sessionCookie": []}]},
    )
    def round_summary(request: Request, round_id: str | None = Query(default=None)):
        context = _context(request, resolved)
        context.require_authenticated()
        try:
            parsed_round_id = int(round_id or "1")
        except ValueError:
            return _finish(
                context, context.respond({"error": "Invalid request"}, HTTPStatus.BAD_REQUEST)
            )
        return _finish(
            context,
            context.read_application.round_summary(context.authorization_scope, parsed_round_id),
        )

    @app.get("/api/calendar/feed/{token}.ics", include_in_schema=False)
    def personal_feed(request: Request, token: str):
        context = _context(request, resolved)
        if not token or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for c in token
        ):
            return _not_found()
        calendar = context.calendar_service.feed_ics(token)
        return _not_found() if calendar is None else _text(context, calendar)

    @app.get("/api/calendar/events/{id}.ics", include_in_schema=False)
    def event_feed(request: Request, id: str):
        context = _context(request, resolved)
        context.require_authenticated()
        if not id.isdigit():
            return _not_found()
        calendar = context.calendar_service.event_ics(int(id), context.authorization_scope)
        return _not_found() if calendar is None else _text(context, calendar)

    def require_read(context: RequestContext):
        context.require_authenticated()

    @app.get("/api/calendar")
    @app.get("/api/calendar/feed")
    def calendar_status(request: Request):
        context = _context(request, resolved)
        require_read(context)
        result = {
            **context.calendar_service.status(context.authorization_scope),
            "_links": {
                "self": {"href": "/api/calendar"},
                "feed": {"href": "/api/calendar/feed", "method": "POST"},
            },
        }
        return _finish(context, context.respond(result))

    @app.get("/api/calendar/events")
    def calendar_events(request: Request):
        context = _context(request, resolved)
        require_read(context)
        return _finish(
            context,
            context.respond(
                {
                    "items": context.calendar_service.list_events(context.authorization_scope),
                    "_links": {"self": {"href": "/api/calendar/events"}},
                }
            ),
        )

    @app.post("/api/calendar/feed", status_code=201)
    def activate_feed(request: Request):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated()
        context.authorize_mutation("POST", ["calendar", "feed"], auth)
        payload = context.read_json()
        result = context.calendar_service.activate(
            context.authorization_scope,
            rotate=bool(context.normalize_bool(payload.get("rotate", False))),
        )
        result.update(
            {
                "_links": {
                    "self": {"href": "/api/calendar"},
                    "feed": {"href": "/api/calendar/feed"},
                    "events": {"href": "/api/calendar/events"},
                },
                "notice": (
                    "Der Feed-Zugang ist persönlich. Bereits extern gespeicherte Termine können "
                    "nach Widerruf oder Neuerzeugung nicht zuverlässig entfernt werden."
                ),
            }
        )
        return _finish(context, context.respond(result, HTTPStatus.CREATED))

    @app.delete("/api/calendar/feed")
    def revoke_feed(request: Request):
        context = _context(request, resolved)
        auth = context.require_authenticated()
        context.authorize_mutation("DELETE", ["calendar", "feed"], auth)
        context.calendar_service.revoke(context.authorization_scope)
        result = {
            **context.calendar_service.status(context.authorization_scope),
            "_links": {
                "self": {"href": "/api/calendar"},
                "feed": {"href": "/api/calendar/feed"},
                "events": {"href": "/api/calendar/events"},
            },
            "notice": (
                "Der Feed wurde widerrufen. Bereits extern gespeicherte Termine können nicht "
                "zuverlässig entfernt werden."
            ),
        }
        return _finish(context, context.respond(result))

    @app.get("/api/notifications")
    def notifications(request: Request):
        context = _context(request, resolved)
        require_read(context)
        return _finish(
            context,
            context.respond(
                {
                    "items": context.notification_service.list_own(context.authorization_scope),
                    "_links": {
                        "self": {"href": "/api/notifications"},
                        "channels": {"href": "/api/notification-channels"},
                        "problems": {"href": "/api/notification-problems"},
                    },
                }
            ),
        )

    @app.get("/api/notification-problems")
    def notification_problems(request: Request):
        context = _context(request, resolved)
        require_read(context)
        return _finish(
            context,
            context.respond(
                {
                    "items": context.notification_service.problems(context.authorization_scope),
                    "_links": {"self": {"href": "/api/notification-problems"}},
                }
            ),
        )

    @app.get("/api/notification-overview")
    def notification_overview(request: Request):
        context = _context(request, resolved)
        require_read(context)
        return _finish(
            context,
            context.respond(
                {
                    "items": context.notification_service.management_overview(
                        context.authorization_scope
                    ),
                    "_links": {"self": {"href": "/api/notification-overview"}},
                }
            ),
        )

    @app.get("/api/notification-channels")
    def notification_channels(request: Request):
        context = _context(request, resolved)
        require_read(context)
        channels = context.notification_service.channels()
        return _finish(
            context,
            context.respond(
                {
                    "web_push": {
                        "available": channels.push_public_key is not None,
                        "public_key": channels.push_public_key,
                    },
                    "email_fallback_configured": channels.email_configured,
                    "sink_enabled": channels.sink_enabled,
                }
            ),
        )

    @app.post("/api/push-subscriptions", status_code=201)
    def register_push(request: Request):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated()
        context.authorize_mutation("POST", ["push-subscriptions"], auth)
        endpoint = context.read_json().get("endpoint")
        if not isinstance(endpoint, str):
            raise ValueError("Push endpoint is required")
        return _finish(
            context,
            context.respond(
                context.notification_service.register_push(context.authorization_scope, endpoint),
                HTTPStatus.CREATED,
            ),
        )

    @app.delete("/api/push-subscriptions/{id}", status_code=204)
    def unregister_push(request: Request, id: str):
        context = _context(request, resolved)
        auth = context.require_authenticated()
        context.authorize_mutation("DELETE", ["push-subscriptions", id], auth)
        return (
            _not_found()
            if not context.notification_service.unregister_push(
                context.authorization_scope, int(id)
            )
            else _finish(context, context.respond({}, HTTPStatus.NO_CONTENT))
        )

    @app.post("/api/notifications/{id}/push-confirmation")
    def confirm_push(request: Request, id: str):
        context = _context(request, resolved)
        auth = context.require_authenticated()
        context.authorize_mutation("POST", ["notifications", id, "push-confirmation"], auth)
        return (
            _not_found()
            if not context.notification_service.confirm_push(context.authorization_scope, int(id))
            else _finish(context, context.respond({"status": "technically_confirmed"}))
        )

    @app.get("/api/absence-reports")
    def absence_reports(request: Request):
        context = _context(request, resolved)
        require_read(context)
        return _finish(
            context,
            context.respond(
                {
                    "items": context.absence_service.list(context.authorization_scope),
                    "_links": {"self": {"href": "/api/absence-reports"}},
                }
            ),
        )

    @app.get("/api/absence-reports/{id}")
    def absence_report(request: Request, id: str):
        context = _context(request, resolved)
        require_read(context)
        report = context.absence_service.get(context.authorization_scope, int(id))
        return _not_found() if report is None else _finish(context, context.respond(report))

    @app.post("/api/absence-reports", status_code=201)
    def create_absence(request: Request):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated()
        context.authorize_mutation("POST", ["absence-reports"], auth)
        return _finish(
            context,
            context.respond(
                context.absence_service.report(context.authorization_scope, context.read_json()),
                HTTPStatus.CREATED,
            ),
        )

    def absence_action(action: str):
        def endpoint(request: Request, report_id: str):
            context = _context(request, resolved, _body(request))
            auth = context.require_authenticated()
            context.authorize_mutation("POST", ["absence-reports", report_id, action], auth)
            payload = context.read_json()
            ident = int(report_id)
            service = context.absence_service
            result = {
                "select-replacement": lambda: service.select_replacement(
                    context.authorization_scope, ident, payload
                ),
                "withdraw": lambda: service.withdraw(context.authorization_scope, ident),
                "reopen": lambda: service.reopen(context.authorization_scope, ident, payload),
                "cancel": lambda: service.cancel(context.authorization_scope, ident, payload),
            }[action]()
            return _finish(context, context.respond(result))

        return endpoint

    for action in ("select-replacement", "withdraw", "reopen", "cancel"):
        app.add_api_route(
            f"/api/absence-reports/{{report_id}}/{action}",
            absence_action(action),
            methods=["POST"],
            name=f"absence_{action}",
        )

    @app.patch("/api/replacement-responses/{response_id}")
    def patch_response(request: Request, response_id: str):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated()
        context.authorize_mutation("PATCH", ["replacement-responses", response_id], auth)
        return _finish(
            context,
            context.respond(
                context.absence_service.respond(
                    context.authorization_scope, int(response_id), context.read_json()
                )
            ),
        )

    @app.post("/api/replacement-responses/{response_id}/respond")
    def post_response(request: Request, response_id: str):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated()
        context.authorize_mutation("POST", ["replacement-responses", response_id, "respond"], auth)
        return _finish(
            context,
            context.respond(
                context.absence_service.respond(
                    context.authorization_scope, int(response_id), context.read_json()
                )
            ),
        )

    @app.get("/api/scheduling-overview")
    def scheduling(request: Request):
        context = _context(request, resolved)
        require_read(context)
        return _finish(
            context,
            context.respond(
                hateoas.scheduling_overview(
                    context.repository.scheduling_overview(context.authorization_scope)
                )
            ),
        )

    @app.get("/api/confirmed-plans")
    def confirmed_plans(request: Request):
        context = _context(request, resolved)
        require_read(context)
        return _finish(
            context,
            context.respond(
                hateoas.confirmed_plans(
                    context.repository.confirmed_plans(context.authorization_scope)
                )
            ),
        )

    @app.get("/api/confirmed-plan-days/{id}")
    def confirmed_day(request: Request, id: str):
        context = _context(request, resolved)
        require_read(context)
        day = context.repository.confirmed_plan_day(int(id), context.authorization_scope)
        return (
            _not_found()
            if day is None
            else _finish(context, context.respond(hateoas.confirmed_plan_day(day)))
        )

    @app.post("/api/planning-proposals", status_code=201)
    def generate_proposal(request: Request):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated(require_csrf=True)
        context.authorize_mutation("POST", ["planning-proposals"], auth)
        round_id = int(context.read_json().get("round_id", 1))
        context.require_round_access(round_id, manage=True)
        return _finish(
            context,
            context.respond(
                hateoas.planning_proposal(context.planning_service.generate_proposal(round_id)),
                HTTPStatus.CREATED,
            ),
        )

    @app.get("/api/exam-rounds/{id}/planning-proposal")
    def get_proposal(request: Request, id: str):
        context = _context(request, resolved)
        context.require_authenticated()
        context.require_round_access(int(id), manage=True)
        proposal = context.planning_service.get_proposal(int(id))
        return _finish(
            context,
            context.respond(
                hateoas.editable_planning_proposal(
                    context.planning_service.proposal_payload(proposal)
                )
            ),
        )

    @app.put("/api/exam-rounds/{id}/planning-proposal")
    def save_proposal(request: Request, id: str):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated(require_csrf=True)
        context.authorize_mutation("PUT", ["exam-rounds", id, "planning-proposal"], auth)
        round_id = int(id)
        context.require_round_access(round_id, manage=True)
        saved = context.planning_service.save_proposal(
            planning_proposal_from_payload(round_id, context.read_json())
        )
        return _finish(
            context,
            context.respond(
                hateoas.editable_planning_proposal(context.planning_service.proposal_payload(saved))
            ),
        )

    @app.post("/api/exam-rounds/{id}/confirm-plan")
    def confirm_plan(request: Request, id: str):
        context = _context(request, resolved)
        auth = context.require_authenticated(require_csrf=True)
        context.authorize_mutation("POST", ["exam-rounds", id, "confirm-plan"], auth)
        round_id = int(id)
        context.require_round_access(round_id, manage=True)
        confirmed = context.planning_service.confirm_plan(round_id)
        try:
            context.calendar_service.sync_round(round_id)
        except Exception:
            emit_event("backend_error", severity="error", category="calendar_processing")
            confirmed["calendar_warning"] = (
                "Der Plan wurde bestätigt, aber die persönlichen Kalender konnten nicht "
                "vollständig vorbereitet werden."
            )
        warning = context.create_notifications_best_effort("plan_confirmed", round_id)
        if warning:
            confirmed["notification_warning"] = warning
        return _finish(context, context.respond(hateoas.confirmed_plan(confirmed)))

    @app.post("/api/candidate-exam-days/generate")
    def generate_days(request: Request):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated(require_csrf=True)
        context.authorize_mutation("POST", ["candidate-exam-days", "generate"], auth)
        round_id = int(context.read_json().get("round_id", 1))
        context.require_round_access(round_id, manage=True)
        return _finish(
            context,
            context.respond(
                hateoas.candidate_day_generation(context.candidate_day_service.generate(round_id)),
                HTTPStatus.OK,
            ),
        )

    @app.post("/api/exam-rounds/{id}/request-availabilities")
    def request_availabilities(request: Request, id: str):
        context = _context(request, resolved)
        auth = context.require_authenticated(require_csrf=True)
        context.authorize_mutation("POST", ["exam-rounds", id, "request-availabilities"], auth)
        round_id = int(id)
        context.require_round_access(round_id, manage=True)
        exam_round = context.planning_service.request_availabilities(round_id)
        warning = context.create_notifications_best_effort("availability_requested", round_id)
        if warning:
            exam_round["notification_warning"] = warning
        return _finish(
            context,
            context.respond(
                hateoas.resource_item("exam-rounds", REST_RESOURCES["exam-rounds"], exam_round)
            ),
        )

    def planning_resource_routes(resource_name: str):
        resource = REST_RESOURCES[resource_name]

        def get_collection(request: Request):
            context = _context(request, resolved)
            require_read(context)
            rows = context.repository.list_visible(
                resource,
                context.authorization_scope,
                context.resource_filters(resource, request.query_params),
            )
            return _finish(
                context,
                context.respond(
                    hateoas.collection(
                        resource_name,
                        resource,
                        rows,
                        request.url.query,
                        allow_create=False,
                        allow_item_mutation=False,
                    )
                ),
            )

        def get_item(request: Request, id: str):
            context = _context(request, resolved)
            require_read(context)
            row = context.repository.get_visible(resource, int(id), context.authorization_scope)
            return (
                _not_found()
                if row is None
                else _finish(
                    context,
                    context.respond(
                        hateoas.resource_item(
                            resource_name, resource, row, allow_item_mutation=False
                        )
                    ),
                )
            )

        return get_collection, get_item

    for name in MIGRATED_PLANNING_RESOURCES:
        get_collection, get_item = planning_resource_routes(name)
        app.add_api_route(
            f"/api/{name}",
            get_collection,
            methods=["GET"],
            name=f"get_planning_{name}",
            openapi_extra=read_security,
        )
        app.add_api_route(
            f"/api/{name}/{{id}}",
            get_item,
            methods=["GET"],
            name=f"get_planning_{name}_item",
            openapi_extra=read_security,
        )

    def aggregate_write(request: Request, id: str | None = None):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated(require_csrf=True)
        path_parts = request.url.path.removeprefix("/api/").strip("/").split("/")
        context.authorize_mutation(request.method, path_parts, auth)
        raise ValueError(
            "Exam days, slots, and assignments must be changed through the planning aggregate"
        )

    for name in ("exam-days", "exam-slots", "exam-day-assignments"):
        app.add_api_route(
            f"/api/{name}",
            aggregate_write,
            methods=["POST"],
            name=f"reject_create_{name}",
            include_in_schema=False,
        )
        app.add_api_route(
            f"/api/{name}/{{id}}",
            aggregate_write,
            methods=["PATCH", "DELETE"],
            name=f"reject_write_{name}",
            include_in_schema=False,
        )

    @app.post("/api/confirmed-plan-days/{day_id}/slots/{slot_id}/start")
    def start_slot(request: Request, day_id: str, slot_id: str):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated(require_csrf=True)
        context.authorize_mutation(
            "POST", ["confirmed-plan-days", day_id, "slots", slot_id, "start"], auth
        )
        day_int = int(day_id)
        context.require_day_access(day_int, manage=True)
        committee_id = context.repository.committee_id_for_resource(EXAM_DAY, day_int)
        actor_member_id = context.authorization_scope.member_for_committee(committee_id)
        if actor_member_id is None:
            raise ForbiddenRequestError("Forbidden.")
        context.repository.start_exam_slot(
            day_int,
            int(slot_id),
            context.read_json(),
            actor_member_id=actor_member_id,
        )
        day = context.repository.confirmed_plan_day(day_int, context.authorization_scope)
        return (
            _not_found()
            if day is None
            else _finish(context, context.respond(hateoas.confirmed_plan_day(day)))
        )

    @app.get(
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/protocol",
        openapi_extra=read_security,
    )
    def slot_protocol(request: Request, day_id: str, slot_id: str):
        context = _context(request, resolved)
        context.require_authenticated()
        slot = context.repository.get(EXAM_SLOT, int(slot_id))
        if slot is None or slot["exam_day_id"] != int(day_id):
            return _not_found()
        protocol = context.exam_protocol_service.get_by_slot(
            context.authorization_scope, int(slot_id)
        )
        return _not_found() if protocol is None else _finish(context, context.respond(protocol))

    @app.get("/api/exam-protocols/{protocol_id}", openapi_extra=read_security)
    def exam_protocol(request: Request, protocol_id: str):
        context = _context(request, resolved)
        context.require_authenticated()
        protocol = context.exam_protocol_service.get(context.authorization_scope, int(protocol_id))
        return _not_found() if protocol is None else _finish(context, context.respond(protocol))

    def protocol_write(
        request: Request,
        protocol_id: str,
        action: str,
        method: str,
    ) -> Response:
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated(require_csrf=True)
        path_parts = ["exam-protocols", protocol_id]
        if action != "content":
            path_parts.append(action)
        context.authorize_mutation(method, path_parts, auth)
        payload = context.read_json()
        service = context.exam_protocol_service
        if action == "content":
            result = service.update_content(context.authorization_scope, int(protocol_id), payload)
        elif action == "submit":
            result = service.submit(context.authorization_scope, int(protocol_id), payload)
        elif action == "responses":
            result = service.respond(context.authorization_scope, int(protocol_id), payload)
        elif action == "correction-requests":
            result = service.request_correction(
                context.authorization_scope, int(protocol_id), payload
            )
        elif action == "open-correction":
            result = service.open_correction(context.authorization_scope, int(protocol_id), payload)
        elif action == "retention":
            result = service.set_retention(context.authorization_scope, int(protocol_id), payload)
        else:  # pragma: no cover - only called by the explicit routes below
            raise ValueError("Unbekannte Protokollaktion")
        return _finish(context, context.respond(result))

    @app.patch("/api/exam-protocols/{protocol_id}", openapi_extra=write_security)
    def update_exam_protocol(request: Request, protocol_id: str):
        return protocol_write(request, protocol_id, "content", "PATCH")

    @app.post("/api/exam-protocols/{protocol_id}/submit", openapi_extra=write_security)
    def submit_exam_protocol(request: Request, protocol_id: str):
        return protocol_write(request, protocol_id, "submit", "POST")

    @app.post("/api/exam-protocols/{protocol_id}/responses", openapi_extra=write_security)
    def respond_to_exam_protocol(request: Request, protocol_id: str):
        return protocol_write(request, protocol_id, "responses", "POST")

    @app.post(
        "/api/exam-protocols/{protocol_id}/correction-requests",
        openapi_extra=write_security,
    )
    def request_exam_protocol_correction(request: Request, protocol_id: str):
        return protocol_write(request, protocol_id, "correction-requests", "POST")

    @app.post(
        "/api/exam-protocols/{protocol_id}/open-correction",
        openapi_extra=write_security,
    )
    def open_exam_protocol_correction(request: Request, protocol_id: str):
        return protocol_write(request, protocol_id, "open-correction", "POST")

    @app.put(
        "/api/exam-protocols/{protocol_id}/retention",
        openapi_extra=write_security,
    )
    def set_exam_protocol_retention(request: Request, protocol_id: str):
        return protocol_write(request, protocol_id, "retention", "PUT")

    @app.get(
        "/api/exam-protocols/{protocol_id}/export.json",
        openapi_extra=read_security,
    )
    def export_exam_protocol_json(request: Request, protocol_id: str):
        context = _context(request, resolved)
        context.require_authenticated()
        result = context.exam_protocol_service.machine_export(
            context.authorization_scope, int(protocol_id)
        )
        return _finish(context, context.respond(result))

    @app.get(
        "/api/exam-protocols/{protocol_id}/export.txt",
        response_class=Response,
        openapi_extra=read_security,
    )
    def export_exam_protocol_text(request: Request, protocol_id: str):
        context = _context(request, resolved)
        context.require_authenticated()
        result = context.exam_protocol_service.human_export(
            context.authorization_scope, int(protocol_id)
        )
        return _plain_text(context, result, f"pruefungsprotokoll-{int(protocol_id)}.txt")

    @app.get(
        "/api/confirmed-plan-days/{day_id}/protocol-completion",
        openapi_extra=read_security,
    )
    def protocol_completion(request: Request, day_id: str):
        context = _context(request, resolved)
        context.require_authenticated()
        result = context.exam_protocol_service.completion_for_day(
            context.authorization_scope, int(day_id)
        )
        return _not_found() if result is None else _finish(context, context.respond(result))

    def attendance(request: Request, day_id: str, entity_id: str, kind: str):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated(require_csrf=True)
        context.authorize_mutation(
            "PATCH", ["confirmed-plan-days", day_id, kind, entity_id, "attendance"], auth
        )
        day_int = int(day_id)
        entity_int = int(entity_id)
        member_id = None
        if kind == "assignments":
            assignment = context.repository.get(EXAM_DAY_ASSIGNMENT, entity_int)
            member_id = assignment.get("committee_member_id") if assignment else None
        context.require_day_access(day_int, manage=kind == "slots", member_id=member_id)
        payload = context.read_json()
        if kind == "slots":
            context.repository.save_candidate_attendance(day_int, entity_int, payload)
        else:
            context.repository.save_member_attendance(day_int, entity_int, payload)
        day = context.repository.confirmed_plan_day(day_int, context.authorization_scope)
        return (
            _not_found()
            if day is None
            else _finish(context, context.respond(hateoas.confirmed_plan_day(day)))
        )

    @app.patch("/api/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance")
    def slot_attendance(request: Request, day_id: str, slot_id: str):
        return attendance(request, day_id, slot_id, "slots")

    @app.patch("/api/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance")
    def assignment_attendance(request: Request, day_id: str, assignment_id: str):
        return attendance(request, day_id, assignment_id, "assignments")

    @app.patch("/api/confirmed-plan-days/{day_id}/slots/{slot_id}/status")
    def slot_status(request: Request, day_id: str, slot_id: str):
        context = _context(request, resolved, _body(request))
        auth = context.require_authenticated(require_csrf=True)
        context.authorize_mutation(
            "PATCH", ["confirmed-plan-days", day_id, "slots", slot_id, "status"], auth
        )
        day_int = int(day_id)
        context.require_day_access(day_int, manage=True)
        context.repository.update_exam_slot_status(day_int, int(slot_id), context.read_json())
        day_record = context.repository.get(EXAM_DAY, day_int)
        if day_record:
            try:
                context.calendar_service.sync_round(int(day_record["exam_round_id"]))
            except Exception:
                emit_event("backend_error", severity="error", category="calendar_processing")
        day = context.repository.confirmed_plan_day(day_int, context.authorization_scope)
        return (
            _not_found()
            if day is None
            else _finish(context, context.respond(hateoas.confirmed_plan_day(day)))
        )

    def resource_routes(resource_name: str):
        resource = REST_RESOURCES[resource_name]

        def get_collection(request: Request):
            context = _context(request, resolved)
            require_read(context)
            params = request.query_params
            if resource_name in {"members", "memberships"}:
                rows = context.repository.member_list(
                    context.resource_filters(resource, params), context.authorization_scope
                )
            elif resource_name == "candidates":
                rows = context.repository.candidate_list(context.authorization_scope)
            else:
                rows = context.repository.list_visible(
                    resource,
                    context.authorization_scope,
                    context.resource_filters(resource, params),
                )
            return _finish(
                context,
                context.respond(
                    hateoas.collection(
                        resource_name,
                        resource,
                        rows,
                        request.url.query,
                        allow_create=resource not in PLAN_AGGREGATE_RESOURCES,
                        allow_item_mutation=resource not in PLAN_AGGREGATE_RESOURCES,
                    )
                ),
            )

        def get_item(request: Request, id: str):
            context = _context(request, resolved)
            require_read(context)
            row = (
                context.repository.member_get(int(id), context.authorization_scope)
                if resource_name in {"members", "memberships"}
                else context.repository.get_visible(resource, int(id), context.authorization_scope)
            )
            return (
                _not_found()
                if row is None
                else _finish(
                    context,
                    context.respond(
                        hateoas.resource_item(
                            resource_name,
                            resource,
                            row,
                            allow_item_mutation=resource not in PLAN_AGGREGATE_RESOURCES,
                        )
                    ),
                )
            )

        def create(request: Request):
            context = _context(request, resolved, _body(request))
            auth = context.require_authenticated(require_csrf=True)
            context.authorize_mutation("POST", [resource_name], auth)
            payload = context.authorize_resource_action(
                resource_name, None, context.read_json(), "create"
            )
            status = HTTPStatus.CREATED
            if resource_name == "candidates":
                row = context.repository.create_candidate(payload)
            elif resource_name == "planning-settings":
                row = context.repository.save_planning_settings(payload)
                status = HTTPStatus.OK
            elif resource_name == "member-availabilities":
                row = context.repository.save_member_availability(payload)
                status = HTTPStatus.OK
            elif resource_name in {"members", "memberships"}:
                row = context.repository.create_membership(payload)
            else:
                row = context.repository.create(resource, payload)
            return _finish(
                context,
                context.respond(hateoas.resource_item(resource_name, resource, row), status),
            )

        def update(request: Request, id: str):
            context = _context(request, resolved, _body(request))
            auth = context.require_authenticated(require_csrf=True)
            context.authorize_mutation("PATCH", [resource_name, id], auth)
            ident = int(id)
            payload = context.authorize_resource_action(
                resource_name, ident, context.read_json(), "update"
            )
            if resource_name == "planning-settings":
                row = context.repository.update_planning_settings(ident, payload)
            elif resource_name == "member-availabilities":
                row = context.repository.update_member_availability(ident, payload)
            elif resource_name == "candidates":
                row = context.repository.update_candidate(ident, payload)
            elif resource_name == "exam-rounds":
                row = context.repository.update_exam_round(ident, payload)
            elif resource_name in {"members", "memberships"}:
                row = context.repository.update_membership(ident, payload)
            else:
                row = context.repository.update(resource, ident, payload)
            return (
                _not_found()
                if row is None
                else _finish(
                    context, context.respond(hateoas.resource_item(resource_name, resource, row))
                )
            )

        def delete(request: Request, id: str):
            context = _context(request, resolved)
            auth = context.require_authenticated(require_csrf=True)
            context.authorize_mutation("DELETE", [resource_name, id], auth)
            ident = int(id)
            context.authorize_resource_action(resource_name, ident, {}, "delete")
            deleted = (
                context.repository.delete_candidate(ident)
                if resource_name == "candidates"
                else context.repository.delete(resource, ident)
            )
            return (
                _not_found()
                if not deleted
                else _finish(context, context.respond({}, HTTPStatus.NO_CONTENT))
            )

        return get_collection, get_item, create, update, delete

    for name in MIGRATED_DOMAIN_RESOURCES:
        get_collection, get_item, create, update, delete = resource_routes(name)
        app.add_api_route(
            f"/api/{name}",
            get_collection,
            methods=["GET"],
            name=f"get_{name}",
            openapi_extra=read_security,
        )
        app.add_api_route(
            f"/api/{name}/{{id}}",
            get_item,
            methods=["GET"],
            name=f"get_{name}_item",
            openapi_extra=read_security,
        )
        app.add_api_route(
            f"/api/{name}",
            create,
            methods=["POST"],
            name=f"create_{name}",
            openapi_extra=write_security,
        )
        app.add_api_route(
            f"/api/{name}/{{id}}",
            update,
            methods=["PATCH"],
            name=f"update_{name}",
            openapi_extra=write_security,
        )
        app.add_api_route(
            f"/api/{name}/{{id}}",
            delete,
            methods=["DELETE"],
            status_code=204,
            name=f"delete_{name}",
            openapi_extra=write_security,
        )

    _get, _item, candidate_create, candidate_update, candidate_delete = resource_routes(
        "candidate-exam-days"
    )
    app.add_api_route(
        "/api/candidate-exam-days",
        candidate_create,
        methods=["POST"],
        name="create_candidate_exam_days",
        openapi_extra=write_security,
    )
    app.add_api_route(
        "/api/candidate-exam-days/{id}",
        candidate_update,
        methods=["PATCH"],
        name="update_candidate_exam_days",
        openapi_extra=write_security,
    )
    app.add_api_route(
        "/api/candidate-exam-days/{id}",
        candidate_delete,
        methods=["DELETE"],
        status_code=204,
        name="delete_candidate_exam_days",
        openapi_extra=write_security,
    )

    @app.get("/api/candidate-committee-assignments")
    def assignment_collection(request: Request):
        context = _context(request, resolved)
        require_read(context)
        value = request.query_params.get("candidate_id")
        rows = context.repository.candidate_committee_assignments(
            int(value) if value is not None else None, context.authorization_scope
        )
        return _finish(
            context,
            context.respond(
                hateoas.collection(
                    "candidate-committee-assignments",
                    CANDIDATE_COMMITTEE_ASSIGNMENT,
                    rows,
                    request.url.query,
                    allow_create=False,
                    allow_item_mutation=False,
                )
            ),
        )

    @app.get("/api/candidate-committee-assignments/{id}")
    def assignment_item(request: Request, id: str):
        context = _context(request, resolved)
        require_read(context)
        row = context.repository.get_visible(
            CANDIDATE_COMMITTEE_ASSIGNMENT, int(id), context.authorization_scope
        )
        return (
            _not_found()
            if row is None
            else _finish(
                context,
                context.respond(
                    hateoas.resource_item(
                        "candidate-committee-assignments",
                        CANDIDATE_COMMITTEE_ASSIGNMENT,
                        row,
                        allow_item_mutation=False,
                    )
                ),
            )
        )

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def static_or_not_found(request: Request, path: str):
        return (
            _static_response(resolved, request)
            if not _is_api_path(request.url.path)
            else _not_found()
        )

    original_openapi = app.openapi
    public_paths = {
        "/api/health",
        "/api/ready",
        "/api/auth/login",
        "/api/auth/invitation/prepare",
        "/api/auth/invitation/activate",
        "/api/auth/recovery/prepare",
        "/api/auth/recovery/complete",
        "/api/observability/frontend-errors",
        "/api/calendar/feed/{token}.ics",
        "/api/calendar/events/{id}.ics",
    }

    def generated_openapi() -> dict:
        document = original_openapi()
        schemas = document.setdefault("components", {}).setdefault("schemas", {})
        schemas.setdefault(
            "JsonObject",
            {"type": "object", "additionalProperties": True},
        )
        schemas.setdefault(
            "ErrorResponse",
            {
                "type": "object",
                "properties": {"error": {}},
                "required": ["error"],
                "additionalProperties": True,
            },
        )
        for path, path_item in document.get("paths", {}).items():
            if path in public_paths:
                continue
            for method, operation in path_item.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                operation["security"] = [
                    (
                        {"sessionCookie": [], "csrfHeader": []}
                        if method in {"post", "put", "patch", "delete"}
                        else {"sessionCookie": []}
                    )
                ]
                responses = operation.setdefault("responses", {})
                for status in (
                    "400",
                    "401",
                    "403",
                    "404",
                    "409",
                    "413",
                    "415",
                    "422",
                    "429",
                    "500",
                ):
                    responses.setdefault(
                        status,
                        {
                            "description": "Application error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    )
                for status in ("200", "201", "202"):
                    response = responses.setdefault(
                        status,
                        {
                            "description": "Successful response",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/JsonObject"}
                                }
                            },
                        },
                    )
                    if "content" not in response:
                        response["content"] = {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/JsonObject"}
                            }
                        }
        return document

    app.openapi = generated_openapi

    return app
