"""Consumer-owned capabilities for reliable cross-module consequences."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Protocol, TypedDict

from backend.planning.plan_consequences import PlanConsequenceSource
from backend.planning.proposals import ConfirmedPlanRevision
from backend.planning.venue_consequences import VenueAuditConsequenceSource
from backend.planning_ports import VenueAuditEventSnapshot


class ConsequenceTaskDraft(TypedDict):
    """Application-owned description persisted by an outer storage adapter."""

    recipient_member_id: int
    consequence_type: str
    action: str
    identity_key: str
    details_json: str


class ConsequenceTaskSnapshot(Protocol):
    """Detached task values the Application needs from its consequence store."""

    @property
    def id(self) -> int: ...

    @property
    def batch_id(self) -> int: ...

    @property
    def origin_type(self) -> str: ...

    @property
    def origin_key(self) -> str: ...

    @property
    def recipient_member_id(self) -> int: ...

    @property
    def consequence_type(self) -> str: ...

    @property
    def action(self) -> str: ...

    @property
    def identity_key(self) -> str: ...

    @property
    def details_json(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def attempt_count(self) -> int: ...

    @property
    def next_attempt_at(self) -> str | None: ...

    @property
    def error_code(self) -> str | None: ...

    @property
    def calendar_event_id(self) -> int | None: ...

    @property
    def calendar_event_version(self) -> int | None: ...

    @property
    def updated_at(self) -> str: ...


class ConsequenceBatchSnapshot(Protocol):
    """Detached batch values the Application needs from its consequence store."""

    @property
    def id(self) -> int: ...

    @property
    def origin_type(self) -> str: ...

    @property
    def origin_key(self) -> str: ...

    @property
    def confirmed_plan_revision_id(self) -> int | None: ...

    @property
    def notification_scope_json(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def attempt_count(self) -> int: ...

    @property
    def next_attempt_at(self) -> str | None: ...

    @property
    def error_code(self) -> str | None: ...

    @property
    def updated_at(self) -> str: ...


class ApplicationConsequenceStore(Protocol):
    """Consumer-owned storage capabilities for Application consequence work."""

    def claim_task(self, task_id: int, *, now: str, lease_until: str) -> bool: ...

    def due_task_ids(
        self,
        *,
        origin_type: str,
        now: str,
        batch_id: int | None = None,
    ) -> tuple[int, ...]: ...

    def due_revision_ids(self, revision_ids: tuple[int, ...], *, now: str) -> tuple[int, ...]: ...

    def record_batch(
        self,
        *,
        origin_type: str,
        origin_key: str,
        confirmed_plan_revision_id: int | None,
        notification_scope: tuple[int, ...],
        tasks: tuple[ConsequenceTaskDraft, ...],
        error_code: str | None,
        now: str,
    ) -> int: ...

    def batch_by_origin(
        self, origin_type: str, origin_key: str
    ) -> ConsequenceBatchSnapshot | None: ...

    def batches_by_origin(
        self, origin_type: str, *, excluding_origin_key: str | None = None
    ) -> tuple[ConsequenceBatchSnapshot, ...]: ...

    def task(self, task_id: int) -> ConsequenceTaskSnapshot | None: ...

    def tasks_for_batch(
        self, batch_id: int, *, statuses: frozenset[str] | None = None
    ) -> tuple[ConsequenceTaskSnapshot, ...]: ...

    def set_batch_state(
        self,
        batch_id: int,
        *,
        status: str,
        attempt_count: int,
        next_attempt_at: str | None,
        error_code: str | None,
        updated_at: str,
    ) -> None: ...

    def set_task_state(
        self,
        task_id: int,
        *,
        status: str,
        attempt_count: int,
        next_attempt_at: str | None,
        error_code: str | None,
        calendar_event_id: int | None,
        calendar_event_version: int | None,
        updated_at: str,
        expected_claim_until: str | None = None,
    ) -> bool: ...


ApplicationConsequenceStoreFactory = Callable[[Path], ApplicationConsequenceStore]


class PlanConsequencePlanningPort(Protocol):
    """Expose immutable Planning facts and deterministic plan descriptions."""

    def confirmed_plan_revision_ids(self) -> tuple[int, ...]: ...

    def confirmed_plan_revision(self, revision_id: int) -> ConfirmedPlanRevision | None: ...

    def confirmed_plan_revisions(self, round_id: int) -> Sequence[ConfirmedPlanRevision]: ...

    def plan_consequence_source(self, revision_id: int) -> PlanConsequenceSource | None: ...


class VenueConsequencePlanningPort(Protocol):
    """Expose Planning-owned venue snapshots and typed consequence descriptions."""

    def preview(
        self,
        *,
        venue_id: int,
        entity_type: str,
        entity_id: int,
        before: dict,
        after: dict,
        meaningful_change: bool,
        today: date | None = None,
    ) -> dict: ...

    def audits_for_venue(self, venue_id: int) -> tuple[VenueAuditEventSnapshot, ...]: ...

    def consequence_audits(self) -> tuple[VenueAuditEventSnapshot, ...]: ...

    def source_for_audit(
        self, audit_id: int, *, today: date | None = None
    ) -> VenueAuditConsequenceSource | None: ...

    def is_current(self, consequence_type: str, details: dict, *, today: date) -> bool: ...


class NotificationApplicationPort(Protocol):
    """Expose only the channel-neutral notice operations this workflow consumes."""

    def create_direct(
        self,
        *,
        committee_id: int,
        round_id: int | None,
        recipient_member_ids: set[int],
        event_type: str,
        title: str,
        message: str,
        action_path: str,
        origin_key: str,
        urgent: bool = False,
    ) -> int: ...

    def create_plan_change(
        self,
        *,
        committee_id: int,
        round_id: int,
        recipient_member_id: int,
        revision_id: int,
        title: str,
        message: str,
        action_path: str,
    ) -> tuple[bool, set[int]]: ...

    def create_direct_if_current(
        self,
        *,
        is_current: Callable[[], bool],
        committee_id: int,
        round_id: int | None,
        recipient_member_id: int,
        event_type: str,
        title: str,
        message: str,
        action_path: str,
        origin_key: str,
    ) -> bool:
        """Write only if a read-only source check passes inside the notice UoW.

        Implementations hold SQLite write intent while invoking the guard so
        the source cannot change between validation and notice persistence.
        The guard may read its owning domain but must not write or dispatch.
        """
        ...


__all__ = [
    "ApplicationConsequenceStore",
    "ApplicationConsequenceStoreFactory",
    "ConsequenceBatchSnapshot",
    "ConsequenceTaskDraft",
    "ConsequenceTaskSnapshot",
    "NotificationApplicationPort",
    "PlanConsequencePlanningPort",
    "VenueConsequencePlanningPort",
]
