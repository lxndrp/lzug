"""Planning-owned ports and immutable snapshots for planning master data."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol

from backend.planning.candidate_days import CandidateDayRecord

PlanningValue = str | int | bool | None
PlanningVisibility = Callable[
    [object, str, int | None, Mapping[str, PlanningValue]], bool | frozenset[int]
]

SPECIALIZATION_LABELS = {
    "application_development": "Anwendungsentwicklung",
    "system_integration": "Systemintegration",
    "data_and_process_analysis": "Daten- und Prozessanalyse",
    "digital_networking": "Digitale Vernetzung",
}

_AVAILABILITY_VALUES = frozenset({"full_day", "morning", "afternoon", "unavailable", "pending"})
_GERMAN_SUBDIVISION_CODES = frozenset(
    {
        "DE-BB",
        "DE-BE",
        "DE-BW",
        "DE-BY",
        "DE-HB",
        "DE-HE",
        "DE-HH",
        "DE-MV",
        "DE-NI",
        "DE-NW",
        "DE-RP",
        "DE-SH",
        "DE-SL",
        "DE-SN",
        "DE-ST",
        "DE-TH",
    }
)


@dataclass(frozen=True)
class PlanningRecordValue:
    """Immutable application-owned record returned by Planning use cases."""

    values: Mapping[str, PlanningValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def as_payload(self) -> dict[str, PlanningValue]:
        """Copy the immutable record into a transport-compatible payload."""
        return dict(self.values)


class PlanningRecord(Protocol):
    """Materialized values for one planning-owned master-data record."""

    @property
    def values(self) -> Mapping[str, PlanningValue]: ...

    def as_payload(self) -> dict[str, PlanningValue]: ...


class PlanningBlocker(Protocol):
    """Persisted person reservation from another round in the same half-year."""

    @property
    def date(self) -> str: ...

    @property
    def day_part(self) -> str: ...

    @property
    def person_id(self) -> int: ...

    @property
    def exam_half_year_id(self) -> int: ...

    @property
    def exam_round_id(self) -> int: ...

    @property
    def exam_day_status(self) -> str: ...

    @property
    def committee_name(self) -> str: ...


class PlanningSnapshot(Protocol):
    """Typed source snapshot used by proposal and calendar calculations."""

    exam_round: PlanningRecord
    half_year: PlanningRecord
    settings: PlanningRecord | None
    candidates: tuple[PlanningRecord, ...]
    members: tuple[PlanningRecord, ...]
    round_candidates: tuple[PlanningRecord, ...]
    candidate_assignments: tuple[PlanningRecord, ...]
    candidate_days: tuple[CandidateDayRecord, ...]
    availabilities: tuple[PlanningRecord, ...]
    blocked_assignments: tuple[PlanningBlocker, ...]


class PlanningRoundSummary(Protocol):
    """Detached round read model for the existing round-summary endpoint."""

    round_id: int
    name: str
    status: str
    committee_id: int
    committee_name: str | None
    candidate_count: int
    mep_count: int

    def as_payload(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class PlanningRoomFacts:
    """Detached persisted facts Planning uses to decide room suitability."""

    room_active: bool
    venue_active: bool
    venue_scope: str
    venue_committee_id: int | None
    coordinate_status: str
    coordinates_required: bool


@dataclass(frozen=True)
class PlanningSettingsReferences:
    """Persisted references needed to validate a settings command."""

    round_committee_id: int | None
    updater_committee_id: int | None
    room: PlanningRoomFacts | None


@dataclass(frozen=True)
class PlanningAvailabilityReferences:
    """Persisted references needed to validate an availability command."""

    round_committee_id: int | None
    member_committee_id: int | None
    member_active: bool
    day_round_id: int | None


@dataclass(frozen=True)
class PlanningAvailabilityPropagationFact:
    """Detached candidate target fact for availability propagation."""

    member_id: int
    person_id: int
    committee_id: int
    day_id: int
    day_date: str
    round_id: int
    round_committee_id: int | None
    round_half_year_id: int | None
    existing_availability_id: int | None


@dataclass(frozen=True)
class PlanningAvailabilityPropagationContext:
    """Facts Planning uses to select availability propagation targets."""

    source_member_id: int
    source_person_id: int
    source_date: str
    source_half_year_id: int
    candidates: tuple[PlanningAvailabilityPropagationFact, ...]


@dataclass(frozen=True)
class PlanningAvailabilityPropagationWrite:
    """One persistence operation selected by Planning's propagation policy."""

    existing_availability_id: int | None
    exam_round_id: int
    committee_member_id: int
    candidate_exam_day_id: int
    availability: str
    responded_at: str | None


