"""ASGI admission adapter; state and persistence ownership remain in the runtime."""

from __future__ import annotations

from http import HTTPStatus

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .runtime import RuntimeConflictError, RuntimeCoordinator


class RuntimeAdmissionMiddleware:
    """Keep an admission until the entire ASGI call, including cleanup, exits."""

    def __init__(self, app: ASGIApp, runtime: RuntimeCoordinator) -> None:
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in {"/api/health", "/api/ready"}:
            await self.app(scope, receive, send)
            return
        admission = self.runtime.admit()
        try:
            admission.__enter__()
        except RuntimeConflictError:
            await JSONResponse(
                {"error": "Runtime is not ready."},
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            admission.__exit__(None, None, None)
