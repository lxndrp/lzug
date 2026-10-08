"""Concrete application wiring for the canonical backend runtime."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from backend.application.exam_venue_api import ExamVenueApi
from backend.assessment.service import ExamResultService
from backend.execution.exam_day_closures import (
    complete_day_mutation,
    guard_day_mutation,
)
from backend.execution.exam_protocols import ExamProtocolService
from backend.execution.slot_service import ExecutionService
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
from backend.persistence.assessment import SQLiteAssessmentUnitOfWorkFactory
from backend.persistence.auth import (
    SQLiteAuthenticationRepository,
    SQLiteOperatorAuthUnitOfWorkFactory,
)
from backend.persistence.candidate_days import SQLiteCandidateDayUnitOfWorkFactory
from backend.persistence.committee_admin import SQLiteCommitteeAdminUnitOfWorkFactory
from backend.persistence.database import DEFAULT_DB_PATH
from backend.persistence.exam_lifecycle import SQLiteExamLifecycleUnitOfWorkFactory
from backend.persistence.execution import SQLiteExecutionUnitOfWorkFactory
from backend.persistence.identity import (
    SQLiteIdentityExecutionSnapshotFactory,
    SQLiteIdentityPlanningSnapshotFactory,
    SQLiteIdentityQueryFactory,
    SQLiteIdentityUnitOfWorkFactory,
)
from backend.persistence.local_auth import (
    SQLiteLocalAuthenticationKey,
    SQLiteLocalAuthUnitOfWorkFactory,
)
from backend.persistence.models import ExamDay
from backend.persistence.notifications import (
    SQLiteNotificationDeliveryUnitOfWorkFactory,
    SQLiteNotificationUnitOfWorkFactory,
)
from backend.persistence.planning import SQLitePlanningUnitOfWorkFactory
from backend.persistence.planning_resources import SQLitePlanningResourceUnitOfWorkFactory
from backend.persistence.sqlite_exam_venues import SQLiteExamVenueRepository
from backend.planning import PlanningService
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


def planning_service(
    db_path: Path,
    *,
    require_confirmed_coordinates: bool = False,
) -> PlanningService:
    """Wire Planning's proposal use cases to the SQLite Unit of Work."""
    return PlanningService(
        SQLitePlanningUnitOfWorkFactory(
            db_path,
            identity_snapshot_factory=SQLiteIdentityPlanningSnapshotFactory(),
            require_confirmed_coordinates=require_confirmed_coordinates,
        )
    )


def execution_service(db_path: Path) -> ExecutionService:
    """Wire Execution commands to a shared SQLite UoW and Identity projection."""
    return ExecutionService(
        SQLiteExecutionUnitOfWorkFactory(
            db_path,
            identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
        )
    )


def assessment_unit_of_work_factory(db_path: Path) -> SQLiteAssessmentUnitOfWorkFactory:
    """Create Assessment persistence bound to the request-selected database."""
    return SQLiteAssessmentUnitOfWorkFactory(
        db_path, day_mutation_handler=_complete_assessment_day_mutation
    )


def exam_lifecycle_unit_of_work_factory(db_path: Path) -> SQLiteExamLifecycleUnitOfWorkFactory:
    """Compose Execution and Assessment ports over one application transaction."""
    assessment_factory = assessment_unit_of_work_factory(db_path)
    return SQLiteExamLifecycleUnitOfWorkFactory(
        SQLiteExecutionUnitOfWorkFactory(
            db_path,
            identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
        ),
        assessment_factory,
        db_path,
        SQLiteAssessmentLifecycleAdapter(assessment_factory).bind,
    )


def exam_protocol_service(db_path: Path) -> ExamProtocolService:
    """Wire Execution protocol commands to the transaction-bound SQLite adapter."""
    return ExamProtocolService(
        SQLiteExecutionUnitOfWorkFactory(
            db_path,
            identity_snapshot_factory=SQLiteIdentityExecutionSnapshotFactory(),
        )
    )


def exam_result_service(db_path: Path) -> ExamResultService:
    """Wire Assessment commands and queries to the SQLite unit of work."""
    return ExamResultService(
        unit_of_work_factory=SQLiteAssessmentUnitOfWorkFactory(
            db_path, day_mutation_handler=_complete_assessment_day_mutation
        )
    )


