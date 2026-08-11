"""HTTP entry point that maps JSON requests onto repository and planning services."""

from __future__ import annotations

import argparse
import json
import os
import signal
import threading
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from . import hateoas, openapi
from .auth import (
    AuthContext,
    AuthenticationRepository,
    SessionCredentials,
)
from .authorization import AuthorizationScope, AuthorizationService
from .candidate_days import CandidateDayService
from .database import (
    DEFAULT_DB_PATH,
    MigrationError,
    PersistenceConfigurationError,
    database_readiness,
    initialize,
    persistence_paths,
    validate_persistence,
)
from .local_auth import LocalAuthError, LocalAuthService
from .models import (
    CANDIDATE,
    CANDIDATE_COMMITTEE_ASSIGNMENT,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_HALF_YEAR,
    EXAM_ROUND,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    Resource,
)
from .planning import PlanningService
from .repositories import REST_RESOURCES, ResourceRepository
from .security import RequestRateLimiter, RuntimeSecurityConfig


class ForbiddenRequestError(Exception):
    """Signal a valid session without authorization for request context."""


class RequestTooLargeError(ValueError):
    """Signal a request body beyond the configured production limit."""


class UnsupportedMediaTypeError(ValueError):
    """Signal a body that is not JSON at the HTTP boundary."""


@dataclass(frozen=True)
class StaticAsset:
    """One trusted immutable response loaded from the configured static root."""

    body: bytes
    content_type: str


STATIC_CONTENT_TYPES = {
    ".css": "text/css",
    ".gif": "image/gif",
    ".htm": "text/html",
    ".html": "text/html",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "text/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ttf": "font/ttf",
    ".txt": "text/plain",
    ".webmanifest": "application/manifest+json",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".xml": "application/xml",
}


@lru_cache(maxsize=8)
def trusted_static_assets(root: Path) -> dict[str, StaticAsset]:
    """Load regular in-root assets without carrying request paths into filesystem APIs."""
    trusted_root = root.resolve(strict=True)
    assets: dict[str, StaticAsset] = {}
    for discovered in trusted_root.rglob("*"):
        try:
            if discovered.is_symlink():
                continue
            resolved = discovered.resolve(strict=True)
            resolved.relative_to(trusted_root)
            if not resolved.is_file():
                continue
            body = resolved.read_bytes()
            route = "/" + discovered.relative_to(trusted_root).as_posix()
        except OSError, ValueError:
            continue
        assets[route] = StaticAsset(
            body=body,
            content_type=STATIC_CONTENT_TYPES.get(
                resolved.suffix.lower(), "application/octet-stream"
            ),
        )
    return assets


