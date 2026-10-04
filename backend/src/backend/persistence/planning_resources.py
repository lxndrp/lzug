"""SQLite Unit of Work adapter for Planning master-data operations."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, NamedTuple, cast

from backend.persistence.candidate_days import SQLiteCandidateDayUnitOfWork
from backend.persistence.database import DEFAULT_DB_PATH, read_session_scope, session_scope
from backend.persistence.models import (
    CANDIDATE,
    CANDIDATE_COMMITTEE_ASSIGNMENT,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_HALF_YEAR,
    EXAM_ROOM,
    EXAM_ROUND,
    EXAM_VENUE,
    MEMBER_AVAILABILITY,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
    Resource,
)
from backend.persistence.resource_access import SQLiteResourceAccessQueryFactory
from backend.persistence.store import Store

if TYPE_CHECKING:
    from backend.planning.candidate_days import CandidateDayRecord
    from backend.planning.resources import (
        PlanningAvailabilityPropagationContext,
        PlanningAvailabilityPropagationFact,
        PlanningAvailabilityPropagationWrite,
        PlanningAvailabilityReferences,
        PlanningBlocker,
        PlanningCandidateAssignmentContext,
        PlanningCandidateAssignmentPlan,
        PlanningRecord,
        PlanningResourceUnitOfWork,
        PlanningRoundCreationContext,
        PlanningRoundCreationPlan,
        PlanningRoundSummary,
        PlanningSettingsReferences,
        PlanningSnapshot,
        PlanningValue,
    )


class _SQLitePlanningRecord(NamedTuple):
    values: Mapping[str, PlanningValue]

    def as_payload(self) -> dict[str, PlanningValue]:
        return dict(self.values)


class _SQLitePlanningSnapshot(NamedTuple):
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


class _SQLitePlanningRoundSummary(NamedTuple):
    round_id: int
    name: str
    status: str
    committee_id: int
    committee_name: str | None
    half_year: Mapping[str, object] | None
    candidate_count: int
    mep_count: int
    settings: PlanningRecord | None
    availability_counts: tuple[PlanningRecord, ...]

    def as_payload(self) -> dict[str, object]:
        return {
            "round": {
                "id": self.round_id,
                "name": self.name,
                "status": self.status,
                "committee_name": self.committee_name,
                "exam_half_year": dict(self.half_year) if self.half_year is not None else None,
            },
            "counts": {
                "candidates": self.candidate_count,
                "mep_count": self.mep_count,
                "required_exam_slots": self.candidate_count + self.mep_count,
            },
            "settings": self.settings.as_payload() if self.settings is not None else None,
            "availability": [row.as_payload() for row in self.availability_counts],
        }


class _SQLitePlanningBlocker(NamedTuple):
    date: str
    day_part: str
    person_id: int
    exam_half_year_id: int
    exam_round_id: int
    exam_day_status: str
    committee_name: str


def _record(values: Mapping[str, object]) -> PlanningRecord:
    """Detach a mapping from persistence and expose it as a read-only record."""
    typed_values = {key: cast("PlanningValue", value) for key, value in values.items()}
    return cast("PlanningRecord", _SQLitePlanningRecord(MappingProxyType(typed_values)))


class _SQLitePlanningRoomFacts(NamedTuple):
    room_active: bool
    venue_active: bool
    venue_scope: str
    venue_committee_id: int | None
    coordinate_status: str
    coordinates_required: bool


class _SQLitePlanningSettingsReferences(NamedTuple):
    round_committee_id: int | None
    updater_committee_id: int | None
    room: _SQLitePlanningRoomFacts | None


class _SQLitePlanningAvailabilityReferences(NamedTuple):
    round_committee_id: int | None
    member_committee_id: int | None
    member_active: bool
    day_round_id: int | None


class _SQLitePlanningAvailabilityPropagationFact(NamedTuple):
    member_id: int
    person_id: int
    committee_id: int
    day_id: int
    day_date: str
    round_id: int
    round_committee_id: int | None
    round_half_year_id: int | None
    existing_availability_id: int | None


class _SQLitePlanningAvailabilityPropagationContext(NamedTuple):
    source_member_id: int
    source_person_id: int
    source_date: str
    source_half_year_id: int
    candidates: tuple[PlanningAvailabilityPropagationFact, ...]


class _SQLitePlanningCandidateAssignmentContext(NamedTuple):
    candidate_exists: bool
    target_round_exists: bool
    active_round_id: int | None
    round_candidate_exists: bool
    exam_half_year_id: int | None
    active_assignment_id: int | None
    active_round_candidate_id: int | None
    target_round_candidate_id: int | None


class _SQLitePlanningRoundCreationContext(NamedTuple):
    exam_half_year_id: int | None
    half_year_exists: bool
    committee_exists: bool
    committee_active: bool
    committee_ready: bool
    creator_committee_id: int | None


class SQLitePlanningResourceUnitOfWorkFactory:
    """Open a consistent read snapshot or write-serialized Planning transaction."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        require_confirmed_coordinates: bool = False,
    ) -> None:
        self.db_path = db_path
        self.require_confirmed_coordinates = require_confirmed_coordinates

    def __call__(
        self, *, write: bool = False
    ) -> AbstractContextManager[PlanningResourceUnitOfWork]:
        return self._unit_of_work(write=write)

    @contextmanager
    def _unit_of_work(self, *, write: bool) -> Iterator[PlanningResourceUnitOfWork]:
        transaction = (
            session_scope(self.db_path, begin_immediate=True)
            if write
            else read_session_scope(self.db_path)
        )
        with transaction as session:
            yield SQLitePlanningResourceUnitOfWork(
                Store(session),
                require_confirmed_coordinates=self.require_confirmed_coordinates,
            )


