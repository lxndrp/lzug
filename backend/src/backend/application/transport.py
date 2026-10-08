"""Framework-neutral request context used by the FastAPI transport.

The context contains only request-scoped security and service orchestration.
It deliberately does not know about ASGI, Starlette, or any HTTP server.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast

from backend.application import (
    ApplicationResult,
    ApplicationServices,
    AuthenticationRequiredError,
    ForbiddenRequestError,
    ReadApplication,
)
from backend.application.planning_payloads import (
    confirmed_plan_change_from_payload as confirmed_plan_change_from_payload,
)
from backend.application.planning_payloads import (
    planning_proposal_from_payload as planning_proposal_from_payload,
)
from backend.application.repositories import REST_RESOURCES, ResourceRepository
from backend.application.resource_access import ResourceAccessQueryFactory, ResourceKind
from backend.application.resource_authorization import ResourceAuthorizer
from backend.assessment.ports import AssessmentActorSnapshot
from backend.assessment.service import ExamResultService
from backend.execution.absence import AbsenceService
from backend.execution.exam_day_closures import ExamDayClosureService
from backend.execution.exam_protocols import ExamProtocolService
from backend.execution.exam_round_lifecycle import ExamRoundLifecycleService
from backend.execution.slot_service import ExecutionService
from backend.identity.auth import AuthContext, AuthenticationRepository, SessionCredentials
from backend.identity.authorization import AuthorizationScope, AuthorizationService
from backend.identity.committee_admin import CommitteeAdminService
from backend.identity.local_auth import LocalAuthService
from backend.identity.people import IdentityService
from backend.integrations.calendar import CalendarService
from backend.notifications.service import NotificationService
from backend.observability import emit_event
from backend.persistence.models import Resource
from backend.planning import PlanningService
from backend.planning.candidate_days import CandidateDayService
from backend.planning.plan_consequences import PlanConsequenceService
from backend.planning.resources import (
    MAX_PLANNING_VISIBILITY_PAGE_SIZE,
    PlanningResourceService,
    PlanningResourceUnitOfWorkFactory,
    PlanningValue,
)
from backend.runtime_policy import RuntimePolicy
from backend.security import RequestRateLimiter
from backend.settings import RuntimeSettings


class RequestTooLargeError(ValueError):
    """Signal a request body beyond the configured production limit."""


class UnsupportedMediaTypeError(ValueError):
    """Signal a body that is not JSON at the transport boundary."""


@dataclass
class RequestContext:
    """Request-scoped access to framework-independent application services."""

    request: Any
    db_path: Path
    session_cookie_name: str
    csrf_cookie_name: str
    cookie_secure: bool
    session_ttl: timedelta
    max_request_bytes: int
    runtime_policy: RuntimePolicy
    planning_service_factory: Callable[[Path], PlanningService]
    execution_service_factory: Callable[[Path], ExecutionService]
    exam_protocol_service_factory: Callable[[Path], ExamProtocolService]
    exam_result_service_factory: Callable[[Path], ExamResultService]
    candidate_day_service_factory: Callable[[Path], CandidateDayService]
    planning_resource_unit_of_work_factory: Callable[[Path], PlanningResourceUnitOfWorkFactory]
    resource_access_query_factory: Callable[[Path], ResourceAccessQueryFactory]
    identity_service_factory: Callable[[Path], IdentityService]
    authorization_service_factory: Callable[[Path], AuthorizationService]
    committee_admin_service_factory: Callable[[Path], CommitteeAdminService]
    authentication_repository_factory: Callable[[Path], AuthenticationRepository]
    local_auth_service_factory: Callable[..., LocalAuthService]
    notification_service_factory: Callable[[Path], NotificationService]
    auth_rate_limiter: RequestRateLimiter
    observability_rate_limiter: RequestRateLimiter
    observability_global_rate_limiter: RequestRateLimiter
    runtime_settings: RuntimeSettings | None = None
    _body: bytes = b""
    auth_context: AuthContext | None = None
    authorization_scope: AuthorizationScope = field(
        default_factory=lambda: AuthorizationScope(
            None, frozenset(), frozenset(), frozenset(), frozenset(), {}
        )
    )
    response_result: ApplicationResult | None = None
    response_headers: list[tuple[str, str]] = field(default_factory=list)

    @property
    def assessment_actor(self) -> AssessmentActorSnapshot:
        """Project the detached request authorization scope into Assessment's contract."""
        scope = self.authorization_scope
        return {
            "person_id": scope.person_id,
            "person_ids": tuple(sorted(scope.person_ids)),
            "committee_ids": tuple(sorted(scope.committee_ids)),
            "member_ids": tuple(sorted(scope.member_ids)),
            "management_committee_ids": tuple(sorted(scope.management_committee_ids)),
            "member_by_committee": dict(scope.member_by_committee),
        }

    @property
    def repository(self) -> ResourceRepository:
        queries = self.resource_access_query_factory(self.db_path)
        return ResourceRepository(self.db_path, queries)

    @property
    def identity_service(self) -> IdentityService:
        return self.identity_service_factory(self.db_path)

    @property
    def committee_admin_service(self) -> CommitteeAdminService:
        return self.committee_admin_service_factory(self.db_path)

    @property
    def resource_access_queries(self) -> ResourceAccessQueryFactory:
        return self.resource_access_query_factory(self.db_path)

    @property
    def planning_service(self) -> PlanningService:
        return self.planning_service_factory(self.db_path)

    @property
    def candidate_day_service(self) -> CandidateDayService:
        return self.candidate_day_service_factory(self.db_path)

    @property
    def planning_resource_service(self) -> PlanningResourceService:
        def authorize(queries, resource: str, entity_id: int | None, payload):
            return ResourceAuthorizer(
                self.resource_access_queries, self.authorization_scope
            ).authorize_with_queries(queries, ResourceKind(resource), entity_id, payload)

        def visible(queries, resource, entity_id, filters):
            resource_kind = ResourceKind(resource)
            if entity_id is None:
                page_size = MAX_PLANNING_VISIBILITY_PAGE_SIZE

                def pages():
                    offset = 0
                    while True:
                        rows = queries.list_visible_page(
                            resource_kind,
                            self.authorization_scope,
                            filters,
                            offset=offset,
                            limit=page_size,
                        )
                        if not rows:
                            return
                        yield frozenset(int(row["id"]) for row in rows)
                        if len(rows) < page_size:
                            return
                        offset += page_size

                return pages()
            return (
                queries.get_visible(resource_kind, entity_id, self.authorization_scope) is not None
            )

        return PlanningResourceService(
            self.planning_resource_unit_of_work_factory(self.db_path), authorize, visible
        )

    def visible_planning_records(
        self, resource: Resource, filters: dict[str, object]
    ) -> list[dict[str, object]]:
        records = self.planning_resource_service.list_visible_records(
            resource.table, cast("dict[str, PlanningValue]", filters)
        )
        return [record.as_payload() for record in records]

    def visible_planning_record(
        self, resource: Resource, resource_id: int
    ) -> dict[str, object] | None:
        record = self.planning_resource_service.get_visible_record(resource.table, resource_id)
        return record.as_payload() if record is not None else None

    @property
    def authentication_repository(self) -> AuthenticationRepository:
        return self.authentication_repository_factory(self.db_path)

    @property
    def authorization_service(self) -> AuthorizationService:
        return self.authorization_service_factory(self.db_path)

    @property
    def local_auth_service(self) -> LocalAuthService:
        return self.local_auth_service_factory(
            self.db_path,
            session_ttl=self.session_ttl,
            settings=self.runtime_settings,
        )

    @property
    def notification_service(self) -> NotificationService:
        return self.notification_service_factory(self.db_path)

    @property
    def calendar_service(self) -> CalendarService:
        return CalendarService(self.db_path, settings=self.runtime_settings)

    @property
    def plan_consequence_service(self) -> PlanConsequenceService:
        return PlanConsequenceService(
            self.db_path,
            notification_service=self.notification_service,
            calendar_service=self.calendar_service,
        )

    @property
    def absence_service(self) -> AbsenceService:
        return AbsenceService(self.db_path, notification_service=self.notification_service)

    @property
    def exam_protocol_service(self) -> ExamProtocolService:
        return self.exam_protocol_service_factory(self.db_path)

    @property
    def execution_service(self) -> ExecutionService:
        return self.execution_service_factory(self.db_path)

    @property
    def exam_result_service(self) -> ExamResultService:
        return self.exam_result_service_factory(self.db_path)

    @property
    def exam_day_closure_service(self) -> ExamDayClosureService:
        return ExamDayClosureService(self.db_path, notification_service=self.notification_service)

    @property
    def exam_round_lifecycle_service(self) -> ExamRoundLifecycleService:
        return ExamRoundLifecycleService(
            self.db_path, notification_service=self.notification_service
        )

    @property
    def read_application(self) -> ReadApplication:
        return ReadApplication(
            self.db_path,
            ApplicationServices(
                planning_resource_service_factory=lambda path: PlanningResourceService(
                    self.planning_resource_unit_of_work_factory(path)
                ),
                authentication_factory=self.authentication_repository_factory,
                authorization_factory=self.authorization_service_factory,
            ),
        )

    @property
    def session_token(self) -> str | None:
        return self.request.cookies.get(self.session_cookie_name)

    @property
    def client_key(self) -> str:
        client = getattr(self.request, "client", None)
        return getattr(client, "host", "unknown")

    def set_body(self, body: bytes) -> None:
        self._body = body

    def read_json(self) -> dict[str, Any]:
        """Decode the bounded JSON object envelope.

        FastAPI owns request-model validation and OpenAPI generation. This
        read remains for the stable media/object envelope and because runtime
        allowlists and lifecycle guards must inspect the object before endpoint
        field validation.
        """
        if len(self._body) > self.max_request_bytes:
            raise RequestTooLargeError(f"Request body exceeds {self.max_request_bytes} bytes.")
        if not self._body:
            return {}
        if (
            self.request.headers.get("content-type", "").split(";", 1)[0].strip()
            != "application/json"
        ):
            raise UnsupportedMediaTypeError("Content-Type must be application/json.")
        try:
            payload = json.loads(self._body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid JSON body") from error
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def require_authenticated(
        self, *, require_actor: bool = True, require_csrf: bool = False
    ) -> AuthContext:
        context = self.authentication_repository.authenticate(self.session_token)
        if context is None:
            raise AuthenticationRequiredError
        scope = self.authorization_service.scope(context)
        if require_csrf and not self.authentication_repository.verify_csrf(
            context, self.request.headers.get("x-csrf-token")
        ):
            raise ForbiddenRequestError("CSRF validation failed.")
        if require_actor and not scope.has_active_membership:
            raise ForbiddenRequestError("Forbidden.")
        self.auth_context = context
        self.authorization_scope = scope
        return context

    def allow_public_auth_request(self, path_parts: list[str]) -> bool:
        endpoint = "/".join(path_parts)
        retry_after = self.auth_rate_limiter.check(f"{self.client_key}:{endpoint}")
        if retry_after is None:
            return True
        self.add_header("Retry-After", str(retry_after))
        self.respond({"error": "Too many requests."}, HTTPStatus.TOO_MANY_REQUESTS)
        return False

    def authorize_mutation(self, method: str, path_parts: list[str], context: AuthContext) -> None:
        self.runtime_policy.authorize_mutation(self, method, path_parts, context)
        self.exam_round_lifecycle_service.assert_http_mutation(
            method,
            path_parts,
            self.read_json() if self._body else {},
        )

    def require_round_access(self, round_id: int, *, manage: bool = False) -> None:
        ResourceAuthorizer(
            self.resource_access_queries, self.authorization_scope
        ).require_round_access(round_id, manage=manage)

    def create_notifications_best_effort(self, event_type: str, round_id: int) -> str | None:
        try:
            result = self.notification_service.create_for_event(event_type, round_id)
            if result.get("problems", 0):
                emit_event("backend_error", severity="warning", category="delivery_incomplete")
                return (
                    "Die Benachrichtigungen wurden in lzug bereitgestellt, aber eine externe "
                    "Zustellung war nicht für alle vorgesehenen Empfänger verfügbar."
                )
            return None
        except Exception:
            emit_event("backend_error", severity="error", category="notification_processing")
            return (
                "Der Fachvorgang wurde gespeichert, aber Benachrichtigungen konnten nicht für "
                "alle vorgesehenen Empfänger verarbeitet werden."
            )

    def require_day_access(
        self, day_id: int, *, manage: bool = False, member_id: int | None = None
    ) -> None:
        ResourceAuthorizer(
            self.resource_access_queries, self.authorization_scope
        ).require_day_access(day_id, manage=manage, member_id=member_id)

    def authorize_resource_action(
        self, resource_name: str, entity_id: int | None, payload: dict[str, Any], action: str
    ) -> dict[str, Any]:
        del action
        resource = ResourceKind(REST_RESOURCES[resource_name].table)
        return ResourceAuthorizer(self.resource_access_queries, self.authorization_scope).authorize(
            resource, entity_id, payload
        )

    def issue_session_cookies(
        self,
        credentials: SessionCredentials,
        *,
        max_age: int | None = None,
    ) -> None:
        self.add_header(
            "Set-Cookie",
            self.cookie(
                self.session_cookie_name,
                credentials.token,
                http_only=True,
                max_age=max_age,
            ),
        )
        self.add_header(
            "Set-Cookie",
            self.cookie(
                self.csrf_cookie_name,
                credentials.csrf_token,
                http_only=False,
                max_age=max_age,
            ),
        )

    def clear_session_cookies(self) -> None:
        self.add_header(
            "Set-Cookie", self.cookie(self.session_cookie_name, "", max_age=0, http_only=True)
        )
        self.add_header(
            "Set-Cookie", self.cookie(self.csrf_cookie_name, "", max_age=0, http_only=False)
        )

    def cookie(self, name: str, value: str, *, http_only: bool, max_age: int | None = None) -> str:
        effective_max_age = (
            max_age
            if max_age is not None
            else (int(self.session_ttl.total_seconds()) if value else 8 * 60 * 60)
        )
        attributes = [
            f"{name}={value}",
            f"Max-Age={effective_max_age}",
            "Path=/",
            "SameSite=Strict",
        ]
        if self.cookie_secure:
            attributes.append("Secure")
        if http_only:
            attributes.append("HttpOnly")
        return "; ".join(attributes)

    def add_header(self, name: str, value: str) -> None:
        self.response_headers.append((name, value))

    def resource_filters(self, resource: Resource, query: Any) -> dict[str, Any]:
        aliases = {"round_id": "exam_round_id"}
        fields = set(resource.readable_fields)
        filters: dict[str, Any] = {}
        for key, values in query.multi_items():
            field_name = aliases.get(key, key)
            if field_name not in fields or field_name in filters:
                continue
            filters[field_name] = self.normalize_filter_value(field_name, values)
        return filters

    @staticmethod
    def normalize_filter_value(field_name: str, value: str) -> Any:
        if field_name == "id" or field_name.endswith("_id") or field_name in {"is_active"}:
            return int(value)
        return value

    def respond(
        self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK
    ) -> ApplicationResult:
        self.response_result = ApplicationResult(payload, status)
        return self.response_result
