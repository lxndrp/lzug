"""Contract and detached values for durable Application consequence state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ConsequenceTaskDraft:
    recipient_member_id: int
    consequence_type: str
    action: str
    identity_key: str
    details_json: str


@dataclass(frozen=True)
class ConsequenceTaskSnapshot:
    id: int
    batch_id: int
    origin_type: str
    origin_key: str
    recipient_member_id: int
    consequence_type: str
    action: str
    identity_key: str
    details_json: str
    status: str
    attempt_count: int
    next_attempt_at: str | None
    error_code: str | None
    calendar_event_id: int | None
    calendar_event_version: int | None
    updated_at: str


@dataclass(frozen=True)
class ConsequenceBatchSnapshot:
    id: int
    origin_type: str
    origin_key: str
    confirmed_plan_revision_id: int | None
    notification_scope_json: str
    status: str
    attempt_count: int
    next_attempt_at: str | None
    error_code: str | None
    updated_at: str


class ApplicationConsequenceStore(Protocol):
    """Own due-work discovery and claim transitions for Application follow-ups."""

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