class SQLiteAssessmentLifecycleAdapter:
    """Expose Assessment-owned lifecycle operations over an outer SQLAlchemy session."""

    def __init__(self, unit_of_work_factory=None) -> None:
        self._unit_of_work_factory = unit_of_work_factory or assessment_unit_of_work_factory(
            DEFAULT_DB_PATH
        )

    def bind(self, session):
        work = self._unit_of_work_factory.in_session(session)
        return _SQLiteAssessmentLifecycleWork(self, work)

    def day_completion(self, work, day_id: int) -> dict:
        snapshot = work.queries.day_completion(day_id)
        if snapshot is None:
            raise ValueError("Assessment day completion snapshot not found")
        return ExamResultService().completion_from_snapshot(snapshot)

    def results_for_day_slots(self, work, day_id: int, slot_ids) -> list[dict]:
        queries = work.queries
        results = []
        for slot_id in slot_ids:
            result = queries.result_by_slot(slot_id, day_id)
            if result is not None:
                results.append(
                    {"id": result["id"], "round_candidate_id": result["round_candidate_id"]}
                )
        return results

    def result_by_id(self, work, result_id: int) -> dict | None:
        return work.queries.result_by_id(result_id)

    def results_for_round(self, work, round_id: int) -> list[dict]:
        return list(work.queries.results_for_round(round_id))

    def result_for_round_candidate(self, work, candidate_id: int) -> dict | None:
        return work.queries.result_for_round_candidate(candidate_id)

    def result_reopening_impacts(self, work, result_ids: set[int]) -> list[dict]:
        impacts = []
        for result_id in sorted(result_ids):
            result = work.queries.result_by_id(result_id)
            if result is None:
                continue
            determination = next(
                (item for item in result["determinations"] if item["status"] == "current"),
                None,
            )
            impacts.append(
                {
                    "id": result_id,
                    "current_determination": determination,
                    "communications": [
                        item for item in result["communications"] if item["status"] == "current"
                    ],
                }
            )
        return impacts

    def open_result_correction(
        self,
        work,
        *,
        result_id: int,
        reopening_id: int,
        actor_member_id: int,
        reason: str,
        requested_at: str,
    ) -> dict:
        result = work.queries.result_by_id(result_id)
        if result is None:
            raise ValueError("Assessment result not found")
        return ExamResultService().reopen_result_for_day(
            work,
            result_id=result_id,
            expected_result_version=result["version"],
            reopening_reference=f"exam-day-reopening:{reopening_id}",
            actor_member_id=actor_member_id,
            reason=reason,
            requested_at=requested_at,
        )


class _SQLiteAssessmentLifecycleWork:
    """Expose Execution's consumer-owned port over a session-bound Assessment UoW."""

    def __init__(self, adapter: SQLiteAssessmentLifecycleAdapter, work) -> None:
        self._adapter = adapter
        self._work = work

    def day_completion(self, day_id: int) -> dict:
        return self._adapter.day_completion(self._work, day_id)

    def results_for_day_slots(self, day_id: int, slot_ids) -> list[dict]:
        return self._adapter.results_for_day_slots(self._work, day_id, slot_ids)

    def result_reopening_impacts(self, result_ids: set[int]) -> list[dict]:
        return self._adapter.result_reopening_impacts(self._work, result_ids)

    def result_by_id(self, result_id: int) -> dict | None:
        return self._adapter.result_by_id(self._work, result_id)

    def results_for_round(self, round_id: int) -> list[dict]:
        return self._adapter.results_for_round(self._work, round_id)

    def result_for_round_candidate(self, candidate_id: int) -> dict | None:
        return self._adapter.result_for_round_candidate(self._work, candidate_id)

    def open_result_correction(self, **command) -> dict:
        return self._adapter.open_result_correction(self._work, **command)


def _complete_assessment_day_mutation(
    session, result_id: int, kind: str, payload: dict, actor_member_id: int, reason: str | None
) -> None:
    days = (
        SQLiteAssessmentUnitOfWorkFactory().in_session(session).queries.days_for_result(result_id)
    )
    guards = []
    for snapshot in days:
        day = session.get(ExamDay, snapshot["day_id"])
        if day is None:
            continue
        guards.append(
            guard_day_mutation(
                session,
                day=day,
                kind=kind,
                entity_id=result_id,
                payload=payload,
                actor_member_id=actor_member_id,
            )
        )
    for guard in guards:
        complete_day_mutation(session, guard, actor_member_id=actor_member_id, reason=reason)


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
