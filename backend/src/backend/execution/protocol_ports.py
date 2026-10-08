"""Persistence-neutral contracts for the exam protocol workflow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Protocol, TypedDict

from backend.execution.slot_ports import DayMutationHandle, DayMutationRequest


class ProtocolEntryDraft(TypedDict):
    category: str
    statement: str
    occurred_from: str
    occurred_to: str | None


class ProtocolEntrySnapshot(ProtocolEntryDraft):
    id: int
    recorded_by_member_id: int
    created_at: str


class ProtocolResponseSnapshot(TypedDict):
    id: int
    committee_member_id: int
    response: str
    entry_id: int | None
    statement: str | None
    responded_at: str


class ProtocolRevisionSnapshot(TypedDict):
    id: int
    version: int
    declaration: str | None
    workflow_state: str
    previous_revision_id: int | None
    correction_request_id: int | None
    changed_by_member_id: int | None
    change_reason: str | None
    submitted_by_member_id: int | None
    submitted_at: str | None
    created_at: str
    entries: Sequence[ProtocolEntrySnapshot]
    responses: Sequence[ProtocolResponseSnapshot]


class ProtocolCorrectionRequestSnapshot(TypedDict):
    id: int
    revision_id: int
    version: int
    requested_by_member_id: int
    reason: str
    status: str
    requested_at: str
    opened_by_member_id: int | None
    opened_at: str | None
    reopening_reference: str | None


class ProtocolRetentionSnapshot(TypedDict):
    rule_reference: str
    retain_until: str | None
    legal_hold: bool
    hold_reason: str | None
    updated_by_member_id: int
    updated_at: str


class ExecutionProtocolSnapshot(TypedDict):
    id: int
    exam_slot_id: int
    current_version: int
    source: str
    created_at: str
    updated_at: str
    exam_day_id: int | None
    day_revision: int | None
    day_status: str | None
    day_closure_status: str | None
    reopening_scope: Sequence[str]
    committee_id: int | None
    participants: Sequence[int]
    late_response_member_ids: Sequence[int]
    revisions: Sequence[ProtocolRevisionSnapshot]
    correction_requests: Sequence[ProtocolCorrectionRequestSnapshot]
    retention: ProtocolRetentionSnapshot | None


class ProtocolRevisionWrite(TypedDict):
    protocol_id: int
    expected_version: int
    declaration: str
    workflow_state: str
    previous_revision_id: int
    correction_request_id: int | None
    actor_member_id: int
    change_reason: str | None
    created_at: str
    entries: Sequence[ProtocolEntryDraft]


class ProtocolSubmissionWrite(TypedDict):
    protocol_id: int
    version: int
    actor_member_id: int
    submitted_at: str


class ProtocolResponseWrite(TypedDict):
    protocol_id: int
    version: int
    actor_member_id: int
    response: str
    entry_id: int | None
    statement: str | None
    responded_at: str


class ProtocolCorrectionRequestWrite(TypedDict):
    protocol_id: int
    revision_id: int
    actor_member_id: int
    reason: str
    requested_at: str


class ProtocolCorrectionOpenWrite(TypedDict):
    protocol_id: int
    expected_version: int
    correction_request_id: int
    actor_member_id: int
    reason: str
    reopening_reference: str | None
    created_at: str


class ProtocolRetentionWrite(TypedDict):
    protocol_id: int
    rule_reference: str
    retain_until: str | None
    legal_hold: bool
    hold_reason: str | None
    actor_member_id: int
    updated_at: str


class ProtocolDaySlotSnapshot(TypedDict):
    exam_slot_id: int
    actual_started_at: str | None
    execution_status: str
    protocol: ExecutionProtocolSnapshot | None


class ProtocolDaySnapshot(TypedDict):
    exam_day_id: int
    committee_id: int | None
    slots: Sequence[ProtocolDaySlotSnapshot]


class ExecutionProtocolUnitOfWork(Protocol):
    """Transaction-bound protocol reads and mutations owned by Execution."""

    def protocol_by_id(self, protocol_id: int) -> ExecutionProtocolSnapshot | None: ...

    def protocol_by_slot(self, slot_id: int) -> ExecutionProtocolSnapshot | None: ...

    def protocol_references(self, protocol_id: int) -> Mapping[str, object]: ...

    def protocol_day_snapshot(self, day_id: int) -> ProtocolDaySnapshot | None: ...

    def write_protocol_revision(self, command: ProtocolRevisionWrite) -> None: ...

    def submit_protocol_revision(self, command: ProtocolSubmissionWrite) -> None: ...

    def write_protocol_response(self, command: ProtocolResponseWrite) -> None: ...

    def write_protocol_correction_request(
        self, command: ProtocolCorrectionRequestWrite
    ) -> None: ...

    def open_protocol_correction(self, command: ProtocolCorrectionOpenWrite) -> None: ...

    def save_protocol_retention(self, command: ProtocolRetentionWrite) -> None: ...

    def guard_day_mutation(self, request: DayMutationRequest) -> DayMutationHandle: ...

    def complete_day_mutation(
        self,
        handle: DayMutationHandle,
        *,
        actor_member_id: int,
        reason: str | None = None,
        protocol_revision_id: int | None = None,
    ) -> None: ...


class ExecutionProtocolUnitOfWorkFactory(Protocol):
    """Open one read or write transaction for an Execution protocol use case."""

    def __call__(
        self, *, write: bool = False
    ) -> AbstractContextManager[ExecutionProtocolUnitOfWork]: ...
