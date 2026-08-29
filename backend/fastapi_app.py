"""Opt-in FastAPI application factory for the incremental HTTP migration."""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .application import (
    ApplicationResult,
    ApplicationServices,
    AuthenticationRequiredError,
    ForbiddenRequestError,
    ReadApplication,
    database_error_result,
)
from .database import database_path
from .security import RuntimeSecurityConfig


@dataclass(frozen=True)
class FastAPIConfig:
    """Startup configuration kept separate from database and service dependencies."""

    db_path: Path
    session_cookie_name: str

    @classmethod
    def from_environment(cls) -> FastAPIConfig:
        """Resolve the same database and cookie configuration as the product adapter."""
        security = RuntimeSecurityConfig.from_environment()
        return cls(
            db_path=database_path(),
            session_cookie_name=("__Host-lzug_session" if security.https_only else "lzug_session"),
        )


def _json_response(result: ApplicationResult) -> JSONResponse:
    return JSONResponse(
        content=result.payload,
        status_code=int(result.status),
        headers={"Cache-Control": "no-store"},
    )


def create_app(
    config: FastAPIConfig | None = None,
    services: ApplicationServices | None = None,
) -> FastAPI:
    """Create the explicitly started synchronous FastAPI migration core."""
    resolved_config = config or FastAPIConfig.from_environment()
    application = ReadApplication(resolved_config.db_path, services)
    app = FastAPI(
        title="lzug FastAPI migration core",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.lzug_config = resolved_config

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

    @app.get("/api/health", include_in_schema=False)
    def health() -> JSONResponse:
        return _json_response(application.health())

    @app.get("/api/ready", include_in_schema=False)
    def readiness() -> JSONResponse:
        return _json_response(application.readiness())

    @app.get("/api/round-summary", include_in_schema=False)
    def round_summary(request: Request) -> JSONResponse:
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

    return app
