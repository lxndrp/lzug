"""Concrete application wiring for the canonical backend runtime."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from backend.application.exam_venue_api import ExamVenueApi
from backend.identity.admin_service import OperatorAuthService
from backend.identity.auth import AuthenticationRepository
from backend.identity.authorization import AuthorizationService
from backend.identity.committee_admin import CommitteeAdminService
from backend.identity.local_auth import LocalAuthService
from backend.identity.people import IdentityService
from backend.integrations.holiday_provider import PythonHolidaysProvider
from backend.integrations.map_provider import MapProviderConfig, NominatimGeocoder
from backend.integrations.notification_delivery import NotificationDeliveryGateway
from backend.notifications.service import NotificationService
from backend.persistence.auth import (
    SQLiteAuthenticationRepository,
    SQLiteOperatorAuthUnitOfWorkFactory,
)
from backend.persistence.candidate_days import SQLiteCandidateDayUnitOfWorkFactory
from backend.persistence.committee_admin import SQLiteCommitteeAdminUnitOfWorkFactory
from backend.persistence.database import DEFAULT_DB_PATH
from backend.persistence.identity import (
    SQLiteIdentityQueryFactory,
    SQLiteIdentityUnitOfWorkFactory,
)
from backend.persistence.local_auth import (
    SQLiteLocalAuthenticationKey,
    SQLiteLocalAuthUnitOfWorkFactory,
)
from backend.persistence.notifications import (
    SQLiteNotificationDeliveryUnitOfWorkFactory,
    SQLiteNotificationUnitOfWorkFactory,
)
from backend.persistence.planning_resources import SQLitePlanningResourceUnitOfWorkFactory
from backend.persistence.sqlite_exam_venues import SQLiteExamVenueRepository
from backend.planning.candidate_days import CandidateDayService
from backend.planning.exam_venues import ExamVenuePolicy, ExamVenueService
from backend.planning.venue_consequences import VenueConsequenceService
from backend.planning_ports import Geocoder, VenueChange, VenueChangeFollowUp
from backend.settings import RuntimeSettings


def candidate_day_service(db_path: Path) -> CandidateDayService:
    """Wire the planning port to SQLite and the configured holiday adapter."""
    return CandidateDayService(
        SQLiteCandidateDayUnitOfWorkFactory(db_path),
        PythonHolidaysProvider(),
    )


def planning_resource_unit_of_work_factory(
    db_path: Path,
    *,
    require_confirmed_coordinates: bool,
) -> SQLitePlanningResourceUnitOfWorkFactory:
    """Wire Planning commands to SQLite using resolved room policy."""
    return SQLitePlanningResourceUnitOfWorkFactory(
        db_path,
        require_confirmed_coordinates=require_confirmed_coordinates,
    )


def notification_service(
    db_path: Path,
    *,
    settings: RuntimeSettings | None = None,
    external_delivery_enabled: bool = True,
) -> NotificationService:
    """Compose notification policy with its SQLite and provider adapters."""
    return NotificationService(
        external_delivery_enabled=external_delivery_enabled,
        delivery_gateway=NotificationDeliveryGateway(settings),
        delivery_unit_of_work_factory=SQLiteNotificationDeliveryUnitOfWorkFactory(db_path),
        notification_unit_of_work_factory=SQLiteNotificationUnitOfWorkFactory(db_path),
    )


def authentication_repository(db_path: Path) -> AuthenticationRepository:
    """Wire Identity account and session operations to the SQLite adapter."""
    return SQLiteAuthenticationRepository(db_path)


def operator_auth_service(db_path: Path) -> OperatorAuthService:
    """Wire operator authentication commands to the SQLite identity UoW."""
    return OperatorAuthService(SQLiteOperatorAuthUnitOfWorkFactory(db_path))


def local_auth_service(
    db_path: Path,
    *,
    session_ttl: timedelta,
    settings: RuntimeSettings | None,
) -> LocalAuthService:
    """Wire local Identity auth ports to SQLite and the instance key store."""
    return LocalAuthService(
        unit_of_work_factory=SQLiteLocalAuthUnitOfWorkFactory(db_path),
        key_provider=SQLiteLocalAuthenticationKey(
            db_path, settings=settings.local_auth if settings else None
        ),
        session_ttl=session_ttl,
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


DEFAULT_MAP_PROVIDER_CONFIG = MapProviderConfig()


def venue_geocoder(config: MapProviderConfig) -> Geocoder:
    """Construct the configured geocoder adapter at the application root."""
    return NominatimGeocoder(config)


def exam_venue_service(
    db_path: Path = DEFAULT_DB_PATH,
    map_provider: MapProviderConfig = DEFAULT_MAP_PROVIDER_CONFIG,
    *,
    notification_service_factory: Callable[[Path], NotificationService] | None = None,
) -> ExamVenueService:
    """Wire Planning's venue ports to SQLite and the configured provider adapter."""
    notifications = (notification_service_factory or notification_service)(db_path)
    consequences = VenueConsequenceService(db_path, notification_service=notifications)
    return ExamVenueService(
        SQLiteExamVenueRepository(db_path, require_confirmed_coordinates=map_provider.active),
        geocoder=venue_geocoder(map_provider),
        follow_up=_VenueAuditFollowUp(consequences),
        impact_query=consequences,
        policy=ExamVenuePolicy(),
    )


def exam_venue_api(
    db_path: Path = DEFAULT_DB_PATH,
    map_provider: MapProviderConfig = DEFAULT_MAP_PROVIDER_CONFIG,
    *,
    notification_service_factory: Callable[[Path], NotificationService] | None = None,
) -> ExamVenueApi:
    """Wire the API consumer to Planning ports and database-scoped services."""
    notifications = (notification_service_factory or notification_service)(db_path)
    consequences = VenueConsequenceService(db_path, notification_service=notifications)
    service = ExamVenueService(
        SQLiteExamVenueRepository(db_path, require_confirmed_coordinates=map_provider.active),
        geocoder=venue_geocoder(map_provider),
        follow_up=_VenueAuditFollowUp(consequences),
        impact_query=consequences,
        policy=ExamVenuePolicy(),
    )
    return ExamVenueApi(service, map_provider, consequences)


class _VenueAuditFollowUp(VenueChangeFollowUp):
    """Execute the existing audit-driven follow-up as an explicit transition."""

    def __init__(self, consequences: VenueConsequenceService) -> None:
        self.consequences = consequences

    def process(self, change: VenueChange):
        return self.consequences.process_audit(change.audit_id)
