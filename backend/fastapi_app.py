"""Opt-in FastAPI application factory for the incremental HTTP migration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from .app import LzugHandler
from .application import (
    ApplicationResult,
    ApplicationServices,
    AuthenticationRequiredError,
    ForbiddenRequestError,
    ReadApplication,
    database_error_result,
)
from .database import database_path
from .runtime_policy import ProductRuntimePolicy, RuntimePolicy
from .security import RequestRateLimiter, RuntimeSecurityConfig


class ErrorResponse(BaseModel):
    """Stable error envelope exposed by the migrated transport routes."""

    error: str


class HealthResponse(BaseModel):
    """Minimal liveness or readiness response without domain diagnostics."""

    status: str
    version: str
    revision: str
    links: dict[str, object] = Field(alias="_links")


class ApiRootResponse(BaseModel):
    """Typed source fragment for the authenticated API entry point."""

    version: str
    links: dict[str, object] = Field(alias="_links")


class LoginRequest(BaseModel):
    """Credentials accepted by the local product login flow."""

    email: str = ""
    password: str = ""
    second_factor: str = ""


class TokenRequest(BaseModel):
    """One invitation or recovery token supplied by an unauthenticated client."""

    token: str = ""


class FactorActivationRequest(BaseModel):
    """Initial factor material for invitation activation or recovery completion."""

    token: str = ""
    password: str = ""
    totp_secret: str = ""
    totp_code: str = ""


class FrontendErrorRequest(BaseModel):
    """Coarse, non-sensitive frontend failure classification."""

    kind: str
    status: int | None = None


class SessionResponse(BaseModel):
    """Authenticated session view whose concrete capability fields remain assembly-owned."""

    authenticated: bool
    account_id: int
    person_id: int | None
    committee_member_id: int | None
    is_operator: bool


class SessionRotationResponse(BaseModel):
    """Response returned after server-side session rotation."""

    status: str
    expires_at: str


class DomainResourceWrite(BaseModel):
    """Shared transport shape; repositories remain the validation authority."""

    model_config = ConfigDict(extra="allow")


class DomainResourceResponse(BaseModel):
    """Common HAL-compatible response envelope for migrated domain resources."""

    model_config = ConfigDict(extra="allow")


class DomainCollectionResponse(BaseModel):
    """Common HAL-compatible collection response for migrated domain resources."""

    items: list[DomainResourceResponse]
    links: dict[str, object] = Field(alias="_links")


# #475 owns only the generic master, organisation, and round setup routes.  The
# planning aggregates are deliberately retained for #476, where their aggregate
# invariants can be migrated together.
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

# #476 moves the complete planning aggregate as one transport slice.  The
# aggregate's persistence and revision rules deliberately remain in the
# synchronous planning and repository services behind the reference handler.
MIGRATED_PLANNING_RESOURCES = (
    "candidate-exam-days",
    "exam-days",
    "exam-slots",
    "exam-day-assignments",
)


_DOMAIN_READ_ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}
_DOMAIN_WRITE_ERRORS = {
    **_DOMAIN_READ_ERRORS,
    400: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


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

    @classmethod
    def from_environment(cls) -> FastAPIConfig:
        """Resolve the same database and cookie configuration as the product adapter."""
        security = RuntimeSecurityConfig.from_environment()
        return cls(
            db_path=database_path(),
            session_cookie_name=("__Host-lzug_session" if security.https_only else "lzug_session"),
            cookie_secure=security.https_only,
            https_only=security.https_only,
            cors_allowed_origins=security.cors_allowed_origins,
            max_request_bytes=security.max_request_bytes,
            session_ttl=security.session_ttl,
            static_dir=(
                Path(os.environ["LZUG_STATIC_DIR"]) if os.environ.get("LZUG_STATIC_DIR") else None
            ),
        )


def _json_response(result: ApplicationResult) -> JSONResponse:
    return JSONResponse(
        content=result.payload,
        status_code=int(result.status),
        headers={
            "Cache-Control": "no-store",
            "Content-Type": "application/json; charset=utf-8",
        },
    )


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
    origin_authority = _normalized_authority(origin)
    if origin_authority is None:
        return False
    scheme, hostname, port = origin_authority
    host_authority = _normalized_authority(request.headers.get("Host", ""), scheme=scheme)
    return host_authority == (scheme, hostname, port)


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
                {"error": "Cross-origin request is not allowed."},
                HTTPStatus.FORBIDDEN,
            )
        )
    elif request.method == "OPTIONS":
        if not _is_api_path(request.url.path) or not origin:
            response = _json_response(
                ApplicationResult({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            )
        elif origin not in config.cors_allowed_origins and not _same_origin(request, origin):
            response = _json_response(
                ApplicationResult(
                    {"error": "Cross-origin request is not allowed."},
                    HTTPStatus.FORBIDDEN,
                )
            )
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
        if request.headers.get("Transfer-Encoding"):
            response = _json_response(
                ApplicationResult(
                    {"error": "Transfer-Encoding is not supported"}, HTTPStatus.BAD_REQUEST
                )
            )
        else:
            content_length = request.headers.get("Content-Length")
            if content_length is not None:
                try:
                    length = int(content_length)
                except ValueError:
                    response = _json_response(
                        ApplicationResult(
                            {"error": "Invalid Content-Length"}, HTTPStatus.BAD_REQUEST
                        )
                    )
                else:
                    if length < 0:
                        response = _json_response(
                            ApplicationResult(
                                {"error": "Invalid Content-Length"}, HTTPStatus.BAD_REQUEST
                            )
                        )
                    elif length > config.max_request_bytes:
                        response = _json_response(
                            ApplicationResult(
                                {
                                    "error": (
                                        f"Request body exceeds {config.max_request_bytes} bytes."
                                    )
                                },
                                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                            )
                        )
                    else:
                        response = await call_next(request)
            else:
                response = await call_next(request)

    for name, value in _security_headers(config, request).items():
        if name.lower() not in response.headers:
            response.headers[name] = value
    if "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


class _BridgeSocket:
    def __init__(self, request: bytes):
        self.input = BytesIO(request)
        self.output = BytesIO()

    def makefile(self, mode: str, *_args, **_kwargs):
        return self.input if "r" in mode else self.output

    def sendall(self, data: bytes) -> None:
        self.output.write(data)


class _BridgeServer:
    server_name = "127.0.0.1"
    server_port = 80


def _legacy_response(handler_type: type[LzugHandler], request: Request, body: bytes) -> Response:
    raw_path = request.scope.get("raw_path", request.url.path.encode("ascii"))
    query = request.scope.get("query_string", b"")
    target = raw_path + (b"?" + query if query else b"")
    header_lines = []
    for name, value in request.headers.raw:
        header_lines.append(name + b": " + value + b"\r\n")
    if body and not request.headers.get("Content-Length"):
        header_lines.append(f"Content-Length: {len(body)}\r\n".encode("ascii"))
    raw_request = (
        request.method.encode("ascii")
        + b" "
        + target
        + b" HTTP/1.1\r\n"
        + b"".join(header_lines)
        + b"\r\n"
        + body
    )
    socket = _BridgeSocket(raw_request)
    handler_type(socket, ("127.0.0.1", 12345), _BridgeServer())
    raw_response = socket.output.getvalue()
    header_bytes, _, response_body = raw_response.partition(b"\r\n\r\n")
    status_line, _, header_block = header_bytes.partition(b"\r\n")
    status = int(status_line.split()[1])
    response = Response(content=response_body, status_code=status)
    response_headers = []
    for header_line in header_block.split(b"\r\n"):
        if b":" not in header_line:
            continue
        name, value = header_line.split(b":", 1)
        if name.lower() != b"content-length":
            response_headers.append((name.lower(), value.lstrip()))
    response.raw_headers = response_headers
    return response


async def _request_body(request: Request) -> bytes:
    """Read an ASGI body while keeping migrated endpoint functions synchronous."""
    return await request.body()


def _legacy_route_response(
    handler_type: type[LzugHandler], request: Request, body: bytes = b""
) -> Response:
    """Run the retained reference handler behind one explicitly migrated route.

    The FastAPI route owns matching, generated OpenAPI metadata and the ASGI
    transport boundary.  The legacy handler remains the deliberately temporary
    implementation reference for this migration slice; later issues replace
    these small bridges with application-flow calls before the final adapter
    removal.
    """
    return _legacy_response(handler_type, request, body)


def create_app(
    config: FastAPIConfig | None = None,
    services: ApplicationServices | None = None,
    *,
    include_legacy_routes: bool = False,
) -> FastAPI:
    """Create the synchronous migration core with an optional legacy route bridge."""
    resolved_config = config or FastAPIConfig.from_environment()
    application = ReadApplication(resolved_config.db_path, services)
    app = FastAPI(
        title="lzug FastAPI migration core",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.lzug_config = resolved_config

    @app.middleware("http")
    async def transport_guard(request: Request, call_next):
        return await _transport_guard(request, call_next, resolved_config)

    @app.exception_handler(AuthenticationRequiredError)
    def authentication_required(
        _request: Request, _error: AuthenticationRequiredError
    ) -> JSONResponse:
        return _json_response(
            ApplicationResult(
                {"error": "Authentication required."},
                status=HTTPStatus.UNAUTHORIZED,
            )
        )

    @app.exception_handler(ForbiddenRequestError)
    def forbidden(_request: Request, error: ForbiddenRequestError) -> JSONResponse:
        return _json_response(
            ApplicationResult(
                {"error": str(error)},
                status=HTTPStatus.FORBIDDEN,
            )
        )

    @app.exception_handler(SQLAlchemyError)
    def database_error(_request: Request, error: SQLAlchemyError) -> JSONResponse:
        return _json_response(database_error_result(error))

    class LegacyReferenceHandler(LzugHandler):
        """Keep the old adapter available as the contractual comparison reference."""

        db_path = resolved_config.db_path
        static_dir = resolved_config.static_dir
        cookie_secure = resolved_config.cookie_secure
        https_only = resolved_config.https_only
        session_cookie_name = resolved_config.session_cookie_name
        csrf_cookie_name = resolved_config.csrf_cookie_name
        cors_allowed_origins = resolved_config.cors_allowed_origins
        session_ttl = resolved_config.session_ttl
        max_request_bytes = resolved_config.max_request_bytes
        auth_rate_limiter = RequestRateLimiter(20, timedelta(minutes=1))
        observability_rate_limiter = RequestRateLimiter(30, timedelta(minutes=1))
        observability_global_rate_limiter = RequestRateLimiter(120, timedelta(minutes=1))
        runtime_policy = resolved_config.runtime_policy

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> JSONResponse:
        return _json_response(application.health())

    @app.get(
        "/api/ready",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
    )
    def readiness() -> JSONResponse:
        return _json_response(application.readiness())

    @app.get(
        "/api/round-summary",
        response_model=dict[str, object],
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
        openapi_extra={"security": [{"sessionCookie": []}]},
    )
    def round_summary(
        request: Request,
        _round_id: str | None = Query(default=None, json_schema_extra={"type": "integer"}),
    ) -> JSONResponse:
        values = [value for value in request.query_params.getlist("round_id") if value]
        try:
            round_id = int(values[0] if values else "1")
        except ValueError:
            return _json_response(
                ApplicationResult(
                    {"error": "Invalid request"},
                    status=HTTPStatus.BAD_REQUEST,
                )
            )
        scope = application.authenticated_scope(
            request.cookies.get(resolved_config.session_cookie_name)
        )
        return _json_response(application.round_summary(scope, round_id))

    @app.get(
        "/api",
        response_model=ApiRootResponse,
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
        openapi_extra={"security": [{"sessionCookie": []}]},
    )
    def api_root(request: Request) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request)

    @app.get(
        "/api/openapi.json",
        response_model=dict[str, object],
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
        openapi_extra={"security": [{"sessionCookie": []}]},
    )
    def openapi_document(request: Request) -> Response:
        """Serve the full legacy reference until all route fragments are migrated."""
        return _legacy_route_response(LegacyReferenceHandler, request)

    @app.get(
        "/api/docs",
        response_class=Response,
        openapi_extra={"security": [{"sessionCookie": []}]},
    )
    def api_docs(request: Request) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request)

    @app.post(
        "/api/auth/login",
        response_model=dict[str, object],
        responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": LoginRequest.model_json_schema()}},
            }
        },
    )
    def login(request: Request, body: bytes = Depends(_request_body)) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request, body)

    @app.post(
        "/api/auth/invitation/prepare",
        response_model=dict[str, object],
        responses={400: {"model": ErrorResponse}},
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": TokenRequest.model_json_schema()}},
            }
        },
    )
    def prepare_invitation(request: Request, body: bytes = Depends(_request_body)) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request, body)

    @app.post(
        "/api/auth/invitation/activate",
        response_model=dict[str, object],
        responses={400: {"model": ErrorResponse}},
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": FactorActivationRequest.model_json_schema()}
                },
            }
        },
    )
    def activate_invitation(request: Request, body: bytes = Depends(_request_body)) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request, body)

    @app.post(
        "/api/auth/recovery/prepare",
        response_model=dict[str, object],
        responses={400: {"model": ErrorResponse}},
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": TokenRequest.model_json_schema()}},
            }
        },
    )
    def prepare_recovery(request: Request, body: bytes = Depends(_request_body)) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request, body)

    @app.post(
        "/api/auth/recovery/complete",
        response_model=dict[str, object],
        responses={400: {"model": ErrorResponse}},
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": FactorActivationRequest.model_json_schema()}
                },
            }
        },
    )
    def complete_recovery(request: Request, body: bytes = Depends(_request_body)) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request, body)

    @app.get(
        "/api/session",
        response_model=SessionResponse,
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
        openapi_extra={"security": [{"sessionCookie": []}]},
    )
    def session(request: Request) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request)

    @app.post(
        "/api/session/rotate",
        response_model=SessionRotationResponse,
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
        openapi_extra={"security": [{"sessionCookie": [], "csrfHeader": []}]},
    )
    def rotate_session(request: Request, body: bytes = Depends(_request_body)) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request, body)

    @app.post(
        "/api/session/logout",
        status_code=HTTPStatus.NO_CONTENT,
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
        openapi_extra={"security": [{"sessionCookie": [], "csrfHeader": []}]},
    )
    def logout_session(request: Request, body: bytes = Depends(_request_body)) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request, body)

    @app.post(
        "/api/observability/frontend-errors",
        status_code=HTTPStatus.ACCEPTED,
        responses={
            400: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            413: {"model": ErrorResponse},
            415: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": FrontendErrorRequest.model_json_schema()}
                },
            }
        },
    )
    def frontend_error(request: Request, body: bytes = Depends(_request_body)) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request, body)

    # Planning and execution operations keep their aggregate transaction,
    # optimistic revision, authorization, and best-effort integration behavior
    # in the existing services while FastAPI owns route matching and OpenAPI.
    def planning_read(request: Request) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request)

    def planning_write(request: Request, body: bytes = Depends(_request_body)) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request, body)

    planning_read_extra = {"security": [{"sessionCookie": []}]}
    planning_proposal_read_errors = {**_DOMAIN_READ_ERRORS, 409: {"model": ErrorResponse}}
    planning_write_extra = {
        "security": [{"sessionCookie": [], "csrfHeader": []}],
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": DomainResourceWrite.model_json_schema()}},
        },
    }

    for path, response_model in (
        ("/api/scheduling-overview", DomainCollectionResponse),
        ("/api/confirmed-plans", DomainCollectionResponse),
        ("/api/confirmed-plan-days/{id}", DomainResourceResponse),
    ):
        app.add_api_route(
            path,
            planning_read,
            methods=["GET"],
            response_model=response_model,
            responses=_DOMAIN_READ_ERRORS,
            openapi_extra=planning_read_extra,
        )

    app.add_api_route(
        "/api/planning-proposals",
        planning_write,
        methods=["POST"],
        status_code=HTTPStatus.CREATED,
        response_model=DomainResourceResponse,
        responses=_DOMAIN_WRITE_ERRORS,
        openapi_extra=planning_write_extra,
    )
    app.add_api_route(
        "/api/candidate-exam-days/generate",
        planning_write,
        methods=["POST"],
        response_model=DomainResourceResponse,
        responses=_DOMAIN_WRITE_ERRORS,
        openapi_extra=planning_write_extra,
    )
    app.add_api_route(
        "/api/exam-rounds/{id}/planning-proposal",
        planning_read,
        methods=["GET"],
        response_model=DomainResourceResponse,
        responses=planning_proposal_read_errors,
        openapi_extra=planning_read_extra,
    )
    app.add_api_route(
        "/api/exam-rounds/{id}/planning-proposal",
        planning_write,
        methods=["PUT"],
        response_model=DomainResourceResponse,
        responses=_DOMAIN_WRITE_ERRORS,
        openapi_extra=planning_write_extra,
    )
    app.add_api_route(
        "/api/exam-rounds/{id}/confirm-plan",
        planning_write,
        methods=["POST"],
        response_model=DomainResourceResponse,
        responses=_DOMAIN_WRITE_ERRORS,
        openapi_extra=planning_write_extra,
    )

    for path in (
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance",
        "/api/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance",
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/status",
    ):
        app.add_api_route(
            path,
            planning_write,
            methods=["PATCH"],
            response_model=DomainResourceResponse,
            responses=_DOMAIN_WRITE_ERRORS,
            openapi_extra=planning_write_extra,
        )
    app.add_api_route(
        "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/start",
        planning_write,
        methods=["POST"],
        response_model=DomainResourceResponse,
        responses=_DOMAIN_WRITE_ERRORS,
        openapi_extra=planning_write_extra,
    )

    # Generic domain validation, authorization, transaction handling, and HAL
    # assembly stay in the repository-backed reference handler while this slice
    # owns the FastAPI route matching and generated OpenAPI fragments.
    def domain_read(request: Request) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request)

    def domain_write(request: Request, body: bytes = Depends(_request_body)) -> Response:
        return _legacy_route_response(LegacyReferenceHandler, request, body)

    domain_read_extra = {"security": [{"sessionCookie": []}]}
    domain_write_extra = {
        "security": [{"sessionCookie": [], "csrfHeader": []}],
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": DomainResourceWrite.model_json_schema()}},
        },
    }

    for resource_name in MIGRATED_DOMAIN_RESOURCES:
        collection_path = f"/api/{resource_name}"
        item_path = f"{collection_path}/{{id}}"
        app.add_api_route(
            collection_path,
            domain_read,
            methods=["GET"],
            response_model=DomainCollectionResponse,
            responses=_DOMAIN_READ_ERRORS,
            openapi_extra=domain_read_extra,
        )
        app.add_api_route(
            collection_path,
            domain_write,
            methods=["POST"],
            response_model=DomainResourceResponse,
            responses={
                **_DOMAIN_WRITE_ERRORS,
                200: {"model": DomainResourceResponse},
                201: {"model": DomainResourceResponse},
            },
            openapi_extra=domain_write_extra,
        )
        app.add_api_route(
            item_path,
            domain_read,
            methods=["GET"],
            response_model=DomainResourceResponse,
            responses=_DOMAIN_READ_ERRORS,
            openapi_extra=domain_read_extra,
        )
        app.add_api_route(
            item_path,
            domain_write,
            methods=["PATCH"],
            response_model=DomainResourceResponse,
            responses={**_DOMAIN_WRITE_ERRORS, 200: {"model": DomainResourceResponse}},
            openapi_extra=domain_write_extra,
        )
        app.add_api_route(
            item_path,
            domain_write,
            methods=["DELETE"],
            status_code=HTTPStatus.NO_CONTENT,
            response_model=None,
            responses=_DOMAIN_WRITE_ERRORS,
            openapi_extra={"security": [{"sessionCookie": [], "csrfHeader": []}]},
        )

    for resource_name in MIGRATED_PLANNING_RESOURCES:
        collection_path = f"/api/{resource_name}"
        item_path = f"{collection_path}/{{id}}"
        app.add_api_route(
            collection_path,
            planning_read,
            methods=["GET"],
            response_model=DomainCollectionResponse,
            responses=_DOMAIN_READ_ERRORS,
            openapi_extra=planning_read_extra,
        )
        app.add_api_route(
            item_path,
            planning_read,
            methods=["GET"],
            response_model=DomainResourceResponse,
            responses=_DOMAIN_READ_ERRORS,
            openapi_extra=planning_read_extra,
        )
        if resource_name == "candidate-exam-days":
            app.add_api_route(
                collection_path,
                planning_write,
                methods=["POST"],
                response_model=DomainResourceResponse,
                responses={
                    **_DOMAIN_WRITE_ERRORS,
                    200: {"model": DomainResourceResponse},
                    201: {"model": DomainResourceResponse},
                },
                openapi_extra=planning_write_extra,
            )
            app.add_api_route(
                item_path,
                planning_write,
                methods=["PATCH"],
                response_model=DomainResourceResponse,
                responses={**_DOMAIN_WRITE_ERRORS, 200: {"model": DomainResourceResponse}},
                openapi_extra=planning_write_extra,
            )
            app.add_api_route(
                item_path,
                planning_write,
                methods=["DELETE"],
                status_code=HTTPStatus.NO_CONTENT,
                response_model=None,
                responses=_DOMAIN_WRITE_ERRORS,
                openapi_extra={"security": [{"sessionCookie": [], "csrfHeader": []}]},
            )

    for path, response_model in (
        ("/api/candidate-committee-assignments", DomainCollectionResponse),
        ("/api/candidate-committee-assignments/{id}", DomainResourceResponse),
    ):
        app.add_api_route(
            path,
            domain_read,
            methods=["GET"],
            response_model=response_model,
            responses=_DOMAIN_READ_ERRORS,
            openapi_extra=domain_read_extra,
        )

    if include_legacy_routes:

        @app.api_route(
            "/{path:path}",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
            include_in_schema=False,
        )
        def legacy_route(request: Request, body: bytes = Depends(_request_body)) -> Response:
            return _legacy_route_response(LegacyReferenceHandler, request, body)

    return app
