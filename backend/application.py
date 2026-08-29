"""Framework-neutral application flows shared by HTTP adapters.

The module composes existing authentication, authorization, readiness, and
repository implementations. It deliberately contains no FastAPI or Starlette
imports so adapters can change without leaking framework types into services or
repositories.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from . import hateoas
from .auth import AuthenticationRepository
from .authorization import AuthorizationScope, AuthorizationService
from .database import DEFAULT_DB_PATH, database_readiness
from .models import EXAM_ROUND
from .repositories import ResourceRepository


class AuthenticationRequiredError(Exception):
    """Signal missing or invalid session material at an HTTP boundary."""


class ForbiddenRequestError(Exception):
    """Signal a valid session without authorization for request context."""


@dataclass(frozen=True)
class ApplicationResult:
    """Transport-neutral JSON payload and its stable HTTP status."""

    payload: dict[str, Any]
    status: HTTPStatus = HTTPStatus.OK


@dataclass(frozen=True)
class ApplicationServices:
    """Injectable database and service factories for one application core."""

    readiness_probe: Callable[[Path], dict[str, object]] = database_readiness
    repository_factory: Callable[[Path], ResourceRepository] = ResourceRepository
    authentication_factory: Callable[[Path], AuthenticationRepository] = AuthenticationRepository
    authorization_factory: Callable[[Path], AuthorizationService] = AuthorizationService


class ReadApplication:
    """Synchronous application flows used by the old and new HTTP adapters."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        services: ApplicationServices | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.services = services or ApplicationServices()

    def health(self) -> ApplicationResult:
        """Return pure process liveness without touching persistence."""
        return ApplicationResult(hateoas.health("ok"))

    def readiness(self) -> ApplicationResult:
        """Return application and database readiness without exposing diagnostics."""
        readiness = self.services.readiness_probe(self.db_path)
        ready = bool(readiness["ready"])
        return ApplicationResult(
            hateoas.health("ready" if ready else "unavailable", signal="ready"),
            HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
        )

    def authenticated_scope(self, token: str | None) -> AuthorizationScope:
        """Resolve the existing session and active committee-membership contract."""
        context = self.services.authentication_factory(self.db_path).authenticate(token)
        if context is None:
            raise AuthenticationRequiredError
        scope = self.services.authorization_factory(self.db_path).scope(context)
        if not scope.has_active_membership:
            raise ForbiddenRequestError("Forbidden.")
        return scope

    def round_summary(self, scope: AuthorizationScope, round_id: int) -> ApplicationResult:
        """Return the existing linked read model after committee authorization."""
        repository = self.services.repository_factory(self.db_path)
        round_data = repository.get(EXAM_ROUND, round_id)
        committee_id = round_data["committee_id"] if round_data is not None else None
        if not scope.can_read_committee(committee_id):
            raise ForbiddenRequestError("Forbidden.")
        summary = repository.round_summary(round_id)
        if summary is None:
            return ApplicationResult(
                {"error": "Exam round not found"},
                HTTPStatus.NOT_FOUND,
            )
        return ApplicationResult(hateoas.round_summary(summary, round_id))


def database_error_result(error: SQLAlchemyError) -> ApplicationResult:
    """Map persistence failures to the public contract shared by both adapters."""
    if isinstance(error, IntegrityError):
        return ApplicationResult(
            {"error": "Database constraint violated."},
            HTTPStatus.CONFLICT,
        )
    if isinstance(error, OperationalError) and "locked" in str(error).lower():
        return ApplicationResult(
            {"error": "The database is busy; retry the request."},
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    return ApplicationResult(
        {"error": "Database operation failed."},
        HTTPStatus.INTERNAL_SERVER_ERROR,
    )
