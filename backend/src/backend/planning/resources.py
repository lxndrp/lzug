"""Planning-owned ports and immutable snapshots for planning master data."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
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


class PlanningResourceUnitOfWork(Protocol):
    """Planning-owned operations on half-years, candidates, rounds and feedback.

    Implementations keep each command atomic and return values detached from
    the persistence technology. The boundary deliberately has no table or
    ORM model parameter.
    """

    def authorization_queries(self) -> object:
        """Return materialized authorization queries bound to this UoW."""

    def list_half_years(self) -> tuple[PlanningRecord, ...]: ...

    def get_half_year(self, half_year_id: int) -> PlanningRecord | None: ...

    def create_round(self, values: Mapping[str, PlanningValue]) -> PlanningRecord: ...

    def list_rounds(self, filters: Mapping[str, PlanningValue]) -> tuple[PlanningRecord, ...]: ...

    def get_round(self, round_id: int) -> PlanningRecord | None: ...

    def delete_round(self, round_id: int) -> bool: ...

    def update_round(
        self, round_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None: ...

    def list_candidates(
        self, filters: Mapping[str, PlanningValue]
    ) -> tuple[PlanningRecord, ...]: ...

    def get_candidate(self, candidate_id: int) -> PlanningRecord | None: ...

    def create_candidate(self, values: Mapping[str, PlanningValue]) -> PlanningRecord: ...

    def update_candidate(
        self, candidate_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None: ...

    def delete_candidate(self, candidate_id: int) -> bool: ...

    def list_candidate_assignments(
        self, filters: Mapping[str, PlanningValue]
    ) -> tuple[PlanningRecord, ...]: ...

    def list_round_candidates(
        self, filters: Mapping[str, PlanningValue]
    ) -> tuple[PlanningRecord, ...]: ...

    def assign_candidate_to_round(self, values: Mapping[str, PlanningValue]) -> PlanningRecord: ...

    def list_settings(self, filters: Mapping[str, PlanningValue]) -> tuple[PlanningRecord, ...]: ...

    def get_settings(self, settings_id: int) -> PlanningRecord | None: ...

    def save_settings(self, values: Mapping[str, PlanningValue]) -> PlanningRecord: ...

    def update_settings(
        self, settings_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None: ...

    def delete_settings(self, settings_id: int) -> bool: ...

    def list_availabilities(
        self, filters: Mapping[str, PlanningValue]
    ) -> tuple[PlanningRecord, ...]: ...

    def get_availability(self, availability_id: int) -> PlanningRecord | None: ...

    def save_availability(self, values: Mapping[str, PlanningValue]) -> PlanningRecord: ...

    def update_availability(
        self, availability_id: int, values: Mapping[str, PlanningValue]
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

    def list_half_years(self) -> tuple[PlanningRecord, ...]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.list_half_years()

    def get_half_year(self, half_year_id: int) -> PlanningRecord | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.get_half_year(half_year_id)

    def create_round(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "exam_round", None, values)
            return unit_of_work.create_round(payload)

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
            return unit_of_work.create_candidate(payload)

    def get_candidate(self, candidate_id: int) -> PlanningRecord | None:
        with self._unit_of_work_factory() as unit_of_work:
            record = unit_of_work.get_candidate(candidate_id)
            return self.present_candidates((record,))[0] if record is not None else None

    def update_candidate(
        self, candidate_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "candidate", candidate_id, values)
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
            return unit_of_work.assign_candidate_to_round(payload)

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
            return unit_of_work.save_settings(payload)

    def update_settings(
        self, settings_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "planning_settings", settings_id, values)
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
            return unit_of_work.save_availability(payload)

    def update_availability(
        self, availability_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        with self._write_unit_of_work() as unit_of_work:
            payload = self._authorized(unit_of_work, "member_availability", availability_id, values)
            return unit_of_work.update_availability(availability_id, payload)

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
            if resource == "exam_half_year":
                records = unit_of_work.list_half_years()
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
                records = list_method(normalized_filters)
            if resource == "candidate":
                records = self.present_candidates(records)
            if self._visible is None:
                return records
            visible_ids = self._visible(
                unit_of_work.authorization_queries(), resource, None, normalized_filters
            )
            if isinstance(visible_ids, bool):
                raise TypeError("Planning collection visibility must return record identifiers")
            return tuple(record for record in records if record.values.get("id") in visible_ids)

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
