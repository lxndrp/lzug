"""Shared HTTP dependencies; domain authorization stays in the application core."""

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import replace
from inspect import Parameter, Signature, signature
from types import FunctionType
from typing import Annotated, get_args, get_origin, get_type_hints

from fastapi import Depends, Header, Request, Security
from fastapi.params import Depends as DependsParameter
from fastapi.params import Security as SecurityParameter
from fastapi.routing import APIRoute
from fastapi.security import APIKeyCookie
from starlette.requests import ClientDisconnect

from backend.application.transport import RequestContext, RequestTooLargeError
from backend.identity.local_auth import LocalAuthError

from .application import ForbiddenRequestError

SESSION_COOKIE = APIKeyCookie(name="lzug_session", scheme_name="sessionCookie", auto_error=False)
_session_cookie_name: ContextVar[str | None] = ContextVar("session_cookie_name", default=None)


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
    """Buffer only a body-consuming route, bounded by actual received bytes.

    Check each ASGI chunk before retaining it and stop receiving on overflow.
    The cached bytes let FastAPI perform its native JSON and Pydantic handling
    without reading the unbounded ASGI stream first.
    """
    if not hasattr(request.state, "raw_body"):
        validate_body_headers(request)
        maximum = request.app.state.lzug_config.max_request_bytes
        body = bytearray()
        try:
            async for chunk in request.stream():
                if len(chunk) > maximum - len(body):
                    raise RequestTooLargeError(f"Request body exceeds {maximum} bytes.")
                body.extend(chunk)
        except ClientDisconnect as error:
            raise ValueError("Incomplete request body.") from error
        request.state.raw_body = bytes(body)
        request._body = request.state.raw_body  # type: ignore[attr-defined]
    return request.state.raw_body


class BoundedBodyRoute(APIRoute):
    """Enforce the transport limit before FastAPI decodes a declared body.

    FastAPI normally reads a complete request body before resolving route
    dependencies. This small compatibility boundary preserves the streaming
    limit while leaving JSON decoding, Pydantic validation, and OpenAPI schema
    generation to FastAPI itself. Routes without a declared body are not read.
    """

    def __init__(self, path: str, endpoint: Callable[..., object], **kwargs) -> None:
        cookie_name = _session_cookie_name.get()
        if cookie_name is not None and cookie_name != SESSION_COOKIE.model.name:
            endpoint = _bind_cookie_security(endpoint, cookie_name, {})
        super().__init__(path, endpoint, **kwargs)

    def get_route_handler(self):
        route_handler = super().get_route_handler()

        async def bounded_handler(request: Request):
            if self.body_field is not None:
                await buffered_body(request)
            return await route_handler(request)

        return bounded_handler


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
        planning_service_factory=request.app.state.planning_service_factory,
        execution_service_factory=request.app.state.execution_service_factory,
        exam_protocol_service_factory=request.app.state.exam_protocol_service_factory,
        exam_result_service_factory=request.app.state.exam_result_service_factory,
        planning_lifecycle_work_factory=request.app.state.planning_lifecycle_work_factory,
        assessment_lifecycle=request.app.state.assessment_lifecycle,
        assessment_round_queries=request.app.state.assessment_round_queries,
        exam_lifecycle_unit_of_work_factory=(request.app.state.exam_lifecycle_unit_of_work_factory),
        candidate_day_service_factory=request.app.state.candidate_day_service_factory,
        planning_resource_unit_of_work_factory=(
            request.app.state.planning_resource_unit_of_work_factory
        ),
        resource_access_query_factory=request.app.state.resource_access_query_factory,
        identity_service_factory=request.app.state.identity_service_factory,
        authorization_service_factory=request.app.state.authorization_service_factory,
        committee_admin_service_factory=request.app.state.committee_admin_service_factory,
        authentication_repository_factory=request.app.state.authentication_repository_factory,
        local_auth_service_factory=request.app.state.local_auth_service_factory,
        notification_service_factory=request.app.state.notification_service_factory,
        runtime_settings=config.runtime_settings,
        auth_rate_limiter=request.app.state.auth_rate_limiter,
        observability_rate_limiter=request.app.state.observability_rate_limiter,
        observability_global_rate_limiter=request.app.state.observability_global_rate_limiter,
    )


Context = Annotated[RequestContext, Depends(request_context)]


def bind_session_cookie(cookie_name: str):
    """Bind a configured cookie while FastAPI assembles route dependencies.

    FastAPI can rebuild dependencies for lazily included routers from endpoint
    signatures. Binding here keeps security native to those signatures and
    avoids post-processing routes or the generated OpenAPI document.
    """
    return _session_cookie_name.set(cookie_name)


