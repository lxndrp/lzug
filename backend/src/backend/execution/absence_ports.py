"""Consumer-owned Persistence-neutral contracts for absence workflows."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, NewType, Protocol

from backend.mutation_locks import MutationLockCommand

AbsenceDayMutationHandle = NewType("AbsenceDayMutationHandle", object)


@dataclass(frozen=True)
class AbsenceReportSnapshot:
    id: int
    exam_day_id: int
    exam_day_assignment_id: int
    committee_member_id: int
    reported_by_member_id: int
    reported_at: str
    reason: str | None
    status: str
    selected_replacement_member_id: int | None
    version: int
    created_at: str
    updated_at: str | None


@dataclass(frozen=True)
class AbsenceResponseSnapshot:
    id: int
    absence_report_id: int
    committee_member_id: int
    response: str
    requested_at: str
    expires_at: str | None
    urgent: bool
    responded_at: str | None


@dataclass(frozen=True)
class AbsenceAuditSnapshot:
    id: int
    actor_member_id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    details: str | None
    created_at: str


@dataclass(frozen=True)
class AbsenceDaySnapshot:
    id: int
    exam_round_id: int
    date: str
    status: str
    closure_status: str
    revision: int


@dataclass(frozen=True)
class AbsenceRoundSnapshot:
    id: int
    committee_id: int
    exam_half_year_id: int
    status: str


@dataclass(frozen=True)
class AbsenceAssignmentSnapshot:
    id: int
    exam_day_id: int
    committee_member_id: int
    revision: int
    assignment_role: str
    day_part: str
    fallback_status: str | None


@dataclass(frozen=True)
class AbsenceMemberSnapshot:
    id: int
    representing_side: str
    is_active: bool


@dataclass(frozen=True)
class AbsenceTargetSnapshot:
    day: AbsenceDaySnapshot
    round: AbsenceRoundSnapshot
    assignment: AbsenceAssignmentSnapshot
    target: AbsenceMemberSnapshot


@dataclass(frozen=True)
class AbsenceCandidateFacts:
    active_members: tuple[AbsenceMemberSnapshot, ...]
    regular_member_ids: frozenset[int]
    fallback_member_ids: frozenset[int]
    available_member_ids: frozenset[int]
    conflict_free_member_ids: frozenset[int]


@dataclass(frozen=True)
class AbsenceViewSnapshot:
    report: AbsenceReportSnapshot
    day: AbsenceDaySnapshot
    round: AbsenceRoundSnapshot
    assignment: AbsenceAssignmentSnapshot
    responses: tuple[AbsenceResponseSnapshot, ...]
    audit: tuple[AbsenceAuditSnapshot, ...]


class AbsenceUnitOfWork(Protocol):
    """Read detached facts and persist absence commands in one transaction.

    The factory's default scope is one immediate write transaction. All lock checks,
    day-mutation guards, audit writes, and domain writes for a command share it.
    `report_view` returns every response and audit row in their existing ascending
    timestamp/id order; `reports_for_committees` orders reports newest first.
    Candidate facts are data only: eligibility policy remains in Execution.
    """

    def assert_mutation_allowed(self, command: MutationLockCommand) -> None: ...

    def reports_for_committees(
        self, committee_ids: Sequence[int]
    ) -> Sequence[AbsenceViewSnapshot]: ...

    def report(self, report_id: int) -> AbsenceReportSnapshot | None: ...

    def report_view(self, report_id: int) -> AbsenceViewSnapshot | None: ...

    def target(
        self, day_id: int, assignment_id: int | None, member_id: int | None
    ) -> AbsenceTargetSnapshot | None: ...

    def report_context(
        self, report_id: int
    ) -> tuple[AbsenceReportSnapshot, AbsenceDaySnapshot, AbsenceRoundSnapshot] | None: ...

    def response(self, response_id: int) -> AbsenceResponseSnapshot | None: ...

    def response_member_ids(self, report_id: int) -> frozenset[int]: ...

    def active_report_exists(self, assignment_id: int, statuses: frozenset[str]) -> bool: ...

    def candidate_facts(
        self, day: AbsenceDaySnapshot, assignment: AbsenceAssignmentSnapshot
    ) -> AbsenceCandidateFacts: ...

    def member(self, member_id: int) -> AbsenceMemberSnapshot | None: ...

    def assignment(self, assignment_id: int) -> AbsenceAssignmentSnapshot | None: ...

    def assignment_slots(self, day_id: int) -> Sequence[str]: ...

    def notification_recipients(
        self,
        committee_id: int,
        *,
        roles: frozenset[str] | None = None,
        exclude_member_id: int | None = None,
    ) -> frozenset[int]: ...

    def guard_day_mutation(
        self,
        *,
        day_id: int,
        kind: str,
        entity_id: int,
        payload: dict[str, object],
        actor_member_id: int,
    ) -> AbsenceDayMutationHandle: ...

    def complete_day_mutation(
        self,
        handle: AbsenceDayMutationHandle,
        *,
        actor_member_id: int,
        reason: str | None = None,
    ) -> None: ...

    def day_guard_snapshot(self, handle: AbsenceDayMutationHandle) -> dict[str, object]: ...

    def record_consequence_source(
        self,
        *,
        audit_event_id: int,
        report_id: int,
        report_version: int,
        assignment_id: int,
        assignment_revision: int,
        source_json: str,
        created_at: str,
    ) -> dict[str, Any]: ...

    def sources_after_cutover(self) -> Sequence[dict[str, Any]]: ...

    def source_by_origin(self, origin_id: str) -> dict[str, Any] | None: ...

    def legacy_unreplayable_count(self) -> int: ...

    def insert_report(
        self,
        *,
        target: AbsenceTargetSnapshot,
        reported_by_member_id: int,
        reported_at: str,
        reason: str | None,
        status: str,
    ) -> AbsenceReportSnapshot: ...

    def insert_response(
        self,
        *,
        report_id: int,
        member_id: int,
        requested_at: str,
        expires_at: str | None,
        urgent: bool,
    ) -> None: ...

    def insert_audit(
        self,
        *,
        report_id: int,
        actor_member_id: int,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        created_at: str,
        details: dict[str, object] | None = None,
    ) -> int: ...

    def update_report(
        self,
        report_id: int,
        *,
        status: str,
        current: str,
        selected_replacement_member_id: int | None = None,
        update_selected_replacement: bool = False,
        increment_version: bool = True,
    ) -> AbsenceReportSnapshot: ...

    def update_response(
        self, response_id: int, *, response: str, responded_at: str
    ) -> AbsenceResponseSnapshot: ...

    def update_assignment_member(
        self,
        assignment_id: int,
        member_id: int,
        *,
        fallback_status: str | None = None,
    ) -> None: ...

    def set_fallback_status(self, assignment_id: int, status: str) -> None: ...


class AbsenceUnitOfWorkFactory(Protocol):
    """Open an immediate writer UoW or a read-only materialization scope."""

    def __call__(self) -> AbstractContextManager[AbsenceUnitOfWork]: ...

    def read_scope(self) -> AbstractContextManager[AbsenceUnitOfWork]: ...
