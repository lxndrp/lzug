"""Application-owned commands and detached cross-domain lifecycle facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backend.execution.lifecycle_ports import (
    PlanAssignmentLifecycleSnapshot,
    PlanningCandidateLifecycleSnapshot,
    PlanningRoundLifecycleSnapshot,
    PlanSlotLifecycleSnapshot,
)
from backend.identity.lifecycle_ports import (
    IdentityCommitteeLifecycleSnapshot,
    IdentityMemberLifecycleSnapshot,
)


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
        return {"revision": self.revision, "confirmed": self.confirmed, "reason": self.reason}


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


@dataclass(frozen=True)
class DayClosureFacts:
    """Detached Planning, Identity, and Assessment inputs for a close decision."""

    committee_id: int
    slots: tuple[PlanSlotLifecycleSnapshot, ...]
    assignments: tuple[PlanAssignmentLifecycleSnapshot, ...]
    members: tuple[IdentityMemberLifecycleSnapshot, ...]
    assessment_completion: Mapping[str, Any]
    management_member_ids: frozenset[int] = frozenset()
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
        return (
            {int(item["candidate_id"]) for item in self.candidates}
            if round_id == self.round.id
            else set()
        )

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

    def lifecycle_context(self, round_id: int, half_year_id: int, candidate_ids: Sequence[int]):
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
