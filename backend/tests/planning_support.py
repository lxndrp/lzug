"""Planning test wiring for the SQLite adapter and request-scoped permissions."""

from __future__ import annotations

from pathlib import Path

from backend.application.resource_access import ResourceKind
from backend.application.resource_authorization import ResourceAuthorizer
from backend.identity.authorization import AuthorizationScope
from backend.persistence.planning_resources import SQLitePlanningResourceUnitOfWorkFactory
from backend.persistence.resource_access import SQLiteResourceAccessQueryFactory
from backend.planning.resources import PlanningResourceService


def planning_resource_service(
    db_path: Path, scope: AuthorizationScope | None = None
) -> PlanningResourceService:
    """Build the real SQLite Planning service with optional transaction auth."""
    query_factory = SQLiteResourceAccessQueryFactory(db_path)
    authorize = None
    if scope is not None:
        authorizer = ResourceAuthorizer(query_factory, scope)

        def authorize(queries, resource, entity_id, payload):
            return authorizer.authorize_with_queries(
                queries, ResourceKind(resource), entity_id, payload
            )

    return PlanningResourceService(SQLitePlanningResourceUnitOfWorkFactory(db_path), authorize)
