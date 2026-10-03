"""Concrete application wiring for the canonical backend runtime."""

from __future__ import annotations

from pathlib import Path

from backend.application.exam_venue_api import ExamVenueApi
from backend.identity.authorization import AuthorizationService
from backend.identity.committee_admin import CommitteeAdminService
from backend.identity.people import IdentityService
from backend.integrations.holiday_provider import PythonHolidaysProvider
from backend.integrations.map_provider import MapProviderConfig, NominatimGeocoder
from backend.persistence.candidate_days import SQLiteCandidateDayUnitOfWorkFactory
from backend.persistence.committee_admin import SQLiteCommitteeAdminUnitOfWorkFactory
from backend.persistence.database import DEFAULT_DB_PATH
from backend.persistence.identity import (
    SQLiteIdentityQueryFactory,
    SQLiteIdentityUnitOfWorkFactory,
)
from backend.persistence.sqlite_exam_venues import SQLiteExamVenueRepository
from backend.planning.candidate_days import CandidateDayService
from backend.planning.exam_venues import ExamVenueService
from backend.planning.venue_consequences import VenueConsequenceService
from backend.planning_ports import Geocoder, VenueChange, VenueChangeFollowUp

DEFAULT_MAP_PROVIDER_CONFIG = MapProviderConfig()


def candidate_day_service(db_path: Path) -> CandidateDayService:
    """Wire the planning port to SQLite and the configured holiday adapter."""
    return CandidateDayService(
        SQLiteCandidateDayUnitOfWorkFactory(db_path),
        PythonHolidaysProvider(),
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


def venue_geocoder(config: MapProviderConfig) -> Geocoder:
    """Construct the configured geocoder adapter at the application root."""
    return NominatimGeocoder(config)


def exam_venue_service(
    db_path: Path = DEFAULT_DB_PATH,
    map_provider: MapProviderConfig = DEFAULT_MAP_PROVIDER_CONFIG,
) -> ExamVenueService:
    """Wire Planning's venue ports to SQLite and the configured provider adapter."""
    consequences = VenueConsequenceService(db_path)
    return ExamVenueService(
        SQLiteExamVenueRepository(
            db_path,
            require_confirmed_coordinates=map_provider.active,
            impact_query=consequences,
        ),
        geocoder=venue_geocoder(map_provider),
        follow_up=_VenueAuditFollowUp(consequences),
    )


def exam_venue_api(
    db_path: Path = DEFAULT_DB_PATH,
    map_provider: MapProviderConfig = DEFAULT_MAP_PROVIDER_CONFIG,
) -> ExamVenueApi:
    """Wire the API consumer to Planning ports and database-scoped services."""
    consequences = VenueConsequenceService(db_path)
    return ExamVenueApi(
        ExamVenueService(
            SQLiteExamVenueRepository(
                db_path,
                require_confirmed_coordinates=map_provider.active,
                impact_query=consequences,
            ),
            geocoder=venue_geocoder(map_provider),
            follow_up=_VenueAuditFollowUp(consequences),
        ),
        map_provider,
        consequences,
    )


class _VenueAuditFollowUp(VenueChangeFollowUp):
    """Execute the existing audit-driven follow-up as an explicit transition."""

    def __init__(self, consequences: VenueConsequenceService) -> None:
        self.consequences = consequences

    def process(self, change: VenueChange):
        return self.consequences.process_audit(change.audit_id)
