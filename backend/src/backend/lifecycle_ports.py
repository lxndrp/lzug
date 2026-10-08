"""Framework-free contracts for shared day- and round-lifecycle capabilities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class AssessmentLifecycleWork(Protocol):
    """Assessment-owned projections and commands inside a caller-owned UoW."""

    def day_completion(self, day_id: int) -> dict[str, Any]: ...

    def results_for_day_slots(
        self, day_id: int, slot_ids: Sequence[int]
    ) -> Sequence[dict[str, Any]]: ...

    def result_reopening_impacts(self, result_ids: set[int]) -> Sequence[dict[str, Any]]: ...

    def result_by_id(self, result_id: int) -> dict[str, Any] | None: ...

    def results_for_round(self, round_id: int) -> list[dict[str, Any]]: ...

    def result_for_round_candidate(self, candidate_id: int) -> dict[str, Any] | None: ...

    def open_result_correction(
        self,
        *,
        result_id: int,
        reopening_id: int,
        actor_member_id: int,
        reason: str,
        requested_at: str,
    ) -> dict[str, Any]: ...


class DayClosureKind(StrEnum):
    REGULAR = "regular"
    EXCEPTION = "exception"


@dataclass(frozen=True)
class ReopeningScopeItem:
    """One explicitly selected lifecycle correction scope."""

    kind: str
    entity_id: int

    def payload(self) -> dict[str, Any]:
        return {"kind": self.kind, "entity_id": self.entity_id}


@dataclass(frozen=True)
class DayCloseCommand:
    revision: int
    confirmed: bool
    closure_kind: DayClosureKind = DayClosureKind.REGULAR
    reason: str | None = None
    clarification_attempts: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "confirmed": self.confirmed,
            "closure_type": self.closure_kind.value,
            "reason": self.reason,
            "clarification_attempts": self.clarification_attempts,
        }


@dataclass(frozen=True)
class DayReopenCommand:
    revision: int
    occasion: str
    source: str
    reason: str
    scope: tuple[ReopeningScopeItem, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "occasion": self.occasion,
            "source": self.source,
            "reason": self.reason,
            "scope": [item.payload() for item in self.scope],
        }


@dataclass(frozen=True)
class RoundDecisionCommand:
    revision: int
    confirmed: bool
    reason: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "confirmed": self.confirmed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RoundReopenCommand:
    revision: int
    occasion: str
    source: str
    reason: str
    scope: tuple[ReopeningScopeItem, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "occasion": self.occasion,
            "source": self.source,
            "reason": self.reason,
            "scope": [item.payload() for item in self.scope],
        }


class AssessmentLifecycleWorkFactory(Protocol):
    """Persistence factory for a bound Assessment capability over an opaque UoW."""

    def __call__(self, transaction: object) -> AssessmentLifecycleWork: ...


@dataclass(frozen=True)
class PlanSlotLifecycleSnapshot:
    """Detached plan-slot values needed by cross-domain lifecycle rules."""

    id: int
    exam_day_id: int
    round_candidate_id: int
    starts_at: str
    ends_at: str
    execution_status: str
    status_reason: str | None
    actual_started_at: str | None
    actual_completed_at: str | None


@dataclass(frozen=True)
class PlanAssignmentLifecycleSnapshot:
    """Detached staffing values needed by day closure and reopening."""

    id: int
    exam_day_id: int
    committee_member_id: int
    assignment_role: str
    day_part: str
    fallback_status: str | None


@dataclass(frozen=True)
class PlanningCandidateLifecycleSnapshot:
    id: int
    first_name: str
    last_name: str
    ihk_exam_number: str


@dataclass(frozen=True)
class PlanningRoundLifecycleSnapshot:
    """Planning-owned round state required by lifecycle decisions."""

    id: int
    exam_half_year_id: int
    committee_id: int
    name: str
    status: str
    revision: int
    lifecycle_status: str
    legacy_status: str | None


@dataclass(frozen=True)
class DayClosureFacts:
    """Detached Planning, Identity, and Assessment inputs for a close decision."""

    committee_id: int
    slots: tuple[PlanSlotLifecycleSnapshot, ...]
    assignments: tuple[PlanAssignmentLifecycleSnapshot, ...]
    members: tuple[IdentityMemberLifecycleSnapshot, ...]
    assessment_completion: Mapping[str, Any]
    assessment_results: tuple[Mapping[str, Any], ...] = ()
    assessment_impacts: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class RoundLifecycleFacts:
    """Detached owner facts consumed while deciding a round close or reopen."""

    round: PlanningRoundLifecycleSnapshot
    day_ids: tuple[int, ...]
    candidates: tuple[Mapping[str, Any], ...]
    candidate_details: tuple[PlanningCandidateLifecycleSnapshot, ...]
    planning_context: Mapping[str, Any]
    slots: tuple[PlanSlotLifecycleSnapshot, ...]
    assignments: tuple[PlanAssignmentLifecycleSnapshot, ...]
    assessment_results: tuple[Mapping[str, Any], ...]
    committee: IdentityCommitteeLifecycleSnapshot
    members: tuple[IdentityMemberLifecycleSnapshot, ...]
    management_member_ids: frozenset[int]

    def round_lifecycle_snapshot(self, round_id: int):
        return self.round if round_id == self.round.id else None

    def round_committee_id(self, round_id: int):
        return self.round.committee_id if round_id == self.round.id else None

    def committee_members(self, committee_id: int):
        return self.members if committee_id == self.committee.id else ()

    def management_member_ids_for_committee(self, committee_id: int):
        return set(self.management_member_ids) if committee_id == self.committee.id else set()

    def results_for_round(self, round_id: int):
        return self.assessment_results if round_id == self.round.id else ()

    def result_for_round_candidate(self, candidate_id: int):
        return next(
            (
                item
                for item in self.assessment_results
                if item["round_candidate_id"] == candidate_id
            ),
            None,
        )

    def round_candidates(self, round_id: int) -> tuple[Mapping[str, Any], ...]:
        return self.candidates if round_id == self.round.id else ()

    def lifecycle_candidate_ids(self, round_id: int) -> set[int]:
        if round_id != self.round.id:
            return set()
        return {int(item["candidate_id"]) for item in self.candidates}

    def candidate_details_for(self, candidate_ids: Sequence[int]):
        requested = set(candidate_ids)
        return tuple(item for item in self.candidate_details if item.id in requested)

    def exam_day_slots(self, day_ids: Sequence[int]):
        requested = set(day_ids)
        return tuple(item for item in self.slots if item.exam_day_id in requested)

    def exam_day_slot_ids(self, day_ids: Sequence[int]):
        return tuple(item.id for item in self.exam_day_slots(day_ids))

    def exam_day_assignments(self, day_ids: Sequence[int]):
        requested = set(day_ids)
        return tuple(item for item in self.assignments if item.exam_day_id in requested)

    def lifecycle_context(
        self, round_id: int, half_year_id: int, candidate_ids: Sequence[int]
    ) -> Mapping[str, Any]:
        if round_id != self.round.id or half_year_id != self.round.exam_half_year_id:
            return {}
        context = self.planning_context
        requested = set(candidate_ids)
        return {
            **context,
            "candidate_assignment_history": tuple(
                item
                for item in context.get("candidate_assignment_history", ())
                if item["candidate_id"] in requested
            ),
        }

    def original_assignment_ended(self, round_candidate_id: int, round_id: int) -> bool:
        return any(
            item["round_candidate_id"] == round_candidate_id
            and item["exam_round_id"] == round_id
            and item["ended_at"] is not None
            for item in self.planning_context.get("candidate_assignment_history", ())
        )

    def effective_transfer_exists(
        self, source_half_year_id: int, target_round_id: int, candidate_id: int
    ) -> bool:
        return any(
            item["candidate_id"] == candidate_id
            and item["exam_round_id"] == target_round_id
            and item["ended_at"] is None
            for item in self.planning_context.get("candidate_assignment_history", ())
        )


class PlanningLifecycleWork(Protocol):
    """Planning-owned facts and commands participating in an outer UoW."""

    def round_lifecycle_snapshot(self, round_id: int) -> PlanningRoundLifecycleSnapshot | None: ...

    def advance_round_lifecycle(
        self,
        round_id: int,
        expected_revision: int,
        now: str,
        *,
        lifecycle_status: str | None = None,
    ) -> bool: ...

    def delete_empty_draft_round(self, round_id: int, expected_revision: int) -> bool: ...

    def round_candidates(self, round_id: int) -> Sequence[Mapping[str, Any]]: ...

    def candidate_details(
        self, candidate_ids: Sequence[int]
    ) -> Sequence[PlanningCandidateLifecycleSnapshot]: ...

    def round_candidate(self, round_id: int, candidate_id: int) -> Mapping[str, Any] | None: ...

    def candidate_assignment(
        self, round_candidate_id: int, round_id: int
    ) -> Mapping[str, Any] | None: ...

    def effective_transfer_exists(
        self, source_half_year_id: int, target_round_id: int, candidate_id: int
    ) -> bool: ...

    def update_candidate_terminal(
        self,
        round_id: int,
        round_candidate_id: int,
        values: Mapping[str, Any],
        *,
        ended_at: str | None,
        change_reason: str | None,
    ) -> bool: ...

    def original_assignment_ended(self, round_candidate_id: int, round_id: int) -> bool: ...

    def lifecycle_context(
        self, round_id: int, half_year_id: int, candidate_ids: Sequence[int]
    ) -> Mapping[str, Any]: ...

    def lifecycle_candidate_ids(self, round_id: int) -> set[int]: ...

    def mutation_target(
        self, resource: str, identifier: int | None, payload: Mapping[str, Any]
    ) -> tuple[int, int] | None: ...

    def dependency_counts(self, round_id: int) -> Mapping[str, int]: ...

    def exam_day_plan(
        self, day_id: int
    ) -> tuple[Sequence[PlanSlotLifecycleSnapshot], Sequence[PlanAssignmentLifecycleSnapshot]]: ...

    def exam_day_assignments(
        self, day_ids: Sequence[int]
    ) -> Sequence[PlanAssignmentLifecycleSnapshot]: ...

    def exam_day_slots(self, day_ids: Sequence[int]) -> Sequence[PlanSlotLifecycleSnapshot]: ...

    def exam_day_slot_ids(self, day_ids: Sequence[int]) -> Sequence[int]: ...

    def round_id_for_slot(self, slot_id: int) -> int | None: ...

    def cancel_exam_day_slots(self, day_ids: Sequence[int], now: str) -> None: ...

    def round_committee_id(self, round_id: int) -> int | None: ...


class PlanningLifecycleWorkFactory(Protocol):
    """Persistence factory for a bound Planning capability over an opaque UoW."""

    def __call__(self, transaction: object) -> PlanningLifecycleWork: ...


@dataclass(frozen=True)
class IdentityMemberLifecycleSnapshot:
    """Detached Identity data needed by lifecycle authorization and findings."""

    id: int
    committee_id: int
    person_id: int
    first_name: str
    last_name: str
    committee_role: str
    representing_side: str
    is_active: int


@dataclass(frozen=True)
class IdentityCommitteeLifecycleSnapshot:
    id: int
    name: str
    occupation: str
    ihk: str


class IdentityLifecycleWork(Protocol):
    """Identity-owned authorization and member projections within an outer UoW."""

    def committee_members(self, committee_id: int) -> Sequence[IdentityMemberLifecycleSnapshot]: ...

    def committee_members_by_ids(
        self, member_ids: Sequence[int]
    ) -> Sequence[IdentityMemberLifecycleSnapshot]: ...

    def committee(self, committee_id: int) -> IdentityCommitteeLifecycleSnapshot | None: ...

    def management_member_ids(self, committee_id: int) -> set[int]: ...


class IdentityLifecycleWorkFactory(Protocol):
    def __call__(self, transaction: object) -> IdentityLifecycleWork: ...


class CalendarLifecycleWork(Protocol):
    """Calendar-owned persisted projection operations in the caller's UoW."""

    def cancel_future_round_events(self, round_id: int, cutoff_date: str, now: str) -> set[int]: ...


class CalendarLifecycleWorkFactory(Protocol):
    def __call__(self, transaction: object) -> CalendarLifecycleWork: ...
