"""Planning-owned snapshots and persistence contracts for plan use cases.

The types in this module describe the values a planning use case needs. They
contain no ORM objects, SQL expressions, or transport models; concrete storage
and transaction behavior belongs to a persistence adapter.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Protocol, TypedDict


class ExamRoundSnapshot(TypedDict):
    """Planning-owned round state needed by proposal use cases."""

    id: int
    committee_id: int
    exam_half_year_id: int
    status: str
    plan_revision: int
    availability_deadline: str | None


class PlanningSettingsSnapshot(TypedDict):
    """The settings consumed by proposal generation and validation."""

    default_room_id: int | None
    lunch_break_enabled: int
    exams_per_day: int
    max_exam_days_per_week: int


class RoundCandidateSnapshot(TypedDict):
    """A candidate currently assigned to the planning round."""

    id: int
    requires_mep: int


class CandidateSnapshot(TypedDict):
    """Candidate facts needed to validate a complete proposal."""

    id: int
    requires_mep: int


class CommitteeMemberSnapshot(TypedDict):
    """Identity facts needed for planning and assignment validation."""

    id: int
    person_id: int
    committee_id: int
    representing_side: str
    committee_role: str
    is_active: int


class PlanningIdentitySnapshots(Protocol):
    """Identity-owned membership snapshots consumed by Planning use cases."""

    def active_committee_members(
        self, committee_id: int
    ) -> Mapping[int, CommitteeMemberSnapshot]: ...

    def members_by_id(self, member_ids: Sequence[int]) -> Mapping[int, CommitteeMemberSnapshot]: ...


class CandidateDaySnapshot(TypedDict):
    """Planning-owned candidate day used as a proposal date."""

    id: int
    date: str
    is_active: int


class MemberAvailabilitySnapshot(TypedDict):
    """A member's availability for one candidate day."""

    committee_member_id: int
    candidate_exam_day_id: int
    availability: str


class PlanSlotSnapshot(Protocol):
    """Materialized slot values returned by a Planning persistence adapter."""

    round_candidate_id: int
    slot_type: str
    id: int | None
    sequence_number: int
    starts_at: str
    ends_at: str
    status: str


class PlanAssignmentSnapshot(Protocol):
    """Materialized assignment values returned by a Planning adapter."""

    committee_member_id: int
    assignment_role: str
    day_part: str
    id: int | None
    fallback_status: str | None


class PlanDaySnapshot(Protocol):
    """Materialized day and nested plan values returned by an adapter."""

    candidate_exam_day_id: int
    room_id: int
    slots: tuple[PlanSlotSnapshot, ...]
    assignments: tuple[PlanAssignmentSnapshot, ...]
    id: int | None
    date: str
    status: str


class PlanningProposalSnapshot(Protocol):
    """Persistence-neutral representation of a complete plan aggregate."""

    round_id: int
    revision: int
    days: tuple[PlanDaySnapshot, ...]


class PlanningContextSnapshot(Protocol):
    """Materialized inputs for proposal generation and validation."""

    exam_round: ExamRoundSnapshot | None
    settings: PlanningSettingsSnapshot | None
    round_candidates: tuple[RoundCandidateSnapshot, ...]
    candidates: Mapping[int, CandidateSnapshot]
    members: Mapping[int, CommitteeMemberSnapshot]
    candidate_days: Mapping[int, CandidateDaySnapshot]
    availability: tuple[MemberAvailabilitySnapshot, ...]
    blocked_person_ids: Mapping[tuple[str, str], Mapping[int, str]]
    active_candidate_assignments: Mapping[int, int]
    usable_room_ids: frozenset[int]
    protected_confirmed_day_ids: frozenset[int]
    exam_day_records: tuple[Mapping[str, object], ...]
    proposal: PlanningProposalSnapshot | None


class ConfirmedPlanRevisionSnapshot(Protocol):
    """Materialized immutable audit record for one confirmed-plan revision."""

    id: int
    exam_round_id: int
    previous_revision: int
    resulting_revision: int
    reason: str
    actor_member_id: int
    before_state_json: str
    after_state_json: str
    created_at: str


class PlanningUnitOfWork(Protocol):
    """Use-case persistence boundary; all methods share one transaction."""

    def planning_context(self, round_id: int) -> PlanningContextSnapshot: ...

    def mark_availabilities_requested(self, round_id: int) -> Mapping[str, object] | None: ...

    def replace_proposal(
        self,
        proposal: PlanningProposalSnapshot,
        *,
        expected_revision: int,
        allowed_statuses: frozenset[str],
        target_status: str,
    ) -> int | None: ...

    def confirm_proposal(self, round_id: int, *, expected_revision: int) -> int | None: ...

    def revise_confirmed_plan(
        self,
        proposal: PlanningProposalSnapshot,
        *,
        expected_revision: int,
        protected_day_ids: frozenset[int],
        actor_member_id: int,
        reason: str,
        before_state_json: str,
        after_state_json: str,
    ) -> ConfirmedPlanRevisionSnapshot | None: ...

    def confirmed_plan_revisions(
        self, round_id: int
    ) -> Sequence[ConfirmedPlanRevisionSnapshot]: ...

    def confirmed_plan_revision_ids_for_round(self, round_id: int) -> Sequence[int]: ...

    def confirmed_plan_revision(self, revision_id: int) -> ConfirmedPlanRevisionSnapshot | None: ...

    def all_confirmed_plan_revisions(self) -> Sequence[ConfirmedPlanRevisionSnapshot]: ...

    def confirmed_plan_revision_ids(self) -> Sequence[int]: ...


class PlanningUnitOfWorkFactory(Protocol):
    """Open one isolated transaction for a Planning command or query."""

    def __call__(self, *, write: bool = False) -> AbstractContextManager[PlanningUnitOfWork]: ...
