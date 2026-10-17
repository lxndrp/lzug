"""HTTP application adapters that preserve established response contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from backend import http_hateoas as hateoas
from backend.application import AuthenticationRequiredError, ForbiddenRequestError
from backend.application.repositories import ResourceRepository
from backend.identity.auth import AuthenticationRepository
from backend.identity.authorization import AuthorizationScope, AuthorizationService
from backend.identity.local_auth import LocalAuthService
from backend.persistence.database import DEFAULT_DB_PATH, database_readiness
from backend.planning.resources import PlanningResourceService
from backend.runtime import RuntimeCoordinator


@dataclass(frozen=True)
class ApplicationResult:
    """HTTP payload and status produced at the adapter boundary."""

    payload: dict[str, Any]
    status: HTTPStatus = HTTPStatus.OK


@dataclass(frozen=True)
class ApplicationServices:
    """Injectable factories for the HTTP application adapter."""

    readiness_probe: Callable[[Path], dict[str, object]] = database_readiness
    repository_factory: Callable[[Path], ResourceRepository] = ResourceRepository
    authentication_factory: Callable[[Path], AuthenticationRepository] | None = None
    local_authentication_factory: Callable[..., LocalAuthService] | None = None
    authorization_factory: Callable[[Path], AuthorizationService] | None = None
    planning_resource_service_factory: Callable[[Path], PlanningResourceService] | None = None


class ReadApplication:
    """HTTP read flows assembled from framework-independent services."""

    def __init__(
        self, db_path: Path = DEFAULT_DB_PATH, services: ApplicationServices | None = None
    ):
        self.db_path = Path(db_path)
        self.services = services or ApplicationServices()
        self.runtime: RuntimeCoordinator | None = None

    def health(self) -> ApplicationResult:
        return ApplicationResult(hateoas.health("ok"))

    def readiness(self) -> ApplicationResult:
        return self.lifecycle(readiness=True)

    def lifecycle(self, *, readiness: bool = False) -> ApplicationResult:
        from backend.public_lifecycle import public_lifecycle

        snapshot = (
            self.runtime.snapshot()
            if self.runtime is not None
            else self.services.readiness_probe(self.db_path)
        )
        lifecycle = public_lifecycle(snapshot)
        ready = lifecycle["ready"]
        payload = hateoas.health("ready" if ready else "unavailable", signal="ready")
        if not readiness:
            payload["_links"] = {"self": {"href": "/api/lifecycle"}}
        return ApplicationResult(
            {**payload, **lifecycle},
            HTTPStatus.OK if ready or not readiness else HTTPStatus.SERVICE_UNAVAILABLE,
        )

    def authenticated_scope(self, token: str | None) -> AuthorizationScope:
        if self.services.authentication_factory is None:
            raise RuntimeError(
                "Authentication repository factory must be injected by the composition root"
            )
        context = self.services.authentication_factory(self.db_path).authenticate(token)
        if context is None:
            raise AuthenticationRequiredError
        if self.services.authorization_factory is None:
            raise RuntimeError(
                "Authorization service factory must be injected by the composition root"
            )
        scope = self.services.authorization_factory(self.db_path).scope(context)
        if not scope.has_active_membership:
            raise ForbiddenRequestError("Forbidden.")
        return scope

    def round_summary(self, scope: AuthorizationScope, round_id: int) -> ApplicationResult:
        if self.services.planning_resource_service_factory is None:
            raise RuntimeError("Planning resource service factory must be injected by composition")
        summary = self.services.planning_resource_service_factory(self.db_path).round_summary(
            round_id, scope.committee_ids
        )
        if summary is None:
            raise ForbiddenRequestError("Forbidden.")
        return ApplicationResult(hateoas.round_summary(summary.as_payload(), round_id))


def database_error_result(error: SQLAlchemyError) -> ApplicationResult:
    """Map persistence failures to the established HTTP response contract."""
    if isinstance(error, IntegrityError):
        return ApplicationResult({"error": "Database constraint violated."}, HTTPStatus.CONFLICT)
    if isinstance(error, OperationalError) and "locked" in str(error).lower():
        return ApplicationResult(
            {"error": "The database is busy; retry the request."}, HTTPStatus.SERVICE_UNAVAILABLE
        )
    return ApplicationResult(
        {"error": "Database operation failed."}, HTTPStatus.INTERNAL_SERVER_ERROR
    )