def reset_session_cookie_binding(token) -> None:
    """Restore the previous cookie binding after app route assembly."""
    _session_cookie_name.reset(token)


def _bind_cookie_security(endpoint: Callable[..., object], cookie_name: str, cache):
    """Clone only dependency signatures that carry the session security node."""
    if endpoint in cache:
        return cache[endpoint]
    try:
        original_signature = signature(endpoint)
        hints = get_type_hints(endpoint, include_extras=True)
    except TypeError, ValueError, NameError:
        return endpoint

    parameters = []
    changed = False
    for parameter in original_signature.parameters.values():
        annotation, bound = _bind_cookie_annotation(
            hints.get(parameter.name, parameter.annotation), cookie_name, cache
        )
        parameters.append(parameter.replace(annotation=annotation))
        changed |= bound
    return_annotation, bound = _bind_cookie_annotation(
        hints.get("return", original_signature.return_annotation), cookie_name, cache
    )
    changed |= bound
    if not changed:
        cache[endpoint] = endpoint
        return endpoint

    bound_signature = original_signature.replace(
        parameters=parameters, return_annotation=return_annotation
    )
    bound_endpoint = FunctionType(
        endpoint.__code__,
        endpoint.__globals__,
        endpoint.__name__,
        endpoint.__defaults__,
        endpoint.__closure__,
    )
    bound_endpoint.__dict__.update(endpoint.__dict__)
    bound_endpoint.__kwdefaults__ = endpoint.__kwdefaults__
    bound_endpoint.__annotations__ = {
        parameter.name: parameter.annotation
        for parameter in bound_signature.parameters.values()
        if parameter.annotation is not Parameter.empty
    }
    if bound_signature.return_annotation is not Signature.empty:
        bound_endpoint.__annotations__["return"] = bound_signature.return_annotation
    bound_endpoint.__signature__ = bound_signature
    cache[endpoint] = bound_endpoint
    return bound_endpoint


def _bind_cookie_annotation(annotation, cookie_name: str, cache) -> tuple[object, bool]:
    """Replace session security metadata in one resolved Annotated type."""
    if get_origin(annotation) is not Annotated:
        return annotation, False
    base, *metadata = get_args(annotation)
    bound_metadata = []
    changed = False
    for item in metadata:
        if isinstance(item, SecurityParameter) and item.dependency is SESSION_COOKIE:
            cookie = APIKeyCookie(
                name=cookie_name,
                scheme_name="sessionCookie",
                auto_error=False,
            )
            item = Security(cookie, scopes=item.scopes, use_cache=item.use_cache)
            changed = True
        elif isinstance(item, DependsParameter) and callable(item.dependency):
            dependency = _bind_cookie_security(item.dependency, cookie_name, cache)
            if dependency is not item.dependency:
                item = replace(item, dependency=dependency)
                changed = True
        bound_metadata.append(item)
    return Annotated[base, *bound_metadata], changed


def body_context(context: Context, body: BufferedBody) -> RequestContext:
    """Attach bounded bytes for the pre-validation security compatibility check."""
    context.set_body(body)
    return context


BodyContext = Annotated[RequestContext, Depends(body_context)]


def object_body_context(context: BodyContext) -> RequestContext:
    """Enforce the stable JSON media/object contract before model validation."""
    context.read_json()
    return context


ObjectBodyContext = Annotated[RequestContext, Depends(object_body_context)]


def public_auth_context(context: BodyContext) -> RequestContext:
    """Apply product-policy and brute-force guards before field validation."""
    if not context.runtime_policy.allow_product_auth():
        raise ForbiddenRequestError("Forbidden.")
    request = context.request
    parts = request.url.path.removeprefix("/api/").strip("/").split("/")
    retry_after = context.auth_rate_limiter.check(f"{context.client_key}:{'/'.join(parts)}")
    if retry_after is not None:
        raise LocalAuthError("rate_limited", "Too many requests.", retry_after=retry_after)
    context.read_json()
    return context


PublicAuthContext = Annotated[RequestContext, Depends(public_auth_context)]


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
    Mutation policy deliberately inspects the decoded object before Pydantic
    field validation so demo allowlists and lifecycle guards cannot be bypassed.
    This is one of the remaining centralized body compatibility reasons.
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


def resource_create_context(context: WriteContext) -> RequestContext:
    """Preserve collection scope checks before native body field validation."""
    resource_name = context.request.url.path.removeprefix("/api/").strip("/").split("/")[0]
    context.authorize_resource_action(resource_name, None, context.read_json(), "create")
    return context


ResourceCreateContext = Annotated[RequestContext, Depends(resource_create_context)]


