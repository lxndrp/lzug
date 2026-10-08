"""Persistence-neutral contracts for exam attendance and slot start."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import NotRequired, Protocol, TypedDict


class SlotSnapshot(TypedDict):
    id: int
    exam_day_id: int
    round_candidate_id: int
    slot_type: str
    starts_at: str
    ends_at: str
    status: str
    actual_started_at: str | None
    execution_status: str
    status_changed_at: str
    actual_completed_at: str | None
    status_reason: str | None


class DayExecutionSnapshot(TypedDict):
    closure_status: str


class AssignmentSnapshot(TypedDict):
    id: int
    committee_member_id: int
    assignment_role: str
    day_part: str


class AttendanceSnapshot(TypedDict):
    id: int
    status: str
    arrived_at: str | None


class MemberExecutionSnapshot(TypedDict):
    id: int
    representing_side: str


type DayMutationHandle = int
"""Opaque transaction-local guard used to complete a day mutation."""


class DayMutationRequest(TypedDict):
    day_id: int
    kind: str
    entity_id: int
    expected_day_revision: object | None
    actor_member_id: int | None
    protocol_revision_id: int | None


class AttendanceCommand(TypedDict):
    status: object
    arrived_at: NotRequired[object | None]
    expected_day_revision: NotRequired[object | None]


class SlotStartCommand(TypedDict):
    actual_started_at: NotRequired[object | None]
    expected_day_revision: NotRequired[object | None]


class SlotStatusCommand(TypedDict):
    status: object
    reason: NotRequired[object | None]
    actual_started_at: NotRequired[object | None]
    actual_completed_at: NotRequired[object | None]
    expected_day_revision: NotRequired[object | None]


class AttendanceValues(TypedDict):
    status: str
    arrived_at: str | None


class ExecutionIdentitySnapshots(Protocol):
    """Identity-owned membership projection consumed by Execution commands."""

    def members_by_id(self, member_ids: Sequence[int]) -> Mapping[int, MemberExecutionSnapshot]: ...


class ExecutionUnitOfWork(Protocol):
    """One transaction for execution reads, state changes, and day revision."""

    def confirmed_slot(self, day_id: int, slot_id: int) -> SlotSnapshot: ...

    def day_execution_state(self, day_id: int) -> DayExecutionSnapshot: ...

    def guard_day_mutation(self, request: DayMutationRequest) -> DayMutationHandle: ...

    def complete_day_mutation(
        self,
        handle: DayMutationHandle,
        *,
        actor_member_id: int,
        reason: str | None = None,
        protocol_revision_id: int | None = None,
    ) -> None: ...

    def assert_slot_status_mutable(
        self,
        day_id: int,
        slot_id: int,
        *,
        actor_member_id: int,
        expected_day_revision: object | None,
    ) -> None: ...

    def candidate_attendance(self, slot_id: int) -> AttendanceSnapshot | None: ...

    def member_attendance(self, day_id: int, member_id: int) -> AttendanceSnapshot | None: ...

    def assignments(self, day_id: int) -> Sequence[AssignmentSnapshot]: ...

    def confirmed_assignment(self, day_id: int, assignment_id: int) -> AssignmentSnapshot: ...

    def members_by_id(self, member_ids: Sequence[int]) -> Mapping[int, MemberExecutionSnapshot]: ...

    def save_candidate_attendance(
        self,
        day_id: int,
        slot_id: int,
        values: AttendanceValues,
        *,
        actor_member_id: int,
        expected_day_revision: object | None,
    ) -> AttendanceSnapshot: ...

    def save_member_attendance(
        self,
        day_id: int,
        assignment_id: int,
        member_id: int,
        values: AttendanceValues,
        *,
        actor_member_id: int,
        expected_day_revision: object | None,
    ) -> AttendanceSnapshot: ...

    def start_slot(
        self,
        day_id: int,
        slot_id: int,
        *,
        started_at: str,
        participant_member_ids: frozenset[int],
        actor_member_id: int,
        expected_day_revision: object | None,
    ) -> SlotSnapshot: ...

    def ensure_started_protocol(
        self,
        slot_id: int,
        *,
        participant_member_ids: frozenset[int],
        actor_member_id: int,
        started_at: str,
    ) -> None: ...

    def update_slot_status(
        self,
        day_id: int,
        slot_id: int,
        *,
        status: str,
        changed_at: str,
        reason: str | None,
        actual_started_at: str | None,
        actual_completed_at: str | None,
        actor_member_id: int,
        expected_day_revision: object | None,
    ) -> SlotSnapshot: ...


class ExecutionUnitOfWorkFactory(Protocol):
    """Open one read or write transaction for an execution use case."""

    def __call__(self, *, write: bool = False) -> AbstractContextManager[ExecutionUnitOfWork]: ...
