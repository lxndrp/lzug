"""Shared HTTP dependencies; domain authorization stays in the application core."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request, Security
from fastapi.security import APIKeyCookie

from backend.application.transport import RequestContext, RequestTooLargeError

from .application import ForbiddenRequestError

SESSION_COOKIE = APIKeyCookie(name="lzug_session", scheme_name="sessionCookie", auto_error=False)


def validate_body_headers(request: Request) -> None:
    """Reject unsupported framing before routing, authentication or body parsing."""
    if request.headers.get("Transfer-Encoding"):
        raise ValueError("Transfer-Encoding is not supported")
    raw_length = request.headers.get("Content-Length")
    try:
        length = int(raw_length) if raw_length is not None else 0
    except ValueError:
        length = -1
    if length < 0:
        raise ValueError("Invalid Content-Length")
    maximum = request.app.state.lzug_config.max_request_bytes
    if length > maximum:
        raise RequestTooLargeError(f"Request body exceeds {maximum} bytes.")


async def buffered_body(request: Request) -> bytes:
    """Reuse the transport buffer without moving JSON errors ahead of access checks.

    The transport guard calls this before routing, including for unknown paths.
    RequestContext.read_json remains responsible for the actual payload size and
    media type at the existing application boundary.
    """
    if not hasattr(request.state, "raw_body"):
        validate_body_headers(request)
        request.state.raw_body = await request.body()
    return request.state.raw_body


BufferedBody = Annotated[bytes, Depends(buffered_body)]


def request_context(request: Request) -> RequestContext:
    """Create one request-scoped context, including the runtime-selected database."""
    config = request.app.state.lzug_config
    session_token = request.cookies.get(config.session_cookie_name)
    return RequestContext(
        request=request,
        db_path=config.runtime_policy.database_for_request(config.db_path, session_token),
        session_cookie_name=config.session_cookie_name,
        csrf_cookie_name=config.csrf_cookie_name,
        cookie_secure=config.cookie_secure,
        session_ttl=config.session_ttl,
        max_request_bytes=config.max_request_bytes,
        runtime_policy=config.runtime_policy,
        runtime_settings=config.runtime_settings,
        auth_rate_limiter=request.app.state.auth_rate_limiter,
        observability_rate_limiter=request.app.state.observability_rate_limiter,
        observability_global_rate_limiter=request.app.state.observability_global_rate_limiter,
    )


Context = Annotated[RequestContext, Depends(request_context)]


def body_context(context: Context, body: BufferedBody) -> RequestContext:
    """Attach the buffered body only to handlers whose existing contract reads it."""
    context.set_body(body)
    return context


BodyContext = Annotated[RequestContext, Depends(body_context)]


def access_context(
    *,
    actor: bool = True,
    csrf: bool = False,
    body: bool = False,
    mutation: bool = False,
    operator: bool = False,
) -> Callable[..., RequestContext]:
    """Compose session, CSRF, membership and runtime/lifecycle mutation checks.

    All decisions delegate to the existing context and services. The operator
    alternative is reserved for the venue boundary. Some existing mutations do
    not require CSRF; callers must choose their established contract explicitly.
    """

    dependency = body_context if body else request_context

    def authorize(context: RequestContext) -> RequestContext:
        auth = context.require_authenticated(require_actor=actor, require_csrf=csrf)
        if (
            operator
            and not auth.is_operator
            and not context.authorization_scope.has_active_membership
        ):
            raise ForbiddenRequestError("Forbidden.")
        if mutation:
            request = context.request
            parts = request.url.path.removeprefix("/api/").strip("/").split("/")
            context.authorize_mutation(request.method, parts, auth)
        return context

    if csrf:

        def write_access(
            context: Annotated[RequestContext, Depends(dependency)],
            _session: Annotated[str | None, Security(SESSION_COOKIE)] = None,
            _csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
        ) -> RequestContext:
            return authorize(context)

        return write_access

    def read_access(
        context: Annotated[RequestContext, Depends(dependency)],
        _session: Annotated[str | None, Security(SESSION_COOKIE)] = None,
    ) -> RequestContext:
        return authorize(context)

    return read_access


SessionContext = Annotated[RequestContext, Depends(access_context(actor=False))]
ReadContext = Annotated[RequestContext, Depends(access_context())]
WriteContext = Annotated[
    RequestContext, Depends(access_context(csrf=True, body=True, mutation=True))
]
EmptyWriteContext = Annotated[RequestContext, Depends(access_context(csrf=True, mutation=True))]
SessionWriteContext = Annotated[
    RequestContext, Depends(access_context(actor=False, csrf=True, mutation=True))
]
MutationContext = Annotated[RequestContext, Depends(access_context(mutation=True))]
BodyMutationContext = Annotated[RequestContext, Depends(access_context(body=True, mutation=True))]


def venue_access(*, mutation: bool = False, identifier: str | None = None):
    """Keep venue path validation before authentication, with operator access.

    Typed identifiers live only in this dependency so FastAPI still emits one
    unchanged validation error, before running the access checks.
    """
    access = access_context(
        actor=False, csrf=mutation, body=mutation, mutation=mutation, operator=True
    )
    base = body_context if mutation else request_context

    def item(id: int, context: Annotated[RequestContext, Depends(base)]) -> RequestContext:
        return access(context)

    def audit(audit_id: int, context: Annotated[RequestContext, Depends(base)]) -> RequestContext:
        return access(context)

    if identifier == "id":
        return item
    if identifier == "audit_id":
        return audit
    return access


VenueReadContext = Annotated[RequestContext, Depends(venue_access())]
VenueWriteContext = Annotated[RequestContext, Depends(venue_access(mutation=True))]
VenueItemReadContext = Annotated[RequestContext, Depends(venue_access(identifier="id"))]
VenueItemWriteContext = Annotated[
    RequestContext, Depends(venue_access(mutation=True, identifier="id"))
]
VenueAuditWriteContext = Annotated[
    RequestContext, Depends(venue_access(mutation=True, identifier="audit_id"))
]


def round_access(
    dependency: Callable[..., RequestContext], *, manage: bool = False, body: bool = False
):
    """Apply the existing round/committee guard after authentication and mutation policy."""

    def access(context: Annotated[RequestContext, Depends(dependency)]) -> RequestContext:
        round_id = int(
            context.read_json().get("round_id", 1) if body else context.request.path_params["id"]
        )
        context.require_round_access(round_id, manage=manage)
        return context

    return access


ManageRoundContext = Annotated[RequestContext, Depends(round_access(access_context(), manage=True))]
ManageRoundWriteContext = Annotated[
    RequestContext,
    Depends(round_access(access_context(csrf=True, body=True, mutation=True), manage=True)),
]
ManageRoundEmptyWriteContext = Annotated[
    RequestContext,
    Depends(round_access(access_context(csrf=True, mutation=True), manage=True)),
]
ManageBodyRoundContext = Annotated[
    RequestContext,
    Depends(
        round_access(access_context(csrf=True, body=True, mutation=True), manage=True, body=True)
    ),
]
