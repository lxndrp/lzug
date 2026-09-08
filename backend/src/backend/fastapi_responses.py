"""Shared FastAPI response translation for all router modules."""

from __future__ import annotations

import json
from http import HTTPStatus

from fastapi.responses import Response

from .application import ApplicationResult
from .transport import RequestContext


def json_response(
    result: ApplicationResult,
    context: RequestContext | None = None,
) -> Response:
    """Translate an application result without changing the established HTTP contract."""
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
    """Return the established JSON response for a missing API resource."""
    return json_response(ApplicationResult({"error": "Not found"}, HTTPStatus.NOT_FOUND))


def finish(
    context: RequestContext,
    result: ApplicationResult | None = None,
) -> Response:
    """Finish one request and append any response headers accumulated by its context."""
    return json_response(result or context.response_result or ApplicationResult({}), context)
