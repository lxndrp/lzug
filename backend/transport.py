"""Framework-neutral request context used by the FastAPI transport.

The context contains only request-scoped security and service orchestration.
It deliberately does not know about ASGI, Starlette, or any HTTP server.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

from .absence import AbsenceService
from .application import (
    ApplicationResult,
    AuthenticationRequiredError,
    ForbiddenRequestError,
    ReadApplication,
)
from .auth import AuthContext, AuthenticationRepository, SessionCredentials
from .authorization import AuthorizationScope, AuthorizationService
from .calendar import CalendarService
from .candidate_days import CandidateDayService
from .exam_day_closures import ExamDayClosureService
from .exam_protocols import ExamProtocolService
from .exam_results import ExamResultService
from .exam_round_lifecycle import ExamRoundLifecycleService
from .local_auth import LocalAuthService
from .models import (
    CANDIDATE,
    EXAM_DAY,
    EXAM_HALF_YEAR,
    EXAM_ROUND,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    Resource,
)
from .notifications import NotificationService
from .observability import emit_event
from .plan_consequences import PlanConsequenceService
from .planning import (
    ConfirmedPlanChange,
    PlanAssignment,
    PlanDay,
    PlanningProposal,
    PlanningService,
    PlanSlot,
)
from .repositories import REST_RESOURCES, ResourceRepository
from .runtime_policy import RuntimePolicy
from .security import RequestRateLimiter


class RequestTooLargeError(ValueError):
    """Signal a request body beyond the configured production limit."""


class UnsupportedMediaTypeError(ValueError):
    """Signal a body that is not JSON at the transport boundary."""


def planning_proposal_from_payload(round_id: int, payload: dict[str, Any]) -> PlanningProposal:
    """Parse a complete proposal while keeping the path as authoritative scope."""

    def integer(
        container: dict[str, Any], field_name: str, *, nullable: bool = False
    ) -> int | None:
        value = container.get(field_name)
        if nullable and value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{field_name} must be an integer")
        return value

    def room_identifier(container: dict[str, Any]) -> int:
        """Accept the temporary location alias without weakening room identity."""
        has_room = "room_id" in container
        has_location = "location_id" in container
        if not has_room and not has_location:
            raise ValueError("room_id must be an integer")
        room_id = integer(container, "room_id") if has_room else None
        location_id = integer(container, "location_id") if has_location else None
        if room_id is not None and location_id is not None and room_id != location_id:
            raise ValueError("room_id and location_id must match")
        if room_id is not None:
            return room_id
        if location_id is None:
            raise ValueError("location_id must be an integer")
        return location_id

    if integer(payload, "round_id") != round_id:
        raise ValueError("round_id must match the request path")
    raw_days = payload.get("exam_days")
    if not isinstance(raw_days, list):
        raise ValueError("exam_days must be an array")
    days: list[PlanDay] = []
    for raw_day in raw_days:
        if not isinstance(raw_day, dict):
            raise ValueError("Each exam day must be an object")
        raw_slots = raw_day.get("slots")
        raw_assignments = raw_day.get("assignments")
        if not isinstance(raw_slots, list) or not isinstance(raw_assignments, list):
            raise ValueError("Each exam day needs slots and assignments arrays")
        slots: list[PlanSlot] = []
        for raw_slot in raw_slots:
            if not isinstance(raw_slot, dict) or not isinstance(raw_slot.get("slot_type"), str):
                raise ValueError("Each slot must be an object with a slot_type")
            slots.append(
                PlanSlot(
                    id=integer(raw_slot, "id", nullable=True),
                    round_candidate_id=integer(raw_slot, "round_candidate_id"),
                    slot_type=raw_slot["slot_type"],
                )
            )
        assignments: list[PlanAssignment] = []
        for raw_assignment in raw_assignments:
            if not isinstance(raw_assignment, dict):
                raise ValueError("Each assignment must be an object")
            if not isinstance(raw_assignment.get("assignment_role"), str) or not isinstance(
                raw_assignment.get("day_part"), str
            ):
                raise ValueError("Assignment role and day part must be strings")
            assignments.append(
                PlanAssignment(
                    id=integer(raw_assignment, "id", nullable=True),
                    committee_member_id=integer(raw_assignment, "committee_member_id"),
                    assignment_role=raw_assignment["assignment_role"],
                    day_part=raw_assignment["day_part"],
                )
            )
        days.append(
            PlanDay(
                id=integer(raw_day, "id", nullable=True),
                candidate_exam_day_id=integer(raw_day, "candidate_exam_day_id"),
                room_id=room_identifier(raw_day),
                slots=tuple(slots),
                assignments=tuple(assignments),
            )
        )
    return PlanningProposal(
        round_id=round_id,
        revision=integer(payload, "revision"),
        days=tuple(days),
    )


def confirmed_plan_change_from_payload(
    round_id: int,
    payload: dict[str, Any],
) -> ConfirmedPlanChange:
    """Parse a complete confirmed-plan revision command at its aggregate boundary."""
    reason = payload.get("reason")
    if not isinstance(reason, str):
        raise ValueError("reason must be a string")
    return ConfirmedPlanChange(
        plan=planning_proposal_from_payload(round_id, payload),
        reason=reason,
    )


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
    auth_rate_limiter: RequestRateLimiter
    observability_rate_limiter: RequestRateLimiter
    observability_global_rate_limiter: RequestRateLimiter
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
    def repository(self) -> ResourceRepository:
        return ResourceRepository(self.db_path)

    @property
    def planning_service(self) -> PlanningService:
        return PlanningService(self.db_path)

    @property
    def candidate_day_service(self) -> CandidateDayService:
        return CandidateDayService(self.db_path)

    @property
    def authentication_repository(self) -> AuthenticationRepository:
        return AuthenticationRepository(self.db_path)

    @property
    def authorization_service(self) -> AuthorizationService:
        return AuthorizationService(self.db_path)

    @property
    def local_auth_service(self) -> LocalAuthService:
        return LocalAuthService(self.db_path, session_ttl=self.session_ttl)

    @property
    def notification_service(self) -> NotificationService:
        return NotificationService(
            self.db_path,
            external_delivery_enabled=self.runtime_policy.external_notifications_enabled(),
        )

    @property
    def calendar_service(self) -> CalendarService:
        return CalendarService(self.db_path)

    @property
    def plan_consequence_service(self) -> PlanConsequenceService:
        return PlanConsequenceService(
            self.db_path,
            self.notification_service,
            self.calendar_service,
        )

    @property
    def absence_service(self) -> AbsenceService:
        return AbsenceService(self.db_path, self.notification_service)

    @property
    def exam_protocol_service(self) -> ExamProtocolService:
        return ExamProtocolService(self.db_path)

    @property
    def exam_result_service(self) -> ExamResultService:
        return ExamResultService(self.db_path)

    @property
    def exam_day_closure_service(self) -> ExamDayClosureService:
        return ExamDayClosureService(self.db_path, self.notification_service)

    @property
    def exam_round_lifecycle_service(self) -> ExamRoundLifecycleService:
        return ExamRoundLifecycleService(self.db_path, self.notification_service)

    @property
    def read_application(self) -> ReadApplication:
        return ReadApplication(self.db_path)

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
        return self.normalize_payload(payload)

    def normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized.pop("specialization_label", None)
        if "default_location_id" in normalized:
            default_location_id = normalized.pop("default_location_id")
            if (
                "default_room_id" in normalized
                and normalized["default_room_id"] != default_location_id
            ):
                raise ValueError("default_room_id and default_location_id must match")
            normalized["default_room_id"] = default_location_id
        if "attempt_number" in normalized:
            normalized["attempt_number"] = max(1, int(normalized["attempt_number"]))
        for field_name in (
            "requires_mep",
            "is_active",
            "lunch_break_enabled",
            "exclude_public_holidays",
        ):
            if field_name in normalized:
                normalized[field_name] = self.normalize_bool(normalized[field_name])
        normalized.pop(CANDIDATE.table, None)
        return normalized

    @staticmethod
    def normalize_bool(value: Any) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return int(value != 0)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return 1
            if normalized in {"0", "false", "no", "off"}:
                return 0
        raise ValueError("Expected boolean value")

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
        round_data = self.repository.get(EXAM_ROUND, round_id)
        committee_id = round_data["committee_id"] if round_data is not None else None
        allowed = (
            self.authorization_scope.can_manage_committee(committee_id)
            if manage
            else self.authorization_scope.can_read_committee(committee_id)
        )
        if not allowed:
            raise ForbiddenRequestError("Forbidden.")

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
        day = self.repository.get(EXAM_DAY, day_id)
        round_id = day.get("exam_round_id") if day else None
        if round_id is None:
            raise ForbiddenRequestError("Forbidden.")
        if manage:
            self.require_round_access(round_id, manage=True)
            return
        self.require_round_access(round_id)
        committee_id = self.repository.committee_id_for_resource(EXAM_DAY, day_id)
        if not self.authorization_scope.can_edit_member(member_id, committee_id):
            raise ForbiddenRequestError("Forbidden.")

    def authorize_resource_action(
        self, resource_name: str, entity_id: int | None, payload: dict[str, Any], action: str
    ) -> dict[str, Any]:
        del action
        resource = REST_RESOURCES[resource_name]
        normalized = dict(payload)
        for actor_field in ("created_by_member_id", "updated_by_member_id"):
            normalized.pop(actor_field, None)
        if resource == MEMBER_AVAILABILITY:
            existing = self.repository.get(resource, entity_id) if entity_id is not None else None
            round_id = existing["exam_round_id"] if existing else normalized.get("exam_round_id")
            if round_id is None:
                raise ForbiddenRequestError("Forbidden.")
            self.require_round_access(int(round_id))
            committee_id = self.repository.committee_id_for_resource(EXAM_ROUND, int(round_id))
            target_member_id = (
                existing["committee_member_id"]
                if existing is not None
                else normalized.get("committee_member_id")
            )
            managed = self.authorization_scope.can_manage_committee(committee_id)
            own_member_id = self.authorization_scope.member_for_committee(committee_id)
            if not managed:
                if existing is not None and existing["committee_member_id"] != own_member_id:
                    raise ForbiddenRequestError("Forbidden.")
                target_member_id = own_member_id
            target_member = (
                self.repository.member_get(int(target_member_id))
                if target_member_id is not None
                else None
            )
            if (
                target_member is None
                or not target_member["is_active"]
                or target_member["committee_id"] != committee_id
                or not self.authorization_scope.can_edit_member(target_member["id"], committee_id)
            ):
                raise ForbiddenRequestError("Forbidden.")
            normalized["exam_round_id"] = int(round_id)
            normalized["committee_member_id"] = target_member["id"]
            if existing is not None and "candidate_exam_day_id" not in normalized:
                normalized["candidate_exam_day_id"] = existing["candidate_exam_day_id"]
            return normalized
        if resource == EXAM_HALF_YEAR:
            raise ForbiddenRequestError(
                "Prüfungshalbjahre entstehen ausschließlich gemeinsam mit einer Ausschussrunde."
            )
        committee_id = self.repository.committee_id_for_resource(resource, entity_id, normalized)
        if not self.authorization_scope.can_manage_committee(committee_id):
            raise ForbiddenRequestError("Forbidden.")
        round_id = self.repository.round_id_for_resource(resource, entity_id, normalized)
        if round_id is not None:
            self.require_round_access(int(round_id), manage=True)
        if resource == EXAM_ROUND:
            member_id = self.authorization_scope.member_for_committee(committee_id)
            if member_id is None:
                raise ForbiddenRequestError("Forbidden.")
            normalized["created_by_member_id"] = member_id
        elif resource == PLANNING_SETTINGS and round_id is not None:
            member_id = self.authorization_scope.member_for_committee(committee_id)
            if member_id is None:
                raise ForbiddenRequestError("Forbidden.")
            normalized["updated_by_member_id"] = member_id
        return normalized

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
