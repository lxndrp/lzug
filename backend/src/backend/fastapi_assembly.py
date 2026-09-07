"""Canonical FastAPI application assembly for product and demo runtimes."""

from __future__ import annotations

from datetime import timedelta

from fastapi import FastAPI

from .application import ApplicationServices, ReadApplication
from .fastapi_app import (
    FastAPIConfig,
    register_application_routes,
    register_openapi_schema,
    register_transport_and_errors,
)
from .security import RequestRateLimiter

__all__ = ["FastAPIConfig", "create_app"]


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
    read_security: dict[str, object] = {"security": [{"sessionCookie": []}]}
    write_security: dict[str, object] = {"security": [{"sessionCookie": [], "csrfHeader": []}]}

    def venue_write_openapi(model_name: str) -> dict[str, object]:
        return {
            **write_security,
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{model_name}"}}
                },
            },
        }

    registration = (
        register_transport_and_errors,
        register_application_routes,
        register_openapi_schema,
    )
    for registrar in registration:
        registrar(
            app,
            resolved,
            application,
            read_security,
            write_security,
            venue_write_openapi,
        )

    return app