class SQLitePlanningResourceUnitOfWork:
    """Perform use-case-sized Planning operations within one SQLite session."""

    def __init__(self, store: Store, *, require_confirmed_coordinates: bool = False) -> None:
        self._store = store
        self._require_confirmed_coordinates = require_confirmed_coordinates

    def authorization_queries(self) -> object:
        """Bind materialized access queries to the active planning transaction."""
        return SQLiteResourceAccessQueryFactory().for_transaction(self._store)

    @staticmethod
    def _visible_id_condition(resource: Resource, visible_ids: frozenset[int] | None):
        if visible_ids is None:
            return ()
        return (resource.model.id.in_(visible_ids),)

    def list_half_years(
        self, visible_ids: frozenset[int] | None = None
    ) -> tuple[PlanningRecord, ...]:
        return tuple(
            map(
                _record,
                self._store.where(
                    EXAM_HALF_YEAR, *self._visible_id_condition(EXAM_HALF_YEAR, visible_ids)
                ),
            )
        )

    def get_half_year(self, half_year_id: int) -> PlanningRecord | None:
        row = self._store.get(EXAM_HALF_YEAR, half_year_id)
        return _record(row) if row is not None else None

    def create_round(self, plan: PlanningRoundCreationPlan) -> PlanningRecord:
        normalized = dict(plan.values)
        if plan.create_half_year:
            if plan.season is None or plan.year is None:
                raise ValueError("Half-year creation plan is incomplete")
            half_year = self._store.create(
                EXAM_HALF_YEAR,
                {"season": plan.season, "year": plan.year, "status": "active"},
            )
            half_year_id = int(half_year["id"])
        elif plan.exam_half_year_id is not None:
            half_year_id = plan.exam_half_year_id
        else:
            raise ValueError("Round creation plan has no exam half-year")
        normalized["exam_half_year_id"] = half_year_id
        normalized["revision"] = 1
        normalized["lifecycle_status"] = "open"
        return _record(self._store.create(EXAM_ROUND, normalized))

    def prepare_round_creation(
        self, values: Mapping[str, PlanningValue]
    ) -> PlanningRoundCreationContext:
        explicit_half_year_id = values.get("exam_half_year_id")
        if explicit_half_year_id is not None:
            half_year_id = int(explicit_half_year_id)
            half_year = self._store.get(EXAM_HALF_YEAR, half_year_id)
        else:
            half_year = self._store.first(
                EXAM_HALF_YEAR, season=values["season"], year=values["year"]
            )
            half_year_id = int(half_year["id"]) if half_year is not None else None
        committee = self._store.get(COMMITTEE, values["committee_id"])
        creator = self._store.get(COMMITTEE_MEMBER, values["created_by_member_id"])
        return cast(
            "PlanningRoundCreationContext",
            _SQLitePlanningRoundCreationContext(
                exam_half_year_id=half_year_id,
                half_year_exists=half_year is not None,
                committee_exists=committee is not None,
                committee_active=bool(committee["is_active"]) if committee is not None else False,
                committee_ready=(
                    committee["bootstrap_state"] == "ready" if committee is not None else False
                ),
                creator_committee_id=(
                    int(creator["committee_id"]) if creator is not None else None
                ),
            ),
        )

    def list_rounds(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]:
        return tuple(
            map(
                _record,
                self._store.where(
                    EXAM_ROUND,
                    *self._visible_id_condition(EXAM_ROUND, visible_ids),
                    **dict(filters),
                ),
            )
        )

    def get_round(self, round_id: int) -> PlanningRecord | None:
        row = self._store.get(EXAM_ROUND, round_id)
        return _record(row) if row is not None else None

    def candidate_assignment_context(
        self, candidate_id: int, round_id: int
    ) -> PlanningCandidateAssignmentContext:
        candidate = self._store.get(CANDIDATE, candidate_id)
        exam_round = self._store.get(EXAM_ROUND, round_id)
        if candidate is None or exam_round is None:
            return cast(
                "PlanningCandidateAssignmentContext",
                _SQLitePlanningCandidateAssignmentContext(
                    candidate_exists=candidate is not None,
                    target_round_exists=exam_round is not None,
                    active_round_id=None,
                    round_candidate_exists=False,
                    exam_half_year_id=None,
                    active_assignment_id=None,
                    active_round_candidate_id=None,
                    target_round_candidate_id=None,
                ),
            )
        active = self._store.first(
            CANDIDATE_COMMITTEE_ASSIGNMENT,
            candidate_id=candidate_id,
            exam_half_year_id=exam_round["exam_half_year_id"],
            ended_at=None,
        )
        round_candidate = self._store.first(
            ROUND_CANDIDATE, candidate_id=candidate_id, exam_round_id=round_id
        )
        return cast(
            "PlanningCandidateAssignmentContext",
            _SQLitePlanningCandidateAssignmentContext(
                candidate_exists=True,
                target_round_exists=True,
                active_round_id=(int(active["exam_round_id"]) if active is not None else None),
                round_candidate_exists=round_candidate is not None,
                exam_half_year_id=int(exam_round["exam_half_year_id"]),
                active_assignment_id=int(active["id"]) if active is not None else None,
                active_round_candidate_id=(
                    int(active["round_candidate_id"]) if active is not None else None
                ),
                target_round_candidate_id=(
                    int(round_candidate["id"]) if round_candidate is not None else None
                ),
            ),
        )

    def delete_round(self, round_id: int) -> bool:
        return self._store.delete(EXAM_ROUND, round_id)

    def update_round(
        self, round_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        existing = self._store.get(EXAM_ROUND, round_id)
        if existing is None:
            return None
        changes = dict(values)
        row = self._store.update(EXAM_ROUND, round_id, changes)
        return _record(row or existing)

    def list_candidates(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]:
        return tuple(
            map(
                _record,
                self._store.where(
                    CANDIDATE,
                    *self._visible_id_condition(CANDIDATE, visible_ids),
                    **dict(filters),
                ),
            )
        )

    def get_candidate(self, candidate_id: int) -> PlanningRecord | None:
        row = self._store.get(CANDIDATE, candidate_id)
        return _record(row) if row is not None else None

    def create_candidate(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        return _record(self._store.create(CANDIDATE, dict(values)))

    def update_candidate(
        self, candidate_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        row = self._store.update(CANDIDATE, candidate_id, dict(values))
        return _record(row) if row is not None else None

    def delete_candidate(self, candidate_id: int) -> bool:
        self._store.delete_where(CANDIDATE_COMMITTEE_ASSIGNMENT, candidate_id=candidate_id)
        self._store.delete_where(ROUND_CANDIDATE, candidate_id=candidate_id)
        return self._store.delete(CANDIDATE, candidate_id)

    def list_candidate_assignments(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]:
        return tuple(
            map(
                _record,
                self._store.where(
                    CANDIDATE_COMMITTEE_ASSIGNMENT,
                    *self._visible_id_condition(CANDIDATE_COMMITTEE_ASSIGNMENT, visible_ids),
                    **dict(filters),
                ),
            )
        )

    def list_round_candidates(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]:
        return tuple(
            map(
                _record,
                self._store.where(
                    ROUND_CANDIDATE,
                    *self._visible_id_condition(ROUND_CANDIDATE, visible_ids),
                    **dict(filters),
                ),
            )
        )

    def delete_round_candidate(self, round_candidate_id: int) -> bool:
        return self._store.delete(ROUND_CANDIDATE, round_candidate_id)

    def assign_candidate_to_round(
        self,
        values: Mapping[str, PlanningValue],
        plan: PlanningCandidateAssignmentPlan,
    ) -> PlanningRecord:
        payload = dict(values)
        if plan.end_assignment_id is not None:
            ended_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
            self._store.update(
                CANDIDATE_COMMITTEE_ASSIGNMENT,
                plan.end_assignment_id,
                {"ended_at": ended_at, "change_reason": plan.change_reason},
            )
        if plan.deactivate_round_candidate_id is not None:
            self._store.update(
                ROUND_CANDIDATE,
                plan.deactivate_round_candidate_id,
                {"is_active": 0},
            )
        if plan.create_round_candidate:
            round_candidate = self._store.create(
                ROUND_CANDIDATE,
                {
                    "exam_round_id": plan.exam_round_id,
                    "candidate_id": plan.candidate_id,
                    "attempt_number": plan.attempt_number,
                    "requires_mep": plan.requires_mep,
                    "is_active": 1,
                },
            )
        else:
            assert plan.target_round_candidate_id is not None
            changed: dict[str, object] = {"is_active": 1}
            if plan.attempt_number is not None:
                changed["attempt_number"] = plan.attempt_number
            if plan.requires_mep is not None:
                changed["requires_mep"] = plan.requires_mep
            round_candidate = self._store.update(
                ROUND_CANDIDATE, plan.target_round_candidate_id, changed
            )
            if round_candidate is None:
                raise ValueError("Round candidate assignment not found")
        if plan.create_active_assignment:
            self._store.create(
                CANDIDATE_COMMITTEE_ASSIGNMENT,
                {
                    "candidate_id": plan.candidate_id,
                    "exam_half_year_id": plan.exam_half_year_id,
                    "exam_round_id": plan.exam_round_id,
                    "round_candidate_id": round_candidate["id"],
                },
            )
        row = self._store.first(
            ROUND_CANDIDATE,
            candidate_id=payload["candidate_id"],
            exam_round_id=payload["exam_round_id"],
        )
        if row is None:
            raise ValueError("Round candidate assignment could not be created")
        return _record(row)

    def list_settings(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]:
        return tuple(
            map(
                _record,
                self._store.where(
                    PLANNING_SETTINGS,
                    *self._visible_id_condition(PLANNING_SETTINGS, visible_ids),
                    **dict(filters),
                ),
            )
        )

    def get_settings(self, settings_id: int) -> PlanningRecord | None:
        row = self._store.get(PLANNING_SETTINGS, settings_id)
        return _record(row) if row is not None else None

    def settings_references(
        self, round_id: int, updater_member_id: int, room_id: int | None
    ) -> PlanningSettingsReferences:
        exam_round = self._store.get(EXAM_ROUND, round_id)
        updater = self._store.get(COMMITTEE_MEMBER, updater_member_id)
        room_facts = None
        if room_id is not None:
            room = self._store.get(EXAM_ROOM, room_id)
            venue = self._store.get(EXAM_VENUE, room["venue_id"]) if room is not None else None
            if room is not None and venue is not None:
                room_facts = _SQLitePlanningRoomFacts(
                    room_active=bool(room["is_active"]),
                    venue_active=bool(venue["is_active"]),
                    venue_scope=str(venue["scope"]),
                    venue_committee_id=(
                        int(venue["committee_id"])
                        if venue.get("committee_id") is not None
                        else None
                    ),
                    coordinate_status=str(venue["coordinate_status"]),
                    coordinates_required=self._require_confirmed_coordinates,
                )
        return cast(
            "PlanningSettingsReferences",
            _SQLitePlanningSettingsReferences(
                round_committee_id=(
                    int(exam_round["committee_id"]) if exam_round is not None else None
                ),
                updater_committee_id=(
                    int(updater["committee_id"]) if updater is not None else None
                ),
                room=room_facts,
            ),
        )

    def save_settings(self, values: Mapping[str, PlanningValue]) -> PlanningRecord:
        payload = dict(values)
        existing = self._store.first(PLANNING_SETTINGS, exam_round_id=payload["exam_round_id"])
        if existing is None:
            return _record(self._store.create(PLANNING_SETTINGS, payload))
        return _record(self._store.update(PLANNING_SETTINGS, existing["id"], payload) or existing)

    def update_settings(
        self, settings_id: int, values: Mapping[str, PlanningValue]
    ) -> PlanningRecord | None:
        existing = self._store.get(PLANNING_SETTINGS, settings_id)
        if existing is None:
            return None
        payload = dict(values)
        return _record(self._store.update(PLANNING_SETTINGS, settings_id, payload) or existing)

    def delete_settings(self, settings_id: int) -> bool:
        return self._store.delete(PLANNING_SETTINGS, settings_id)

    def list_availabilities(
        self,
        filters: Mapping[str, PlanningValue],
        visible_ids: frozenset[int] | None = None,
    ) -> tuple[PlanningRecord, ...]:
        return tuple(
            map(
                _record,
                self._store.where(
                    MEMBER_AVAILABILITY,
                    *self._visible_id_condition(MEMBER_AVAILABILITY, visible_ids),
                    **dict(filters),
                ),
            )
        )

    def get_availability(self, availability_id: int) -> PlanningRecord | None:
        row = self._store.get(MEMBER_AVAILABILITY, availability_id)
        return _record(row) if row is not None else None

    def availability_references(
        self, round_id: int, committee_member_id: int, candidate_exam_day_id: int
    ) -> PlanningAvailabilityReferences:
        exam_round = self._store.get(EXAM_ROUND, round_id)
        member = self._store.get(COMMITTEE_MEMBER, committee_member_id)
        day = self._store.get(CANDIDATE_EXAM_DAY, candidate_exam_day_id)
        return cast(
            "PlanningAvailabilityReferences",
            _SQLitePlanningAvailabilityReferences(
                round_committee_id=(
                    int(exam_round["committee_id"]) if exam_round is not None else None
                ),
                member_committee_id=(int(member["committee_id"]) if member is not None else None),
                member_active=bool(member["is_active"]) if member is not None else False,
                day_round_id=int(day["exam_round_id"]) if day is not None else None,
            ),
        )

    def availability_propagation_context(
        self, round_id: int, committee_member_id: int, candidate_exam_day_id: int
    ) -> PlanningAvailabilityPropagationContext:
        member = self._store.get(COMMITTEE_MEMBER, committee_member_id)
        day = self._store.get(CANDIDATE_EXAM_DAY, candidate_exam_day_id)
        source_round = self._store.get(EXAM_ROUND, round_id)
        if member is None or day is None or source_round is None:
            raise RuntimeError("Validated availability references changed inside the write UoW")

        members = self._store.where(COMMITTEE_MEMBER, person_id=member["person_id"])
        days = self._store.where(CANDIDATE_EXAM_DAY, date=day["date"])
        candidates: list[PlanningAvailabilityPropagationFact] = []
        for other_member in members:
            for other_day in days:
                other_round = self._store.get(EXAM_ROUND, other_day["exam_round_id"])
                existing = self._store.first(
                    MEMBER_AVAILABILITY,
                    exam_round_id=other_day["exam_round_id"],
                    committee_member_id=other_member["id"],
                    candidate_exam_day_id=other_day["id"],
                )
                candidates.append(
                    cast(
                        "PlanningAvailabilityPropagationFact",
                        _SQLitePlanningAvailabilityPropagationFact(
                            member_id=int(other_member["id"]),
                            person_id=int(other_member["person_id"]),
                            committee_id=int(other_member["committee_id"]),
                            day_id=int(other_day["id"]),
                            day_date=str(other_day["date"]),
                            round_id=int(other_day["exam_round_id"]),
                            round_committee_id=(
                                int(other_round["committee_id"])
                                if other_round is not None
                                else None
                            ),
                            round_half_year_id=(
                                int(other_round["exam_half_year_id"])
                                if other_round is not None
                                else None
                            ),
                            existing_availability_id=(
                                int(existing["id"]) if existing is not None else None
                            ),
                        ),
                    )
                )
        return cast(
            "PlanningAvailabilityPropagationContext",
            _SQLitePlanningAvailabilityPropagationContext(
                source_member_id=int(member["id"]),
                source_person_id=int(member["person_id"]),
                source_date=str(day["date"]),
                source_half_year_id=int(source_round["exam_half_year_id"]),
                candidates=tuple(candidates),
            ),
        )

    def save_availability(
        self,
        values: Mapping[str, PlanningValue],
        propagation: tuple[PlanningAvailabilityPropagationWrite, ...],
    ) -> PlanningRecord:
        payload = dict(values)
        existing = self._store.first(
            MEMBER_AVAILABILITY,
            exam_round_id=payload["exam_round_id"],
            committee_member_id=payload["committee_member_id"],
            candidate_exam_day_id=payload["candidate_exam_day_id"],
        )
        saved = (
            self._store.create(MEMBER_AVAILABILITY, payload)
            if existing is None
            else self._store.update(MEMBER_AVAILABILITY, existing["id"], payload) or existing
        )
        self._apply_availability_propagation(propagation)
        return _record(saved)

    def update_availability(
        self,
        availability_id: int,
        values: Mapping[str, PlanningValue],
        propagation: tuple[PlanningAvailabilityPropagationWrite, ...],
    ) -> PlanningRecord | None:
        existing = self._store.get(MEMBER_AVAILABILITY, availability_id)
        if existing is None:
            return None
        payload = dict(values)
        saved = self._store.update(MEMBER_AVAILABILITY, availability_id, payload) or existing
        self._apply_availability_propagation(propagation)
        return _record(saved)

    def delete_availability(self, availability_id: int) -> bool:
        return self._store.delete(MEMBER_AVAILABILITY, availability_id)

    def planning_snapshot(self, round_id: int) -> PlanningSnapshot | None:
        exam_round = self._store.get(EXAM_ROUND, round_id)
        if exam_round is None:
            return None
        half_year = self._store.get(EXAM_HALF_YEAR, exam_round["exam_half_year_id"])
        settings = self._store.first(PLANNING_SETTINGS, exam_round_id=round_id)
        candidates = self._store.all(CANDIDATE)
        candidate_day_port = SQLiteCandidateDayUnitOfWork(self._store)
        round_candidates = self._store.where(ROUND_CANDIDATE, exam_round_id=round_id)
        active_round_candidate_ids = {row["id"] for row in round_candidates if row["is_active"]}
        candidate_assignments = tuple(
            _record(row)
            for row in self._store.where(
                CANDIDATE_COMMITTEE_ASSIGNMENT, exam_round_id=round_id, ended_at=None
            )
            if row["round_candidate_id"] in active_round_candidate_ids
        )
        members = self._store.where(COMMITTEE_MEMBER, committee_id=exam_round["committee_id"])
        return cast(
            "PlanningSnapshot",
            _SQLitePlanningSnapshot(
                exam_round=_record(exam_round),
                half_year=_record(half_year or {}),
                settings=_record(settings) if settings is not None else None,
                candidates=tuple(map(_record, candidates)),
                members=tuple(map(_record, members)),
                round_candidates=tuple(map(_record, round_candidates)),
                candidate_assignments=candidate_assignments,
                candidate_days=candidate_day_port.candidate_days(round_id),
                availabilities=tuple(
                    map(_record, self._store.where(MEMBER_AVAILABILITY, exam_round_id=round_id))
                ),
                blocked_assignments=self._blocked_assignments(exam_round),
            ),
        )

    def round_summary(self, round_id: int) -> PlanningRoundSummary | None:
        exam_round = self._store.get(EXAM_ROUND, round_id)
        if exam_round is None:
            return None
        committee = self._store.get(COMMITTEE, exam_round["committee_id"])
        half_year = self._store.get(EXAM_HALF_YEAR, exam_round["exam_half_year_id"])
        candidate_count = self._store.count(ROUND_CANDIDATE, exam_round_id=round_id, is_active=1)
        mep_count = self._store.count(
            ROUND_CANDIDATE, exam_round_id=round_id, requires_mep=1, is_active=1
        )
        settings = self._store.first(PLANNING_SETTINGS, exam_round_id=round_id)
        availability_counts = self._store.grouped_counts(
            MEMBER_AVAILABILITY, "availability", exam_round_id=round_id
        )
        return cast(
            "PlanningRoundSummary",
            _SQLitePlanningRoundSummary(
                round_id=int(exam_round["id"]),
                name=str(exam_round["name"]),
                status=str(exam_round["status"]),
                committee_id=int(exam_round["committee_id"]),
                committee_name=str(committee["name"]) if committee is not None else None,
                half_year=MappingProxyType(dict(half_year)) if half_year is not None else None,
                candidate_count=candidate_count,
                mep_count=mep_count,
                settings=_record(settings) if settings is not None else None,
                availability_counts=tuple(map(_record, availability_counts)),
            ),
        )

    def _blocked_assignments(self, exam_round: Mapping[str, object]) -> tuple[PlanningBlocker, ...]:
        blockers: list[PlanningBlocker] = []
        for assignment in self._store.all(EXAM_DAY_ASSIGNMENT):
            day = self._store.get(EXAM_DAY, assignment["exam_day_id"])
            if day is None or day["status"] in {"cancelled", "completed"}:
                continue
            other_round = self._store.get(EXAM_ROUND, day["exam_round_id"])
            if (
                other_round is None
                or other_round["id"] == exam_round["id"]
                or other_round["exam_half_year_id"] != exam_round["exam_half_year_id"]
            ):
                continue
            member = self._store.get(COMMITTEE_MEMBER, assignment["committee_member_id"])
            committee = self._store.get(COMMITTEE, other_round["committee_id"])
            if member is None or committee is None:
                continue
            blockers.append(
                _SQLitePlanningBlocker(
                    date=str(day["date"]),
                    day_part=str(assignment["day_part"]),
                    person_id=int(member["person_id"]),
                    exam_half_year_id=int(other_round["exam_half_year_id"]),
                    exam_round_id=int(other_round["id"]),
                    exam_day_status=str(day["status"]),
                    committee_name=str(committee["name"]),
                )
            )
        return tuple(blockers)

    def _apply_availability_propagation(
        self, propagation: tuple[PlanningAvailabilityPropagationWrite, ...]
    ) -> None:
        for command in propagation:
            values: dict[str, object] = {
                "exam_round_id": command.exam_round_id,
                "committee_member_id": command.committee_member_id,
                "candidate_exam_day_id": command.candidate_exam_day_id,
                "availability": command.availability,
                "responded_at": command.responded_at,
            }
            if command.existing_availability_id is None:
                self._store.create(MEMBER_AVAILABILITY, values)
            else:
                self._store.update(MEMBER_AVAILABILITY, command.existing_availability_id, values)