@dataclass(frozen=True)
class PlanningRoundCreationContext:
    """Detached references Planning validates before a round is created."""

    exam_half_year_id: int | None
    half_year_exists: bool
    committee_exists: bool
    committee_active: bool
    committee_ready: bool
    creator_committee_id: int | None


@dataclass(frozen=True)
class PlanningRoundCreationPlan:
    """Planning's decision to reuse or create the round's half-year."""

    values: Mapping[str, PlanningValue]
    exam_half_year_id: int | None
    create_half_year: bool
    season: str | None
    year: int | None


@dataclass(frozen=True)
class PlanningCandidateAssignmentContext:
    """Persisted assignment facts for a Planning reassignment decision."""

    candidate_exists: bool
    target_round_exists: bool
    active_round_id: int | None
    round_candidate_exists: bool
    exam_half_year_id: int | None = None
    active_assignment_id: int | None = None
    active_round_candidate_id: int | None = None
    target_round_candidate_id: int | None = None


@dataclass(frozen=True)
class PlanningCandidateAssignmentPlan:
    """Policy decision for one atomic candidate-to-round assignment command."""

    candidate_id: int
    exam_round_id: int
    exam_half_year_id: int
    end_assignment_id: int | None
    deactivate_round_candidate_id: int | None
    target_round_candidate_id: int | None
    create_round_candidate: bool
    create_active_assignment: bool
    attempt_number: PlanningValue
    requires_mep: PlanningValue
    change_reason: str | None


