"""Shared FastAPI response and same-origin transport helpers."""

from __future__ import annotations

import json
from http import HTTPStatus
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import Response

from .application import ApplicationResult
from .transport import RequestContext


def json_response(result: ApplicationResult, context: RequestContext | None = None) -> Response:
    """Serialize one framework-independent application result as JSON."""
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


def not_found() -> Response:
    """Return the stable API not-found envelope."""
    return json_response(ApplicationResult({"error": "Not found"}, HTTPStatus.NOT_FOUND))


def finish(context: RequestContext, result: ApplicationResult | None = None) -> Response:
    """Finish a request with its explicit or context-owned result and headers."""
    return json_response(result or context.response_result or ApplicationResult({}), context)


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
