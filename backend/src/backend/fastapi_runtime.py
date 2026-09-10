"""ASGI admission adapter; state and persistence ownership remain in the runtime."""

from __future__ import annotations

import asyncio
from http import HTTPStatus

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .public_lifecycle import unavailable_payload
from .runtime import RuntimeConflictError, RuntimeCoordinator


class RuntimeAdmissionMiddleware:
    """Keep an admission until the entire ASGI call, including cleanup, exits."""

    def __init__(self, app: ASGIApp, runtime: RuntimeCoordinator) -> None:
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["path"] in {"/api/health", "/api/ready", "/api/lifecycle"}
            or (
                scope.get("method") in {"GET", "HEAD"}
                and scope["path"] != "/api"
                and not scope["path"].startswith("/api/")
            )
        ):
            await self.app(scope, receive, send)
            return
        admission = self.runtime.admit()
        try:
            admission.__enter__()
        except RuntimeConflictError as error:
            await JSONResponse(
                unavailable_payload({"state": error.state, "ready": False}),
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)
            return
        try:
            # Cancellation must not abandon a service worker between database
            # transactions or while it is still accessing document storage.
            execution = asyncio.ensure_future(self.app(scope, receive, send))
            try:
                await asyncio.shield(execution)
            except asyncio.CancelledError:
                while not execution.done():
                    try:
                        await asyncio.shield(execution)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not execution.cancelled():
                    execution.exception()
                raise
        finally:
            admission.__exit__(None, None, None)
