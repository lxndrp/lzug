"""Consumer-owned capabilities for reliable cross-module consequences."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Protocol

from backend.persistence.application_consequence_ports import (
    ConsequenceBatchSnapshot,
    ConsequenceTaskDraft,
    ConsequenceTaskSnapshot,
)
from backend.planning.plan_consequences import PlanConsequenceSource
from backend.planning.proposals import ConfirmedPlanRevision
from backend.planning.venue_consequences import VenueAuditConsequenceSource
from backend.planning_ports import VenueAuditEventSnapshot


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
    ) -> None: ...


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

    def supersede_unsent_plan_changes(
        self,
        *,
        round_id: int,
        recipient_member_id: int,
        newer_revision_id: int,
    ) -> set[int]: ...


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
