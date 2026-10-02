"""Shared FastAPI contract, response, and same-origin transport helpers."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from backend.application.transport import RequestContext

from .api_contracts import ErrorResponse, RuntimeUnavailableResponse
from .application import ApplicationResult

APPLICATION_ERROR_RESPONSES: dict[int, dict[str, object]] = {
    int(status): {"description": "Application error", "model": ErrorResponse}
    for status in (
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.CONFLICT,
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
        HTTPStatus.UNPROCESSABLE_ENTITY,
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.INTERNAL_SERVER_ERROR,
    )
}
APPLICATION_ERROR_RESPONSES[503] = {
    "description": "Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.",
    "model": RuntimeUnavailableResponse,
}


def json_response(result: ApplicationResult, context: RequestContext | None = None) -> Response:
    """Render one framework-independent result with FastAPI's JSON response."""
    if result.status == HTTPStatus.NO_CONTENT:
        response: Response = Response(status_code=int(result.status))
    else:
        response = JSONResponse(
            content=result.payload,
            status_code=int(result.status),
            headers={"Cache-Control": "no-store"},
        )
    if context is not None:
        for name, value in context.response_headers:
            response.raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))
    return response


def payload_data[PayloadModel: BaseModel](
    _context: RequestContext,
    payload: PayloadModel,
    *,
    exclude_unset: bool = True,
) -> dict[str, Any]:
    """Convert FastAPI's validated model to the established application payload.

    Pydantic owns parsing, field validation and compatibility aliases at the
    request boundary. Application commands receive only declared model data.
    """
    return payload.model_dump(exclude_unset=exclude_unset)


def not_found() -> Response:
    """Return the stable API not-found envelope."""
    return json_response(ApplicationResult({"error": "Not found"}, HTTPStatus.NOT_FOUND))


def finish(context: RequestContext, result: ApplicationResult | None = None) -> Any | Response:
    """Finish a request while preserving FastAPI validation on declared success models.

    An explicitly declared response model is the transport boundary: return its
    ordinary payload so FastAPI validates and serializes it. Non-success status
    codes and routes without a declared model retain the established response
    adapter, including application-owned headers.
    """
    resolved = result or context.response_result or ApplicationResult({})
    route = context.request.scope.get("route")
    expected_status = getattr(route, "status_code", None) or HTTPStatus.OK
    if (
        getattr(route, "response_model", None) is not None
        and int(resolved.status) == expected_status
        and 200 <= int(resolved.status) < 300
    ):
        context.request.state.lzug_response_headers = tuple(context.response_headers)
        return resolved.payload
    return json_response(resolved, context)


def calendar_text(context: RequestContext, value: str) -> Response:
    """Return a personal calendar attachment with transport headers."""
    response = Response(
        value, media_type="text/calendar; charset=utf-8", headers={"Cache-Control": "no-store"}
    )
    response.headers["Content-Disposition"] = "attachment; filename=pruefungstermine.ics"
    _append_context_headers(response, context)
    return response


def plain_text(context: RequestContext, value: str, filename: str) -> Response:
    """Return a named plain-text attachment with transport headers."""
    response = Response(
        value, media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-store"}
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    _append_context_headers(response, context)
    return response


def _append_context_headers(response: Response, context: RequestContext) -> None:
    for name, value in context.response_headers:
        response.raw_headers.append((name.lower().encode("latin-1"), value.encode("latin-1")))


def normalized_authority(value: str, *, scheme: str | None = None) -> tuple[str, str, int] | None:
    """Normalize an HTTP authority without accepting user-info or URL suffixes."""
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


def same_origin(request: Request, origin: str) -> bool:
    """Compare a browser Origin header with the request authority."""
    parsed = normalized_authority(origin)
    if parsed is None:
        return False
    scheme, hostname, port = parsed
    return normalized_authority(request.headers.get("Host", ""), scheme=scheme) == (
        scheme,
        hostname,
        port,
    )
