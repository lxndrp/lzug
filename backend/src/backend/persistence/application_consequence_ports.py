"""Contract and detached values for durable Application consequence state."""

from __future__ import annotations

from dataclasses import dataclass


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
