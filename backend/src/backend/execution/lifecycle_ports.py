"""Consumer-owned capabilities and rule inputs for Execution lifecycle services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from backend.identity.lifecycle_ports import (
    IdentityCommitteeLifecycleSnapshot,
    IdentityMemberLifecycleSnapshot,
)


class PlanSlotLifecycleSnapshot(Protocol):
    id: int
    exam_day_id: int
    round_candidate_id: int
    starts_at: str
    ends_at: str
    execution_status: str
    status_reason: str | None
    actual_started_at: str | None
    actual_completed_at: str | None


class PlanAssignmentLifecycleSnapshot(Protocol):
    id: int
    exam_day_id: int
    committee_member_id: int
    assignment_role: str
    day_part: str
    fallback_status: str | None


class PlanningCandidateLifecycleSnapshot(Protocol):
    id: int
    first_name: str
    last_name: str
    ihk_exam_number: str


class PlanningRoundLifecycleSnapshot(Protocol):
    id: int
    exam_half_year_id: int
    committee_id: int
    name: str
    status: str
    revision: int
    lifecycle_status: str
    legacy_status: str | None


class _PayloadCommand(Protocol):
    def payload(self) -> dict[str, Any]: ...


class DayCloseCommand(_PayloadCommand, Protocol): ...


class DayReopenCommand(_PayloadCommand, Protocol): ...


class RoundDecisionCommand(Protocol):
    revision: int
    confirmed: bool
    reason: str | None


class RoundReopenCommand(Protocol):
    revision: int
    occasion: str
    source: str
    reason: str
    scope: Sequence[Any]


class DayClosureFacts(Protocol):
    committee_id: int
    slots: Sequence[PlanSlotLifecycleSnapshot]
    assignments: Sequence[PlanAssignmentLifecycleSnapshot]
    members: Sequence[IdentityMemberLifecycleSnapshot]
    assessment_completion: Mapping[str, Any]
    management_member_ids: frozenset[int]
    assessment_results: Sequence[Mapping[str, Any]]
    assessment_impacts: Sequence[Mapping[str, Any]]


class RoundLifecycleFacts(Protocol):
    round: PlanningRoundLifecycleSnapshot
    day_ids: Sequence[int]
    candidates: Sequence[Mapping[str, Any]]
    candidate_details: Sequence[PlanningCandidateLifecycleSnapshot]
    planning_context: Mapping[str, Any]
    slots: Sequence[PlanSlotLifecycleSnapshot]
    assignments: Sequence[PlanAssignmentLifecycleSnapshot]
    assessment_results: Sequence[Mapping[str, Any]]
    committee: IdentityCommitteeLifecycleSnapshot
    members: Sequence[IdentityMemberLifecycleSnapshot]
    management_member_ids: frozenset[int]

    def round_lifecycle_snapshot(self, round_id: int) -> PlanningRoundLifecycleSnapshot | None: ...
    def round_committee_id(self, round_id: int) -> int | None: ...
    def committee_members(self, committee_id: int) -> Sequence[IdentityMemberLifecycleSnapshot]: ...
    def management_member_ids_for_committee(self, committee_id: int) -> set[int]: ...
    def results_for_round(self, round_id: int) -> Sequence[Mapping[str, Any]]: ...
    def result_for_round_candidate(self, candidate_id: int) -> Mapping[str, Any] | None: ...
    def round_candidates(self, round_id: int) -> Sequence[Mapping[str, Any]]: ...
    def lifecycle_candidate_ids(self, round_id: int) -> set[int]: ...
    def candidate_details_for(
        self, candidate_ids: Sequence[int]
    ) -> Sequence[PlanningCandidateLifecycleSnapshot]: ...
    def exam_day_slots(self, day_ids: Sequence[int]) -> Sequence[PlanSlotLifecycleSnapshot]: ...
    def exam_day_slot_ids(self, day_ids: Sequence[int]) -> Sequence[int]: ...
    def exam_day_assignments(
        self, day_ids: Sequence[int]
    ) -> Sequence[PlanAssignmentLifecycleSnapshot]: ...
    def lifecycle_context(
        self, round_id: int, half_year_id: int, candidate_ids: Sequence[int]
    ) -> Mapping[str, Any]: ...
    def original_assignment_ended(self, round_candidate_id: int, round_id: int) -> bool: ...
    def effective_transfer_exists(
        self, source_half_year_id: int, target_round_id: int, candidate_id: int
    ) -> bool: ...


class AssessmentLifecycleWork(Protocol):
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


class AssessmentLifecycleWorkFactory(Protocol):
    def __call__(self, transaction: object) -> AssessmentLifecycleWork: ...


class PlanningLifecycleWork(Protocol):
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
    def __call__(self, transaction: object) -> PlanningLifecycleWork: ...


class IdentityLifecycleWork(Protocol):
    def committee_members(self, committee_id: int) -> Sequence[IdentityMemberLifecycleSnapshot]: ...
    def committee_members_by_ids(
        self, member_ids: Sequence[int]
    ) -> Sequence[IdentityMemberLifecycleSnapshot]: ...
    def committee(self, committee_id: int) -> IdentityCommitteeLifecycleSnapshot | None: ...
    def management_member_ids(self, committee_id: int) -> set[int]: ...


class IdentityLifecycleWorkFactory(Protocol):
    def __call__(self, transaction: object) -> IdentityLifecycleWork: ...


class CalendarLifecycleWork(Protocol):
    def cancel_future_round_events(self, round_id: int, cutoff_date: str, now: str) -> set[int]: ...


class CalendarLifecycleWorkFactory(Protocol):
    def __call__(self, transaction: object) -> CalendarLifecycleWork: ...