class PlanningResourceUnitOfWork(Protocol):
    """Planning-owned operations on half-years, candidates, rounds and feedback.

    Implementations keep each command atomic and return values detached from
    the persistence technology. The boundary deliberately has no table or
    ORM model parameter.
    """

    def authorization_queries(self) -> object:
        """Return materialized authorization queries bound to this UoW."""

    def list_half_years(
        self, visible_ids: frozenset[int] | None = None
    ) -> tuple[PlanningRecord, ...]: ...

    def get_half_year(self, half_year_id: int) -> PlanningRecord | None: ...

    def create_round(self, plan: PlanningRoundCreationPlan) -> PlanningRecord: ...

    def prepare_round_creation(
        self, values: Mapping[str, PlanningValue]
    ) -> PlanningRoundCreationContext: ...

    def list_rounds(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]: ...

    def get_round(self, round_id: int) -> PlanningRecord | None: ...

    def candidate_assignment_context(
        self, candidate_id: int, round_id: int
    ) -> PlanningCandidateAssignmentContext: ...

    def delete_round(self, round_id: int) -> bool: ...

    def update_round(
        self, round_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None: ...

    def list_candidates(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]: ...

    def get_candidate(self, candidate_id: int) -> PlanningRecord | None: ...

    def create_candidate(self, values: Mapping[str, PlanningValue]) -> PlanningRecord: ...

    def update_candidate(
        self, candidate_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None: ...

    def delete_candidate(self, candidate_id: int) -> bool: ...

    def list_candidate_assignments(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]: ...

    def list_round_candidates(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]: ...

    def assign_candidate_to_round(
        self,
        values: Mapping[str, PlanningValue],
        plan: PlanningCandidateAssignmentPlan,
    ) -> PlanningRecord: ...

    def list_settings(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]: ...

    def get_settings(self, settings_id: int) -> PlanningRecord | None: ...

    def settings_references(
        self, round_id: int, updater_member_id: int, room_id: int | None
    ) -> PlanningSettingsReferences: ...

    def save_settings(self, values: Mapping[str, PlanningValue]) -> PlanningRecord: ...

    def update_settings(
        self, settings_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None: ...

    def delete_settings(self, settings_id: int) -> bool: ...

    def list_availabilities(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]: ...

    def get_availability(self, availability_id: int) -> PlanningRecord | None: ...

    def availability_references(
        self, round_id: int, committee_member_id: int, candidate_exam_day_id: int
    ) -> PlanningAvailabilityReferences: ...

    def availability_propagation_context(
        self, round_id: int, committee_member_id: int, candidate_exam_day_id: int
    ) -> PlanningAvailabilityPropagationContext: ...

    def save_availability(
        self,
        values: Mapping[str, PlanningValue],
        propagation: tuple[PlanningAvailabilityPropagationWrite, ...],
    ) -> PlanningRecord: ...

    def update_availability(
        self,
        availability_id: int,
        values: Mapping[str, PlanningValue],
        propagation: tuple[PlanningAvailabilityPropagationWrite, ...],
    ) -> PlanningRecord | None: ...

    def delete_availability(self, availability_id: int) -> bool: ...

    def planning_snapshot(self, round_id: int) -> PlanningSnapshot | None: ...

    def round_summary(self, round_id: int) -> PlanningRoundSummary | None: ...


class PlanningResourceUnitOfWorkFactory(Protocol):
    """Open a read snapshot or a write-serialized Planning transaction."""

    def __call__(
        self, *, write: bool = False
    ) -> AbstractContextManager[PlanningResourceUnitOfWork]: ...


class PlanningResourceService:
    """Expose planning master-data use cases through Planning-owned ports."""

    def __init__(
        self,
        unit_of_work_factory: PlanningResourceUnitOfWorkFactory,
        authorize: (
            Callable[[object, str, int | None, dict[str, PlanningValue]], dict[str, PlanningValue]]
            | None
        ) = None,
        visible: PlanningVisibility | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorize = authorize
        self._visible = visible

    def _write_unit_of_work(self) -> AbstractContextManager[PlanningResourceUnitOfWork]:
        return self._unit_of_work_factory(write=True)

    def _authorized(
        self,
        unit_of_work: PlanningResourceUnitOfWork,
        resource: str,
        entity_id: int | None,
        values: Mapping[str, PlanningValue],
    ) -> dict[str, PlanningValue]:
        payload = dict(values)
        if self._authorize is not None:
            return self._authorize(
                unit_of_work.authorization_queries(), resource, entity_id, payload
            )
        return payload

    @staticmethod
    def _normalize_round_create(values: Mapping[str, PlanningValue]) -> dict[str, PlanningValue]:
        payload = dict(values)
        for field in ("committee_id", "created_by_member_id"):
            if field not in payload:
                raise ValueError(f"Missing required field: {field}")
        if payload.get("exam_half_year_id") is not None:
            payload.pop("season", None)
            payload.pop("year", None)
        else:
            season = payload.get("season")
            if season not in {"summer", "winter"}:
                raise ValueError("Season must be summer or winter")
            try:
                year = int(payload.get("year"))  # type: ignore[arg-type]
            except (TypeError, ValueError) as error:
                raise ValueError("Year must be a four-digit number") from error
            if not 2000 <= year <= 2100:
                raise ValueError("Year must be between 2000 and 2100")
            payload["year"] = year
        PlanningResourceService._validate_round_fields(payload)
        return payload

    @staticmethod
    def _validate_round_fields(values: Mapping[str, PlanningValue]) -> None:
        if not str(values.get("name", "")).strip():
            raise ValueError("Exam round name is required")
        if values.get("status") in {"plan_proposed", "plan_confirmed"}:
            raise ValueError("Planning proposal statuses require the planning aggregate")

    @staticmethod
    def _validate_round_update(
        existing: Mapping[str, PlanningValue], changes: Mapping[str, PlanningValue]
    ) -> None:
        merged = {**existing, **changes}
        if any(
            merged[field] != existing[field]
            for field in ("exam_half_year_id", "committee_id")
            if field in changes
        ):
            raise ValueError("An exam round cannot be reassigned to another half-year or committee")
        if (
            "status" in changes
            and merged["status"] != existing["status"]
            and {merged["status"], existing["status"]}.intersection(
                {"plan_proposed", "plan_confirmed"}
            )
        ):
            raise ValueError("Planning proposal statuses require the planning aggregate")
        if not str(merged.get("name", "")).strip():
            raise ValueError("Exam round name is required")
        deadline = merged.get("availability_deadline")
        reminder = merged.get("availability_reminder_at")
        if deadline and reminder and reminder > deadline:
            raise ValueError("Availability reminder must be before the deadline")

    @staticmethod
    def _required_id(values: Mapping[str, PlanningValue], field: str) -> int:
        value = values.get(field)
        if value is None:
            raise ValueError(f"Missing required field: {field}")
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid identifier: {field}") from error

    @staticmethod
    def _validate_assignment(
        context: PlanningCandidateAssignmentContext,
        values: Mapping[str, PlanningValue],
        *,
        require_candidate: bool,
    ) -> dict[str, PlanningValue]:
        payload = dict(values)
        candidate_id = PlanningResourceService._required_id(payload, "candidate_id")
        round_id = PlanningResourceService._required_id(payload, "exam_round_id")
        if require_candidate and not context.candidate_exists:
            raise ValueError("Candidate not found")
        if not context.target_round_exists:
            raise ValueError("Exam round not found")
        if context.active_round_id is not None and context.active_round_id != round_id:
            if not str(payload.get("assignment_change_reason") or "").strip():
                raise ValueError("A reason is required for a committee change")
        if not context.round_candidate_exists:
            payload["attempt_number"] = payload.get("attempt_number") or 1
            payload["requires_mep"] = payload.get("requires_mep") or 0
        payload["candidate_id"] = candidate_id
        payload["exam_round_id"] = round_id
        return payload

    @staticmethod
    def _plan_round_creation(
        values: Mapping[str, PlanningValue], context: PlanningRoundCreationContext
    ) -> PlanningRoundCreationPlan:
        payload = dict(values)
        if not context.committee_exists:
            raise ValueError("Committee not found")
        if not context.committee_active or not context.committee_ready:
            raise ValueError("Committee is not ready for an exam round")
        committee_id = PlanningResourceService._required_id(payload, "committee_id")
        creator_id = PlanningResourceService._required_id(payload, "created_by_member_id")
        if context.creator_committee_id != committee_id:
            raise ValueError("Creating member does not belong to the exam round committee")
        payload["committee_id"] = committee_id
        payload["created_by_member_id"] = creator_id

        requested_half_year_id = payload.get("exam_half_year_id")
        if requested_half_year_id is not None:
            half_year_id = PlanningResourceService._required_id(payload, "exam_half_year_id")
            if not context.half_year_exists:
                raise ValueError("Exam half-year not found")
            payload.pop("season", None)
            payload.pop("year", None)
            return PlanningRoundCreationPlan(
                values=MappingProxyType(payload),
                exam_half_year_id=half_year_id,
                create_half_year=False,
                season=None,
                year=None,
            )

        if context.exam_half_year_id is not None:
            payload["exam_half_year_id"] = context.exam_half_year_id
            return PlanningRoundCreationPlan(
                values=MappingProxyType(payload),
                exam_half_year_id=context.exam_half_year_id,
                create_half_year=False,
                season=None,
                year=None,
            )

        season = payload.get("season")
        year = payload.get("year")
        if not isinstance(season, str) or not isinstance(year, int):
            raise ValueError("Season and year are required to create an exam half-year")
        return PlanningRoundCreationPlan(
            values=MappingProxyType(payload),
            exam_half_year_id=None,
            create_half_year=True,
            season=season,
            year=year,
        )

    @staticmethod
    def _plan_candidate_assignment(
        context: PlanningCandidateAssignmentContext,
        values: Mapping[str, PlanningValue],
    ) -> PlanningCandidateAssignmentPlan:
        payload = PlanningResourceService._validate_assignment(
            context, values, require_candidate=True
        )
        round_id = PlanningResourceService._required_id(payload, "exam_round_id")
        candidate_id = PlanningResourceService._required_id(payload, "candidate_id")
        half_year_id = context.exam_half_year_id
        if half_year_id is None:
            raise ValueError("Exam round not found")
        reassignment = context.active_round_id is not None and context.active_round_id != round_id
        return PlanningCandidateAssignmentPlan(
            candidate_id=candidate_id,
            exam_round_id=round_id,
            exam_half_year_id=half_year_id,
            end_assignment_id=context.active_assignment_id if reassignment else None,
            deactivate_round_candidate_id=(
                context.active_round_candidate_id if reassignment else None
            ),
            target_round_candidate_id=context.target_round_candidate_id,
            create_round_candidate=not context.round_candidate_exists,
            create_active_assignment=context.active_assignment_id is None or reassignment,
            attempt_number=(
                (payload.get("attempt_number") or 1)
                if not context.round_candidate_exists
                else payload.get("attempt_number")
            ),
            requires_mep=(
                (payload.get("requires_mep") or 0)
                if not context.round_candidate_exists
                else payload.get("requires_mep")
            ),
            change_reason=(
                str(payload["assignment_change_reason"])
                if payload.get("assignment_change_reason") is not None
                else None
            ),
        )

    @staticmethod
    def _normalize_settings(values: Mapping[str, PlanningValue]) -> dict[str, PlanningValue]:
        payload = dict(values)
        for field in ("exam_round_id", "updated_by_member_id"):
            if field not in payload:
                raise ValueError(f"Missing required field: {field}")
        subdivision = payload.get("holiday_subdivision_code")
        if subdivision is not None and subdivision not in _GERMAN_SUBDIVISION_CODES:
            raise ValueError("Unknown German federal state")
        if payload.get("exclude_public_holidays") and subdivision is None:
            raise ValueError("Federal state is required when public holidays are excluded")
        return payload

    @staticmethod
    def _validate_settings_references(
        values: Mapping[str, PlanningValue], references: PlanningSettingsReferences
    ) -> None:
        if references.round_committee_id is None:
            raise ValueError("Exam round not found")
        if references.updater_committee_id != references.round_committee_id:
            raise ValueError("Updating member does not belong to the exam round committee")
        room_id = values.get("default_room_id")
        room = references.room
        if room_id is not None and (
            room is None
            or not room.room_active
            or not room.venue_active
            or not (
                room.venue_scope == "global"
                or room.venue_committee_id == references.round_committee_id
            )
            or (room.coordinates_required and room.coordinate_status != "confirmed")
        ):
            raise ValueError("Default room is not active for the exam round committee")

    @staticmethod
    def _normalize_availability(
        values: Mapping[str, PlanningValue], *, now: datetime | None = None
    ) -> dict[str, PlanningValue]:
        payload = dict(values)
        for field in (
            "exam_round_id",
            "committee_member_id",
            "candidate_exam_day_id",
            "availability",
        ):
            if field not in payload:
                raise ValueError(f"Missing required field: {field}")
        if payload["availability"] not in _AVAILABILITY_VALUES:
            raise ValueError("Unknown availability value")
        if payload["availability"] == "pending":
            payload["responded_at"] = None
        else:
            payload["responded_at"] = (
                payload.get("responded_at")
                or (now or datetime.now(UTC).replace(microsecond=0)).isoformat()
            )
        return payload

    @staticmethod
    def _validate_availability_references(
        values: Mapping[str, PlanningValue], references: PlanningAvailabilityReferences
    ) -> None:
        if references.round_committee_id is None:
            raise ValueError("Exam round not found")
        if (
            references.member_committee_id is None
            or not references.member_active
            or references.member_committee_id != references.round_committee_id
        ):
            raise ValueError("Member does not belong to the exam round committee")
        round_id = PlanningResourceService._required_id(values, "exam_round_id")
        if references.day_round_id != round_id:
            raise ValueError("Candidate exam day does not belong to the exam round")

    @staticmethod
    def _plan_availability_propagation(
        values: Mapping[str, PlanningValue],
        context: PlanningAvailabilityPropagationContext,
    ) -> tuple[PlanningAvailabilityPropagationWrite, ...]:
        source_member_id = context.source_member_id
        source_date = context.source_date
        availability = str(values["availability"])
        responded_at_value = values.get("responded_at")
        responded_at = str(responded_at_value) if responded_at_value is not None else None
        writes: list[PlanningAvailabilityPropagationWrite] = []
        for fact in context.candidates:
            if (
                fact.member_id == source_member_id
                or fact.person_id != context.source_person_id
                or fact.day_date != source_date
                or fact.round_committee_id != fact.committee_id
                or fact.round_half_year_id != context.source_half_year_id
            ):
                continue
            writes.append(
                PlanningAvailabilityPropagationWrite(
                    existing_availability_id=fact.existing_availability_id,
                    exam_round_id=fact.round_id,
                    committee_member_id=fact.member_id,
                    candidate_exam_day_id=fact.day_id,
                    availability=availability,
                    responded_at=responded_at,
                )
            )
        return tuple(writes)

    def list_half_years(self) -> tuple[PlanningRecord, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.list_half_years()

    def get_half_year(self, half_year_id: int) -> PlanningRecord | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.get_half_year(half_year_id)

    def create_round(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "exam_round", None, values)
            payload = self._normalize_round_create(payload)
            context = unit_of_work.prepare_round_creation(payload)
            plan = self._plan_round_creation(payload, context)
            return unit_of_work.create_round(plan)

    def list_rounds(
        self, filters: Mapping[str, PlanningValue] | None = None
    ) -> tuple[PlanningRecord, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.list_rounds(filters or {})

    def get_round(self, round_id: int) -> PlanningRecord | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.get_round(round_id)

    def delete_round(self, round_id: int) -> bool:
        with self._write_unit_of_work() as unit_of_work:
            self._authorized(unit_of_work, "exam_round", round_id, {})
            return unit_of_work.delete_round(round_id)

    def update_round(
        self, round_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "exam_round", round_id, values)
            existing = unit_of_work.get_round(round_id)
            if existing is None:
                return None
            self._validate_round_update(existing.values, payload)
            return unit_of_work.update_round(round_id, payload)

    def list_candidates(
        self, filters: Mapping[str, PlanningValue] | None = None
    ) -> tuple[PlanningRecord, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            rows = unit_of_work.list_candidates(filters or {})
            return self.present_candidates(rows)

    @staticmethod
    def present_candidates(rows: tuple[PlanningRecord, ...]) -> tuple[PlanningRecord, ...]:
        """Add the stable display label to materialized candidate records."""
        return tuple(
            PlanningRecordValue(
                {
                    **row.values,
                    "specialization_label": SPECIALIZATION_LABELS.get(
                        str(row.values.get("specialization")),
                        row.values.get("specialization"),
                    ),
                }
            )
            for row in rows
        )

    def create_candidate(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "candidate", None, values)
            round_id = payload.pop("exam_round_id", None)
            attempt_number = payload.pop("attempt_number", None)
            requires_mep = payload.pop("requires_mep", None)
            if round_id is not None:
                assignment_values = {
                    "candidate_id": -1,
                    "exam_round_id": round_id,
                    "attempt_number": attempt_number,
                    "requires_mep": requires_mep,
                }
            else:
                assignment_values = None
            candidate = unit_of_work.create_candidate(payload)
            if assignment_values is not None:
                candidate_id = self._required_id(candidate.values, "id")
                assignment_values["candidate_id"] = candidate_id
                target_round_id = self._required_id(assignment_values, "exam_round_id")
                context = unit_of_work.candidate_assignment_context(candidate_id, target_round_id)
                plan = self._plan_candidate_assignment(context, assignment_values)
                unit_of_work.assign_candidate_to_round(assignment_values, plan)
            return candidate

    def get_candidate(self, candidate_id: int) -> PlanningRecord | None:
        with self._unit_of_work_factory() as unit_of_work:
            record = unit_of_work.get_candidate(candidate_id)
            return self.present_candidates((record,))[0] if record is not None else None

    def update_candidate(
        self, candidate_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "candidate", candidate_id, values)
            if ("attempt_number" in payload or "requires_mep" in payload) and payload.get(
                "exam_round_id"
            ) is None:
                raise ValueError("Missing required field: exam_round_id")
            if payload.get("exam_round_id") is None:
                payload.pop("assignment_change_reason", None)
            if payload.get("exam_round_id") is not None:
                candidate = unit_of_work.get_candidate(candidate_id)
                if candidate is None:
                    return None
                round_id = self._required_id(payload, "exam_round_id")
                context = unit_of_work.candidate_assignment_context(candidate_id, round_id)
                assignment_values = {**payload, "candidate_id": candidate_id}
                plan = self._plan_candidate_assignment(context, assignment_values)
                payload.pop("exam_round_id", None)
                payload.pop("attempt_number", None)
                payload.pop("requires_mep", None)
                payload.pop("assignment_change_reason", None)
                updated = unit_of_work.update_candidate(candidate_id, payload)
                if updated is not None:
                    unit_of_work.assign_candidate_to_round(assignment_values, plan)
                return updated
            return unit_of_work.update_candidate(candidate_id, payload)

    def delete_candidate(self, candidate_id: int) -> bool:
        with self._write_unit_of_work() as unit_of_work:
            self._authorized(unit_of_work, "candidate", candidate_id, {})
            return unit_of_work.delete_candidate(candidate_id)

    def list_candidate_assignments(
        self, filters: Mapping[str, PlanningValue] | None = None
    ) -> tuple[PlanningRecord, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.list_candidate_assignments(filters or {})

    def list_round_candidates(
        self, filters: Mapping[str, PlanningValue] | None = None
    ) -> tuple[PlanningRecord, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.list_round_candidates(filters or {})

    def assign_candidate_to_round(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "round_candidate", None, values)
            candidate_id = self._required_id(payload, "candidate_id")
            round_id = self._required_id(payload, "exam_round_id")
            context = unit_of_work.candidate_assignment_context(candidate_id, round_id)
            plan = self._plan_candidate_assignment(context, payload)
            return unit_of_work.assign_candidate_to_round(payload, plan)

    def list_settings(
        self, filters: Mapping[str, PlanningValue] | None = None
    ) -> tuple[PlanningRecord, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.list_settings(filters or {})

    def get_settings(self, settings_id: int) -> PlanningRecord | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.get_settings(settings_id)

    def save_settings(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "planning_settings", None, values)
            payload = self._normalize_settings(payload)
            references = unit_of_work.settings_references(
                self._required_id(payload, "exam_round_id"),
                self._required_id(payload, "updated_by_member_id"),
                (
                    self._required_id(payload, "default_room_id")
                    if payload.get("default_room_id") is not None
                    else None
                ),
            )
            self._validate_settings_references(payload, references)
            return unit_of_work.save_settings(payload)

    def update_settings(
        self, settings_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "planning_settings", settings_id, values)
            existing = unit_of_work.get_settings(settings_id)
            if existing is None:
                return None
            normalized = self._normalize_settings({**existing.values, **payload})
            references = unit_of_work.settings_references(
                self._required_id(normalized, "exam_round_id"),
                self._required_id(normalized, "updated_by_member_id"),
                (
                    self._required_id(normalized, "default_room_id")
                    if normalized.get("default_room_id") is not None
                    else None
                ),
            )
            self._validate_settings_references(normalized, references)
            return unit_of_work.update_settings(settings_id, payload)

    def delete_settings(self, settings_id: int) -> bool:
        with self._write_unit_of_work() as unit_of_work:
            self._authorized(unit_of_work, "planning_settings", settings_id, {})
            return unit_of_work.delete_settings(settings_id)

    def list_availabilities(
        self, filters: Mapping[str, PlanningValue] | None = None
    ) -> tuple[PlanningRecord, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.list_availabilities(filters or {})

    def get_availability(self, availability_id: int) -> PlanningRecord | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.get_availability(availability_id)

    def save_availability(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "member_availability", None, values)
            payload = self._normalize_availability(payload)
            references = unit_of_work.availability_references(
                self._required_id(payload, "exam_round_id"),
                self._required_id(payload, "committee_member_id"),
                self._required_id(payload, "candidate_exam_day_id"),
            )
            self._validate_availability_references(payload, references)
            propagation_context = unit_of_work.availability_propagation_context(
                self._required_id(payload, "exam_round_id"),
                self._required_id(payload, "committee_member_id"),
                self._required_id(payload, "candidate_exam_day_id"),
            )
            propagation = self._plan_availability_propagation(payload, propagation_context)
            return unit_of_work.save_availability(payload, propagation)

    def update_availability(
        self, availability_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "member_availability", availability_id, values)
            existing = unit_of_work.get_availability(availability_id)
            if existing is None:
                return None
            normalized = self._normalize_availability({**existing.values, **payload})
            references = unit_of_work.availability_references(
                self._required_id(normalized, "exam_round_id"),
                self._required_id(normalized, "committee_member_id"),
                self._required_id(normalized, "candidate_exam_day_id"),
            )
            self._validate_availability_references(normalized, references)
            propagation_context = unit_of_work.availability_propagation_context(
                self._required_id(normalized, "exam_round_id"),
                self._required_id(normalized, "committee_member_id"),
                self._required_id(normalized, "candidate_exam_day_id"),
            )
            propagation = self._plan_availability_propagation(normalized, propagation_context)
            return unit_of_work.update_availability(availability_id, normalized, propagation)

    def delete_availability(self, availability_id: int) -> bool:
        with self._write_unit_of_work() as unit_of_work:
            self._authorized(unit_of_work, "member_availability", availability_id, {})
            return unit_of_work.delete_availability(availability_id)

    def planning_snapshot(self, round_id: int) -> PlanningSnapshot | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.planning_snapshot(round_id)

    def round_summary(self, round_id: int) -> PlanningRoundSummary | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.round_summary(round_id)

    def list_visible_records(
        self, resource: str, filters: Mapping[str, PlanningValue] | None = None
    ) -> tuple[PlanningRecord, ...]:
        normalized_filters = filters or {}
        with self._unit_of_work_factory() as unit_of_work:
            visible_ids: frozenset[int] | None = None
            if self._visible is not None:
                collection_visibility = self._visible(
                    unit_of_work.authorization_queries(), resource, None, normalized_filters
                )
                if isinstance(collection_visibility, bool):
                    raise TypeError("Planning collection visibility must return record identifiers")
                visible_ids = collection_visibility
            if resource == "exam_half_year":
                records = unit_of_work.list_half_years(visible_ids)
            else:
                list_method_name = {
                    "exam_round": "list_rounds",
                    "round_candidate": "list_round_candidates",
                    "candidate": "list_candidates",
                    "candidate_committee_assignment": "list_candidate_assignments",
                    "planning_settings": "list_settings",
                    "member_availability": "list_availabilities",
                }.get(resource)
                if list_method_name is None:
                    raise ValueError(f"No Planning query for resource {resource}")
                list_method = getattr(unit_of_work, list_method_name)
                records = list_method(normalized_filters, visible_ids)
            if resource == "candidate":
                records = self.present_candidates(records)
            return records

    def get_visible_record(self, resource: str, resource_id: int) -> PlanningRecord | None:
        with self._unit_of_work_factory() as unit_of_work:
            get_method_name = {
                "exam_half_year": "get_half_year",
                "exam_round": "get_round",
                "candidate": "get_candidate",
                "planning_settings": "get_settings",
                "member_availability": "get_availability",
            }.get(resource)
            if get_method_name is not None:
                get_method = getattr(unit_of_work, get_method_name)
                record = get_method(resource_id)
            elif resource in {"round_candidate", "candidate_committee_assignment"}:
                list_method = (
                    unit_of_work.list_round_candidates
                    if resource == "round_candidate"
                    else unit_of_work.list_candidate_assignments
                )
                record = next(
                    (
                        row
                        for row in list_method({"id": resource_id})
                        if row.values.get("id") == resource_id
                    ),
                    None,
                )
            else:
                raise ValueError(f"No Planning query for resource {resource}")
            if record is None:
                return None
            if resource == "candidate":
                record = self.present_candidates((record,))[0]
            if self._visible is None:
                return record
            is_visible = self._visible(
                unit_of_work.authorization_queries(), resource, resource_id, {}
            )
            if not isinstance(is_visible, bool):
                raise TypeError("Planning item visibility must return a boolean")
            return record if is_visible else None