def resource_item_write_context(id: int, context: WriteContext) -> RequestContext:
    """Preserve item scope and typed-ID checks before body field validation."""
    resource_name = context.request.url.path.removeprefix("/api/").strip("/").split("/")[0]
    context.authorize_resource_action(resource_name, id, context.read_json(), "update")
    context.request.state.resource_identifier = id
    return context


ResourceItemWriteContext = Annotated[RequestContext, Depends(resource_item_write_context)]


def resource_identifier(context: RequestContext) -> int:
    """Return an identifier validated by the resource access dependency."""
    return context.request.state.resource_identifier


def venue_access(*, mutation: bool = False, identifier: str | None = None, body: bool = True):
    """Keep venue path validation before authentication, with operator access.

    Typed identifiers live only in this dependency so FastAPI still emits one
    unchanged validation error, before running the access checks.
    """
    access = access_context(
        actor=False, csrf=mutation, body=mutation and body, mutation=mutation, operator=True
    )
    base = body_context if mutation and body else request_context
    return _venue_access_dependency(base, access, mutation=mutation, identifier=identifier)


def _venue_access_dependency(base, access, *, mutation: bool, identifier: str | None):
    """Expose the underlying cookie and CSRF dependencies to OpenAPI."""
    if identifier is not None:
        return _venue_item_dependency(base, access, mutation=mutation, identifier=identifier)
    return _venue_collection_dependency(base, access, mutation=mutation)


def _venue_collection_dependency(base, access, *, mutation: bool):
    if mutation:

        def item(
            context: Annotated[RequestContext, Depends(base)],
            _session: Annotated[str | None, Security(SESSION_COOKIE)] = None,
            _csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
        ) -> RequestContext:
            del _session, _csrf
            return access(context)

    else:

        def item(
            context: Annotated[RequestContext, Depends(base)],
            _session: Annotated[str | None, Security(SESSION_COOKIE)] = None,
        ) -> RequestContext:
            del _session
            return access(context)

    return item


def _venue_item_dependency(base, access, *, mutation: bool, identifier: str):
    """Validate a typed route identifier before applying the existing access check."""
    if mutation:

        def item(
            id: int,
            context: Annotated[RequestContext, Depends(base)],
            _session: Annotated[str | None, Security(SESSION_COOKIE)] = None,
            _csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
        ) -> RequestContext:
            del _session, _csrf
            return _validated_venue_context(context, access, "id", id)

        def audit(
            audit_id: int,
            context: Annotated[RequestContext, Depends(base)],
            _session: Annotated[str | None, Security(SESSION_COOKIE)] = None,
            _csrf: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
        ) -> RequestContext:
            del _session, _csrf
            return _validated_venue_context(context, access, "audit_id", audit_id)

    else:

        def item(
            id: int,
            context: Annotated[RequestContext, Depends(base)],
            _session: Annotated[str | None, Security(SESSION_COOKIE)] = None,
        ) -> RequestContext:
            del _session
            return _validated_venue_context(context, access, "id", id)

        def audit(
            audit_id: int,
            context: Annotated[RequestContext, Depends(base)],
            _session: Annotated[str | None, Security(SESSION_COOKIE)] = None,
        ) -> RequestContext:
            del _session
            return _validated_venue_context(context, access, "audit_id", audit_id)

    return {"id": item, "audit_id": audit}[identifier]


def _validated_venue_context(
    context: RequestContext, access, name: str, value: int
) -> RequestContext:
    identifiers = getattr(context.request.state, "validated_path_identifiers", {})
    identifiers[name] = value
    context.request.state.validated_path_identifiers = identifiers
    return access(context)


def venue_identifier(context: RequestContext, name: str = "id") -> int:
    """Return an identifier validated by the venue access dependency."""
    return context.request.state.validated_path_identifiers[name]


VenueReadContext = Annotated[RequestContext, Depends(venue_access())]
VenueWriteContext = Annotated[RequestContext, Depends(venue_access(mutation=True))]
VenueEmptyWriteContext = Annotated[RequestContext, Depends(venue_access(mutation=True, body=False))]
VenueItemReadContext = Annotated[RequestContext, Depends(venue_access(identifier="id"))]
VenueItemWriteContext = Annotated[
    RequestContext, Depends(venue_access(mutation=True, identifier="id"))
]
VenueItemEmptyWriteContext = Annotated[
    RequestContext, Depends(venue_access(mutation=True, identifier="id", body=False))
]
VenueAuditWriteContext = Annotated[
    RequestContext, Depends(venue_access(mutation=True, identifier="audit_id", body=False))
]


def round_access(dependency: Callable[..., RequestContext], *, manage: bool = False):
    """Apply the existing round/committee guard after authentication and mutation policy."""

    def access(id: int, context: Annotated[RequestContext, Depends(dependency)]) -> RequestContext:
        context.require_round_access(id, manage=manage)
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
