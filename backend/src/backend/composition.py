"""Concrete application wiring for the canonical backend runtime."""

from __future__ import annotations

from pathlib import Path

from backend.identity.authorization import AuthorizationService
from backend.identity.committee_admin import CommitteeAdminService
from backend.identity.people import IdentityService
from backend.integrations.holiday_provider import PythonHolidaysProvider
from backend.integrations.map_provider import planning_requires_confirmed_coordinates
from backend.persistence.candidate_days import SQLiteCandidateDayUnitOfWorkFactory
from backend.persistence.committee_admin import SQLiteCommitteeAdminUnitOfWorkFactory
from backend.persistence.identity import (
    SQLiteIdentityQueryFactory,
    SQLiteIdentityUnitOfWorkFactory,
)
from backend.persistence.planning_resources import SQLitePlanningResourceUnitOfWorkFactory
from backend.planning.candidate_days import CandidateDayService


def candidate_day_service(db_path: Path) -> CandidateDayService:
    """Wire the planning port to SQLite and the configured holiday adapter."""
    return CandidateDayService(
        SQLiteCandidateDayUnitOfWorkFactory(db_path),
        PythonHolidaysProvider(),
    )


def planning_resource_unit_of_work_factory(
    db_path: Path,
) -> SQLitePlanningResourceUnitOfWorkFactory:
    """Wire Planning master-data commands to SQLite and current room policy."""
    return SQLitePlanningResourceUnitOfWorkFactory(
        db_path,
        require_confirmed_coordinates=planning_requires_confirmed_coordinates(),
    )


def identity_service(db_path: Path) -> IdentityService:
    """Wire Identity's write/read ports to their SQLite adapters."""
    return IdentityService(
        SQLiteIdentityUnitOfWorkFactory(db_path),
        SQLiteIdentityQueryFactory(db_path),
    )


def authorization_service(db_path: Path) -> AuthorizationService:
    """Wire actor resolution to Identity's active-membership query port."""
    return AuthorizationService(identity_service(db_path))


def committee_admin_service(db_path: Path) -> CommitteeAdminService:
    """Wire Identity committee commands to their transactional SQLite adapter."""
    return CommitteeAdminService(SQLiteCommitteeAdminUnitOfWorkFactory(db_path))