class LzugHandler(BaseHTTPRequestHandler):
    """Serve the versioned JSON API and its OpenAPI-backed interactive documentation.

    This adapter parses transport data, delegates domain work to services and
    repositories, and maps expected errors to HTTP responses. Endpoint details
    remain canonical in :mod:`backend.openapi`, rather than being duplicated in
    method documentation here.
    """

    db_path = DEFAULT_DB_PATH
    static_dir: Path | None = None
    cookie_secure = True
    https_only = True
    session_cookie_name = "__Host-lzug_session"
    csrf_cookie_name = "lzug_csrf"
    cors_allowed_origins: frozenset[str] = frozenset()
    session_ttl = timedelta(hours=8)
    max_request_bytes = 1024 * 1024
    auth_rate_limiter = RequestRateLimiter(20, timedelta(minutes=1))

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

    def do_GET(self) -> None:
        """Dispatch read, health, OpenAPI, and Swagger UI requests."""
        try:
            if not self.require_allowed_origin():
                return
            parsed = urlparse(self.path)
            if self.static_dir is not None and not self.is_api_path(parsed.path):
                self.serve_static(parsed.path)
                return
            path_parts = self.path_parts(parsed.path)
            query = parse_qs(parsed.query)

            if path_parts == ["health"]:
                readiness = database_readiness(self.db_path)
                self.respond(
                    hateoas.health("ok" if readiness["ready"] else "unavailable"),
                    HTTPStatus.OK if readiness["ready"] else HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return

            if path_parts in ([], ["openapi.json"], ["docs"]):
                if self.require_authenticated(require_actor=False) is None:
                    return
                if path_parts == []:
                    self.respond(hateoas.api_root())
                elif path_parts == ["openapi.json"]:
                    self.respond(openapi.spec())
                else:
                    self.respond_html(self.docs_html())
                return

            if path_parts == ["session"]:
                context = self.require_authenticated(require_actor=False)
                if context is None:
                    return
                self.respond(
                    {
                        "authenticated": True,
                        "account_id": context.account_id,
                        "person_id": context.person_id,
                        "committee_member_id": context.committee_member_id,
                        "is_operator": context.is_operator,
                    }
                )
                return

            if self.require_authenticated() is None:
                return

            if path_parts == ["round-summary"]:
                round_id = int(query.get("round_id", ["1"])[0])
                self.require_round_access(round_id)
                summary = self.repository.round_summary(round_id)
                if summary is None:
                    self.respond({"error": "Exam round not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(hateoas.round_summary(summary, round_id))
                return

            if path_parts == ["scheduling-overview"]:
                self.respond(
                    hateoas.scheduling_overview(
                        self.repository.scheduling_overview(self.authorization_scope)
                    )
                )
                return

            if path_parts == ["confirmed-plans"]:
                self.respond(
                    hateoas.confirmed_plans(
                        self.repository.confirmed_plans(self.authorization_scope)
                    )
                )
                return

            if len(path_parts) == 2 and path_parts[0] == "confirmed-plan-days":
                day = self.repository.confirmed_plan_day(
                    int(path_parts[1]), self.authorization_scope
                )
                if day is None:
                    self.respond({"error": "Confirmed exam day not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(hateoas.confirmed_plan_day(day))
                return

            if path_parts and path_parts[0] == "candidate-committee-assignments":
                if len(path_parts) == 1:
                    candidate_id = query.get("candidate_id", [None])[0]
                    rows = self.repository.candidate_committee_assignments(
                        int(candidate_id) if candidate_id is not None else None,
                        self.authorization_scope,
                    )
                    self.respond(
                        hateoas.collection(
                            "candidate-committee-assignments",
                            CANDIDATE_COMMITTEE_ASSIGNMENT,
                            rows,
                            parsed.query,
                            allow_create=False,
                            allow_item_mutation=False,
                        )
                    )
                    return
                if len(path_parts) == 2:
                    row = self.repository.get_visible(
                        CANDIDATE_COMMITTEE_ASSIGNMENT,
                        int(path_parts[1]),
                        self.authorization_scope,
                    )
                    if row is None:
                        self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                        return
                    self.respond(
                        hateoas.resource_item(
                            "candidate-committee-assignments",
                            CANDIDATE_COMMITTEE_ASSIGNMENT,
                            row,
                            allow_item_mutation=False,
                        )
                    )
                    return

            resource_name, entity_id = self.resource_target(path_parts)
            if resource_name is None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return

            entity = REST_RESOURCES[resource_name]
            if entity_id is None:
                if resource_name in {"members", "memberships"}:
                    rows = self.repository.member_list(
                        self.resource_filters(entity, query), self.authorization_scope
                    )
                elif resource_name == "candidates":
                    rows = self.repository.candidate_list(self.authorization_scope)
                else:
                    filters = self.resource_filters(entity, query)
                    rows = self.repository.list_visible(entity, self.authorization_scope, filters)
                self.respond(
                    hateoas.collection(
                        resource_name,
                        entity,
                        rows,
                        parsed.query,
                    )
                )
                return

            row = (
                self.repository.member_get(entity_id, self.authorization_scope)
                if resource_name in {"members", "memberships"}
                else self.repository.get_visible(entity, entity_id, self.authorization_scope)
            )
            if row is None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.respond(hateoas.resource_item(resource_name, entity, row))
        except ForbiddenRequestError as error:
            self.respond({"error": str(error)}, HTTPStatus.FORBIDDEN)
        except ValueError:
            self.respond({"error": "Invalid request"}, HTTPStatus.BAD_REQUEST)
        except SQLAlchemyError as error:
            self.respond_database_error(error)

    def do_POST(self) -> None:
        """Dispatch creates and planning actions, translating domain errors to HTTP."""
        try:
            if not self.require_allowed_origin():
                return
            path_parts = self.path_parts(urlparse(self.path).path)
            if (
                path_parts
                and path_parts[0] == "auth"
                and not self.allow_public_auth_request(path_parts)
            ):
                return
            if path_parts == ["auth", "login"]:
                payload = self.read_json()
                result = self.local_auth_service.login(
                    payload.get("email", "") if isinstance(payload.get("email", ""), str) else "",
                    (
                        payload.get("password", "")
                        if isinstance(payload.get("password", ""), str)
                        else ""
                    ),
                    (
                        payload.get("second_factor", "")
                        if isinstance(payload.get("second_factor", ""), str)
                        else ""
                    ),
                    remote_key=self.client_address[0],
                )
                self.issue_session_cookies(result.credentials)
                self.respond(
                    {
                        "authenticated": True,
                        "account_id": result.account_id,
                        "expires_at": result.credentials.expires_at,
                    }
                )
                return

            if path_parts == ["auth", "invitation", "prepare"]:
                preparation = self.local_auth_service.prepare_invitation(
                    self.read_json().get("token", "")
                )
                self.respond(
                    {
                        "email": preparation.email,
                        "expires_at": preparation.expires_at,
                        "totp_secret": preparation.totp_secret,
                    }
                )
                return

            if path_parts == ["auth", "invitation", "activate"]:
                payload = self.read_json()
                account, recovery_codes = self.local_auth_service.activate_invitation(
                    payload.get("token", ""),
                    payload.get("password", ""),
                    payload.get("totp_secret", ""),
                    payload.get("totp_code", ""),
                )
                self.respond(
                    {
                        "activated": True,
                        "account": account,
                        "recovery_codes": recovery_codes,
                    }
                )
                return

            if path_parts == ["auth", "recovery", "prepare"]:
                preparation = self.local_auth_service.prepare_recovery(
                    self.read_json().get("token", "")
                )
                self.respond(
                    {
                        "email": preparation.email,
                        "expires_at": preparation.expires_at,
                        "totp_secret": preparation.totp_secret,
                    }
                )
                return

            if path_parts == ["auth", "recovery", "complete"]:
                payload = self.read_json()
                account, recovery_codes = self.local_auth_service.complete_recovery(
                    payload.get("token", ""),
                    payload.get("password", ""),
                    payload.get("totp_secret", ""),
                    payload.get("totp_code", ""),
                )
                self.respond(
                    {
                        "recovered": True,
                        "account": account,
                        "recovery_codes": recovery_codes,
                    }
                )
                return

            if path_parts == ["session", "rotate"]:
                context = self.require_authenticated(require_actor=False, require_csrf=True)
                if context is None:
                    return
                credentials = self.authentication_repository.rotate_session(
                    self.session_token(), ttl=self.session_ttl
                )
                if credentials is None:
                    self.respond({"error": "Authentication required."}, HTTPStatus.UNAUTHORIZED)
                    return
                self.issue_session_cookies(credentials)
                self.respond({"status": "rotated", "expires_at": credentials.expires_at})
                return

            if path_parts == ["session", "logout"]:
                context = self.require_authenticated(require_actor=False, require_csrf=True)
                if context is None:
                    return
                self.authentication_repository.revoke_session(self.session_token(), reason="logout")
                self.clear_session_cookies()
                self.respond({}, HTTPStatus.NO_CONTENT)
                return

            if self.require_authenticated(require_csrf=True) is None:
                return
            if (
                len(path_parts) == 5
                and path_parts[0] == "confirmed-plan-days"
                and path_parts[2] == "slots"
                and path_parts[4] == "start"
            ):
                day_id = int(path_parts[1])
                slot_id = int(path_parts[3])
                self.require_day_access(day_id, manage=True)
                self.repository.start_exam_slot(day_id, slot_id, self.read_json())
                day = self.repository.confirmed_plan_day(day_id, self.authorization_scope)
                if day is None:
                    self.respond({"error": "Confirmed exam day not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(hateoas.confirmed_plan_day(day))
                return

            if (
                len(path_parts) == 3
                and path_parts[0] == "exam-rounds"
                and path_parts[2] == "request-availabilities"
            ):
                self.require_round_access(int(path_parts[1]), manage=True)
                exam_round = self.planning_service.request_availabilities(int(path_parts[1]))
                self.respond(
                    hateoas.resource_item(
                        "exam-rounds",
                        REST_RESOURCES["exam-rounds"],
                        exam_round,
                    )
                )
                return

            if (
                len(path_parts) == 3
                and path_parts[0] == "exam-rounds"
                and path_parts[2] == "confirm-plan"
            ):
                self.require_round_access(int(path_parts[1]), manage=True)
                confirmed_plan = self.planning_service.confirm_plan(int(path_parts[1]))
                self.respond(hateoas.confirmed_plan(confirmed_plan))
                return

            if path_parts == ["planning-proposals"]:
                payload = self.read_json()
                round_id = int(payload.get("round_id", 1))
                self.require_round_access(round_id, manage=True)
                proposal = self.planning_service.generate_proposal(round_id)
                self.respond(hateoas.planning_proposal(proposal), HTTPStatus.CREATED)
                return

            if path_parts == ["candidate-exam-days", "generate"]:
                payload = self.read_json()
                round_id = int(payload.get("round_id", 1))
                self.require_round_access(round_id, manage=True)
                result = self.candidate_day_service.generate(round_id)
                self.respond(hateoas.candidate_day_generation(result))
                return

            resource_name, entity_id = self.resource_target(path_parts)
            if resource_name is None or entity_id is not None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return

            payload = self.authorize_resource_action(
                resource_name, None, self.read_json(), "create"
            )
            status = HTTPStatus.CREATED
            if resource_name == "candidates":
                row = self.repository.create_candidate(payload)
            elif resource_name == "planning-settings":
                row = self.repository.save_planning_settings(payload)
                status = HTTPStatus.OK
            elif resource_name == "member-availabilities":
                row = self.repository.save_member_availability(payload)
                status = HTTPStatus.OK
            elif resource_name in {"members", "memberships"}:
                row = self.repository.create_membership(payload)
            else:
                row = self.repository.create(REST_RESOURCES[resource_name], payload)
            self.respond(
                hateoas.resource_item(
                    resource_name,
                    REST_RESOURCES[resource_name],
                    row,
                ),
                status,
            )
        except ForbiddenRequestError as error:
            self.respond({"error": str(error)}, HTTPStatus.FORBIDDEN)
        except RequestTooLargeError as error:
            self.respond({"error": str(error)}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        except UnsupportedMediaTypeError as error:
            self.respond({"error": str(error)}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        except LocalAuthError as error:
            status = (
                HTTPStatus.TOO_MANY_REQUESTS
                if error.code == "rate_limited"
                else HTTPStatus.UNAUTHORIZED
            )
            if error.code in {"invalid_factor", "token_invalid"}:
                status = HTTPStatus.BAD_REQUEST
            if error.retry_after is not None:
                self._add_response_header("Retry-After", str(error.retry_after))
            self.respond({"error": str(error)}, status)
        except ValueError as error:
            self.respond({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except SQLAlchemyError as error:
            self.respond_database_error(error)

    def do_PATCH(self) -> None:
        """Dispatch partial updates through the repository validation boundary."""
        try:
            if not self.require_allowed_origin():
                return
            if self.require_authenticated(require_csrf=True) is None:
                return
            path_parts = self.path_parts(urlparse(self.path).path)
            if (
                len(path_parts) == 5
                and path_parts[0] == "confirmed-plan-days"
                and path_parts[2] in {"slots", "assignments"}
                and path_parts[4] == "attendance"
            ):
                day_id = int(path_parts[1])
                entity_id = int(path_parts[3])
                member_id = None
                if path_parts[2] == "assignments":
                    assignment = self.repository.get(EXAM_DAY_ASSIGNMENT, entity_id)
                    member_id = assignment.get("committee_member_id") if assignment else None
                self.require_day_access(
                    day_id,
                    manage=path_parts[2] == "slots",
                    member_id=member_id,
                )
                payload = self.read_json()
                if path_parts[2] == "slots":
                    self.repository.save_candidate_attendance(day_id, entity_id, payload)
                else:
                    self.repository.save_member_attendance(day_id, entity_id, payload)
                day = self.repository.confirmed_plan_day(day_id, self.authorization_scope)
                if day is None:
                    self.respond({"error": "Confirmed exam day not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(hateoas.confirmed_plan_day(day))
                return

            if (
                len(path_parts) == 5
                and path_parts[0] == "confirmed-plan-days"
                and path_parts[2] == "slots"
                and path_parts[4] == "status"
            ):
                day_id = int(path_parts[1])
                slot_id = int(path_parts[3])
                self.require_day_access(day_id, manage=True)
                self.repository.update_exam_slot_status(day_id, slot_id, self.read_json())
                day = self.repository.confirmed_plan_day(day_id, self.authorization_scope)
                if day is None:
                    self.respond({"error": "Confirmed exam day not found"}, HTTPStatus.NOT_FOUND)
                    return
                self.respond(hateoas.confirmed_plan_day(day))
                return

            resource_name, entity_id = self.resource_target(path_parts)
            if resource_name is None or entity_id is None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return

            payload = self.authorize_resource_action(
                resource_name, entity_id, self.read_json(), "update"
            )
            if resource_name == "planning-settings":
                row = self.repository.update_planning_settings(entity_id, payload)
            elif resource_name == "member-availabilities":
                row = self.repository.update_member_availability(entity_id, payload)
            elif resource_name == "candidates":
                row = self.repository.update_candidate(entity_id, payload)
            elif resource_name == "exam-rounds":
                row = self.repository.update_exam_round(entity_id, payload)
            elif resource_name in {"members", "memberships"}:
                row = self.repository.update_membership(entity_id, payload)
            else:
                row = self.repository.update(
                    REST_RESOURCES[resource_name],
                    entity_id,
                    payload,
                )
            if row is None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.respond(
                hateoas.resource_item(
                    resource_name,
                    REST_RESOURCES[resource_name],
                    row,
                )
            )
        except ForbiddenRequestError as error:
            self.respond({"error": str(error)}, HTTPStatus.FORBIDDEN)
        except RequestTooLargeError as error:
            self.respond({"error": str(error)}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        except UnsupportedMediaTypeError as error:
            self.respond({"error": str(error)}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        except ValueError as error:
            self.respond({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except SQLAlchemyError as error:
            self.respond_database_error(error)

    def do_DELETE(self) -> None:
        try:
            if not self.require_allowed_origin():
                return
            if self.require_authenticated(require_csrf=True) is None:
                return
            resource_name, entity_id = self.resource_target(
                self.path_parts(urlparse(self.path).path)
            )
            if resource_name is None or entity_id is None:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return

            self.authorize_resource_action(resource_name, entity_id, {}, "delete")
            if resource_name == "candidates":
                deleted = self.repository.delete_candidate(entity_id)
            else:
                deleted = self.repository.delete(REST_RESOURCES[resource_name], entity_id)
            if not deleted:
                self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.respond({}, HTTPStatus.NO_CONTENT)
        except ForbiddenRequestError as error:
            self.respond({"error": str(error)}, HTTPStatus.FORBIDDEN)
        except SQLAlchemyError as error:
            self.respond_database_error(error)

    def do_OPTIONS(self) -> None:
        """Answer only explicit, allowlisted API CORS preflight requests."""
        origin = self.headers.get("Origin")
        if not self.is_api_path(urlparse(self.path).path) or not origin:
            self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        if not self.require_allowed_origin():
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CSRF-Token")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def health(self) -> dict:
        readiness = database_readiness(self.db_path)
        return hateoas.health("ok" if readiness["ready"] else "unavailable")

    def require_authenticated(
        self,
        *,
        require_actor: bool = True,
        require_csrf: bool = False,
    ) -> AuthContext | None:
        """Authenticate the request and enforce the shared CSRF policy."""
        context = self.authentication_repository.authenticate(self.session_token())
        if context is None:
            self.respond({"error": "Authentication required."}, HTTPStatus.UNAUTHORIZED)
            return None
        self.auth_context = context
        self.authorization_scope = self.authorization_service.scope(context)
        if require_csrf and not self.authentication_repository.verify_csrf(
            context, self.headers.get("X-CSRF-Token")
        ):
            self.respond({"error": "CSRF validation failed."}, HTTPStatus.FORBIDDEN)
            return None
        if require_actor and not self.authorization_scope.has_active_membership:
            self.respond({"error": "Forbidden."}, HTTPStatus.FORBIDDEN)
            return None
        return context

    def require_allowed_origin(self) -> bool:
        """Reject browser cross-origin requests unless the origin is exact and explicit."""
        origin = self.headers.get("Origin")
        if (
            origin is None
            or self.origin_is_same_host(origin)
            or self.allowed_cors_origin(origin) is not None
        ):
            return True
        self.respond({"error": "Cross-origin request is not allowed."}, HTTPStatus.FORBIDDEN)
        return False

    def origin_is_same_host(self, origin: str) -> bool:
        origin_authority = self.normalized_origin_authority(origin)
        if origin_authority is None:
            return False
        scheme, hostname, port = origin_authority
        host_authority = self.normalized_host_authority(self.headers.get("Host", ""), scheme=scheme)
        return host_authority == (hostname, port)

    @staticmethod
    def normalized_origin_authority(origin: str) -> tuple[str, str, int] | None:
        """Return a canonical browser origin while rejecting malformed authorities."""
        try:
            parsed = urlparse(origin)
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            return None
        return (
            parsed.scheme,
            parsed.hostname.lower(),
            port or (443 if parsed.scheme == "https" else 80),
        )

    @staticmethod
    def normalized_host_authority(host: str, *, scheme: str) -> tuple[str, int] | None:
        """Normalize Host using the request-origin scheme without trusting malformed ports."""
        try:
            parsed = urlparse(f"{scheme}://{host}")
            port = parsed.port
        except ValueError:
            return None
        if (
            scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            return None
        return parsed.hostname.lower(), port or (443 if scheme == "https" else 80)

    def allowed_cors_origin(self, requested_origin: str) -> str | None:
        """Select only a validated configured value for a reflected CORS header."""
        return next(
            (allowed for allowed in self.cors_allowed_origins if requested_origin == allowed),
            None,
        )

    def allow_public_auth_request(self, path_parts: list[str]) -> bool:
        endpoint = "/".join(path_parts)
        remote_key = self.client_address[0] if self.client_address else "unknown"
        retry_after = self.auth_rate_limiter.check(f"{remote_key}:{endpoint}")
        if retry_after is None:
            return True
        self._add_response_header("Retry-After", str(retry_after))
        self.respond({"error": "Too many requests."}, HTTPStatus.TOO_MANY_REQUESTS)
        return False

    @property
    def authorization_scope(self) -> AuthorizationScope:
        return getattr(
            self,
            "_authorization_scope",
            AuthorizationScope(None, frozenset(), frozenset(), frozenset(), frozenset(), {}),
        )

    @authorization_scope.setter
    def authorization_scope(self, scope: AuthorizationScope) -> None:
        self._authorization_scope = scope

    def require_round_access(self, round_id: int, *, manage: bool = False) -> None:
        """Enforce round access without disclosing whether another round exists."""
        repository = self.repository
        round_data = repository.get(EXAM_ROUND, round_id)
        committee_id = round_data["committee_id"] if round_data is not None else None
        allowed = (
            self.authorization_scope.can_manage_committee(committee_id)
            if manage
            else self.authorization_scope.can_read_committee(committee_id)
        )
        if not allowed:
            raise ForbiddenRequestError("Forbidden.")

    def require_day_access(
        self,
        day_id: int,
        *,
        manage: bool = False,
        member_id: int | None = None,
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
        self,
        resource_name: str,
        entity_id: int | None,
        payload: dict,
        action: str,
    ) -> dict:
        """Authorize a CRUD action and replace all client-supplied actor IDs."""
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
            if not self.authorization_scope.management_committee_ids:
                raise ForbiddenRequestError("Forbidden.")
            return normalized

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

    def session_token(self) -> str | None:
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        morsel = cookies.get(self.session_cookie_name)
        return morsel.value if morsel is not None else None

    def issue_session_cookies(self, credentials: SessionCredentials) -> None:
        self._add_response_header("Set-Cookie", self._session_cookie(credentials.token))
        self._add_response_header("Set-Cookie", self._csrf_cookie(credentials.csrf_token))

    def clear_session_cookies(self) -> None:
        self._add_response_header("Set-Cookie", self._session_cookie("", max_age=0))
        self._add_response_header("Set-Cookie", self._csrf_cookie("", max_age=0))

    def _session_cookie(self, value: str, *, max_age: int = 8 * 60 * 60) -> str:
        return self._cookie(
            self.session_cookie_name,
            value,
            max_age=int(self.session_ttl.total_seconds()) if value else max_age,
            http_only=True,
        )

    def _csrf_cookie(self, value: str, *, max_age: int = 8 * 60 * 60) -> str:
        return self._cookie(
            self.csrf_cookie_name,
            value,
            max_age=int(self.session_ttl.total_seconds()) if value else max_age,
            http_only=False,
        )

    def _cookie(self, name: str, value: str, *, max_age: int, http_only: bool) -> str:
        attributes = [f"{name}={value}", f"Max-Age={max_age}", "Path=/", "SameSite=Strict"]
        if self.cookie_secure:
            attributes.append("Secure")
        if http_only:
            attributes.append("HttpOnly")
        return "; ".join(attributes)

    def _add_response_header(self, name: str, value: str) -> None:
        headers = getattr(self, "_response_headers", None)
        if headers is None:
            headers = []
            self._response_headers = headers
        headers.append((name, value))

    def respond_database_error(self, error: SQLAlchemyError) -> None:
        """Map persistence failures to stable public HTTP messages and statuses."""
        if isinstance(error, IntegrityError):
            self.respond({"error": "Database constraint violated."}, HTTPStatus.CONFLICT)
            return
        if isinstance(error, OperationalError) and "locked" in str(error).lower():
            self.respond(
                {"error": "The database is busy; retry the request."},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        self.respond({"error": "Database operation failed."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def resource_target(self, path_parts: list[str]) -> tuple[str | None, int | None]:
        if len(path_parts) not in (1, 2):
            return None, None
        resource_name = path_parts[0]
        if resource_name not in REST_RESOURCES:
            return None, None
        if len(path_parts) == 1:
            return resource_name, None
        return resource_name, int(path_parts[1])

    def path_parts(self, path: str) -> list[str]:
        normalized = path.strip("/")
        if normalized == "api":
            return []
        if normalized.startswith("api/"):
            normalized = normalized[4:]
        return [part for part in normalized.split("/") if part]

    @staticmethod
    def is_api_path(path: str) -> bool:
        """Keep API routes outside the static SPA fallback boundary."""
        return path == "/api" or path.startswith("/api/")

    def serve_static(self, request_path: str) -> None:
        """Serve an asset or the Angular shell without allowing path escapes."""
        static_dir = self.static_dir
        if static_dir is None:
            self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        try:
            decoded_path = unquote(request_path)
            if (
                not decoded_path.startswith("/")
                or any(ord(character) < 32 or ord(character) == 127 for character in decoded_path)
                or any(part in {".", ".."} for part in decoded_path.split("/"))
            ):
                raise ValueError
            assets = trusted_static_assets(static_dir)
        except ValueError, OSError:
            self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        asset = assets.get(decoded_path)
        asset_path = (
            decoded_path in {"/favicon.ico", "/favicon.svg", "/robots.txt"}
            or decoded_path == "/assets"
            or decoded_path.startswith("/assets/")
            or "." in decoded_path.rsplit("/", 1)[-1]
        )
        if asset is not None:
            self.respond_static_asset(asset)
            return
        if asset_path:
            self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        index_asset = assets.get("/index.html")
        if index_asset is None:
            self.respond({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        self.respond_static_asset(index_asset, cache_control="no-cache")

    def respond_static_asset(self, asset: StaticAsset, *, cache_control: str | None = None) -> None:
        """Write one preloaded trusted asset without reflecting request metadata."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Cache-Control", cache_control or "public, max-age=31536000, immutable")
        self.send_security_headers()
        self.send_header("Content-Type", asset.content_type)
        self.send_header("Content-Length", str(len(asset.body)))
        self.end_headers()
        try:
            self.wfile.write(asset.body)
        except BrokenPipeError, ConnectionResetError:
            pass

    def resource_filters(self, resource: Resource, query: dict[str, list[str]]) -> dict:
        aliases = {"round_id": "exam_round_id"}
        fields = set(resource.readable_fields)
        filters = {}
        for key, values in query.items():
            field = aliases.get(key, key)
            if field not in fields or not values:
                continue
            filters[field] = self.normalize_filter_value(field, values[0])
        return filters

    def normalize_filter_value(self, field: str, value: str):
        if field == "id" or field.endswith("_id") or field in {"is_active"}:
            return int(value)
        return value

    def read_json(self) -> dict:
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Transfer-Encoding is not supported")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid Content-Length") from error
        if length < 0:
            raise ValueError("Invalid Content-Length")
        if length == 0:
            return {}
        if length > self.max_request_bytes:
            raise RequestTooLargeError(f"Request body exceeds {self.max_request_bytes} bytes.")
        if self.headers.get_content_type() != "application/json":
            raise UnsupportedMediaTypeError("Content-Type must be application/json.")
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete request body")
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid JSON body") from error
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return self.normalize_payload(payload)

    def normalize_payload(self, payload: dict) -> dict:
        normalized = dict(payload)
        if "specialization_label" in normalized:
            normalized.pop("specialization_label")
        if "attempt_number" in normalized:
            normalized["attempt_number"] = max(1, int(normalized["attempt_number"]))
        if "requires_mep" in normalized:
            normalized["requires_mep"] = self.normalize_bool(normalized["requires_mep"])
        if "is_active" in normalized:
            normalized["is_active"] = self.normalize_bool(normalized["is_active"])
        if "lunch_break_enabled" in normalized:
            normalized["lunch_break_enabled"] = self.normalize_bool(
                normalized["lunch_break_enabled"]
            )
        if "exclude_public_holidays" in normalized:
            normalized["exclude_public_holidays"] = self.normalize_bool(
                normalized["exclude_public_holidays"]
            )
        if CANDIDATE.table in normalized:
            normalized.pop(CANDIDATE.table)
        return normalized

    def normalize_bool(self, value) -> int:
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

    def respond(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = b"" if status == HTTPStatus.NO_CONTENT else self.json_bytes(payload)
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        if body:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in getattr(self, "_response_headers", []):
            self.send_header(name, value)
        self._response_headers = []
        self.end_headers()
        if body:
            try:
                self.wfile.write(body)
            except BrokenPipeError, ConnectionResetError:
                pass

    def respond_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in getattr(self, "_response_headers", []):
            self.send_header(name, value)
        self._response_headers = []
        self.end_headers()
        self.wfile.write(body)

    def json_bytes(self, payload) -> bytes:
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def docs_html(self) -> str:
        return """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>lzug API Docs</title>
</head>
<body>
  <main>
    <h1>lzug API</h1>
    <p>Die maschinenlesbare Beschreibung ist als
      <a href="/api/openapi.json">OpenAPI-Dokument</a> verfügbar.</p>
  </main>
</body>
</html>"""

    def send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Permitted-Cross-Domain-Policies", "none")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
            "img-src 'self' data:; connect-src 'self'",
        )
        if self.https_only:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        origin = self.headers.get("Origin")
        allowed_origin = self.allowed_cors_origin(origin) if origin is not None else None
        if allowed_origin is not None:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        """Log only transport metadata, never client addresses, queries, headers, or bodies."""
        path = urlparse(self.path).path
        print(f"http_request method={self.command} path={path} status={code} bytes={size}")

    def log_message(self, format: str, *args) -> None:
        print("http_server event=protocol_message")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the lzug demo backend.")
    parser.add_argument("--host", default=os.environ.get("LZUG_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("LZUG_PORT", "8000")))
    parser.add_argument(
        "--static-dir",
        default=os.environ.get("LZUG_STATIC_DIR"),
        help="Angular production output directory",
    )
    parser.add_argument("--db", dest="db_value", help="SQLite database path")
    parser.add_argument("--data-dir", help="Persistent data directory (default: /data)")
    parser.add_argument("--documents", help="Document storage directory")
    parser.add_argument("--backups", help="Backup directory")
    parser.add_argument(
        "--database-url",
        help="SQLite database URL, for example sqlite:////data/lzug.sqlite",
    )
    parser.add_argument("--init", action="store_true", help="Create schema before starting.")
    parser.add_argument("--seed", action="store_true", help="Load demo data with --init.")
    parser.add_argument("--reset", action="store_true", help="Delete the database before --init.")
    args = parser.parse_args()
    if args.db_value and args.database_url:
        parser.error("Use only one of --db and --database-url")
    try:
        args.paths = persistence_paths(
            data_dir=args.data_dir,
            database=args.database_url or args.db_value,
            documents=args.documents,
            backups=args.backups,
        )
        args.db = args.paths.database
        args.static_dir = Path(args.static_dir).expanduser() if args.static_dir else None
    except (ValueError, PersistenceConfigurationError) as error:
        parser.error(str(error))
    if args.static_dir is not None and not (args.static_dir / "index.html").is_file():
        parser.error(f"Static directory must contain index.html: {args.static_dir}")
    return args


def main() -> None:
    args = parse_args()
    try:
        runtime_security = RuntimeSecurityConfig.from_environment()
    except ValueError as error:
        raise SystemExit(f"Invalid security configuration: {error}") from error
    try:
        validate_persistence(args.paths)
    except PersistenceConfigurationError as error:
        raise SystemExit(f"Persistent storage is not ready: {error}") from error
    try:
        if args.init:
            initialize(
                args.db,
                with_seed=args.seed,
                reset=args.reset,
                backup_dir=args.paths.backups,
            )
    except MigrationError as error:
        raise SystemExit(f"Database migration failed: {error}") from error
    readiness = database_readiness(args.db)
    if not readiness["ready"]:
        raise SystemExit(
            f"Database is not ready: {args.db}. "
            f"Reason: {readiness['reason']}. "
            "Start with --init to initialize or migrate it, then retry."
        )

    try:
        validate_persistence(args.paths, require_database=True)
    except PersistenceConfigurationError as error:
        raise SystemExit(f"Persistent storage is not ready: {error}") from error

    LzugHandler.db_path = args.db
    LzugHandler.static_dir = args.static_dir
    LzugHandler.cookie_secure = runtime_security.https_only
    LzugHandler.session_cookie_name = (
        "__Host-lzug_session" if runtime_security.https_only else "lzug_session"
    )
    LzugHandler.https_only = runtime_security.https_only
    LzugHandler.cors_allowed_origins = runtime_security.cors_allowed_origins
    LzugHandler.session_ttl = runtime_security.session_ttl
    LzugHandler.max_request_bytes = runtime_security.max_request_bytes
    LzugHandler.auth_rate_limiter = RequestRateLimiter(
        runtime_security.auth_rate_limit,
        runtime_security.auth_rate_window,
    )
    server = ThreadingHTTPServer((args.host, args.port), LzugHandler)
    server.daemon_threads = True
    print(f"lzug backend listening on http://{args.host}:{args.port}")
    print(f"database: {args.db}")

    def request_shutdown(signum: int, _frame) -> None:
        print(f"received signal {signum}; shutting down")
        threading.Thread(target=server.shutdown, name="lzug-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    server_thread = threading.Thread(target=server.serve_forever, name="lzug-http", daemon=True)
    server_thread.start()
    try:
        server_thread.join()
    finally:
        server.server_close()
        server_thread.join()


if __name__ == "__main__":
    main()
