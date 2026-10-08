"""Persistence ports owned by the notifications module."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.notifications.delivery import ClaimedDelivery, DeliveryResult


class NotificationScope(Protocol):
    """Authorized scope values required by notification queries."""

    member_ids: frozenset[int]
    management_committee_ids: frozenset[int]
    person_id: int | None


@dataclass(frozen=True)
class NotificationRound:
    id: int
    committee_id: int
    status: str
    availability_deadline: str | None
    availability_reminder_at: str | None


@dataclass(frozen=True)
class NotificationMember:
    id: int
    person_id: int
    committee_role: str
    is_active: bool
    committee_id: int


@dataclass(frozen=True)
class AvailabilityResponse:
    member_id: int
    responded_at: str | None
    availability: str


@dataclass(frozen=True)
class ScheduleLine:
    date: str
    venue: str
    room: str


@dataclass(frozen=True)
class NoticeDraft:
    committee_id: int
    round_id: int | None
    recipient_member_id: int
    event_type: str
    origin_key: str
    title: str
    message: str
    action_path: str


@dataclass(frozen=True)
class NoticeWrite:
    id: int
    created: bool


@dataclass(frozen=True)
class OwnNotification:
    id: int
    event_type: str
    title: str
    message: str
    action_path: str
    created_at: str


@dataclass(frozen=True)
class DeliveryDiagnostic:
    notification_id: int
    event_type: str
    recipient_member_id: int
    channel: str
    status: str
    attempt_count: int
    error_code: str | None
    claim_token: str | None
    claimed_at: str | None
    claim_expires_at: str | None
    updated_at: str


@dataclass(frozen=True)
class PlanChangeNotice:
    id: int
    origin_key: str


@dataclass(frozen=True)
class PlanRevision:
    id: int
    round_id: int
    resulting_revision: int


@dataclass(frozen=True)
class DeliveryAttempt:
    attempt_count: int
    technical_confirmed_at: str | None
    claim_token: str | None


@dataclass(frozen=True)
class PushSubscriptionSnapshot:
    id: int
    person_id: int
    active: bool


@dataclass(frozen=True)
class SyntheticMember:
    id: int
    committee_id: int
    active: bool


@dataclass(frozen=True)
class DeliveryFallbackCandidate:
    notification_id: int
    recipient_member_id: int
    status: str
    next_attempt_at: str | None
    claim_token: str | None


class NotificationUnitOfWork(Protocol):
    """Short persistence transaction over notification-owned data."""

    def round(self, round_id: int) -> NotificationRound | None: ...

    def due_rounds(self) -> tuple[NotificationRound, ...]: ...

    def active_members(self, committee_id: int) -> tuple[NotificationMember, ...]: ...

    def availability_responses(self, round_id: int) -> tuple[AvailabilityResponse, ...]: ...

    def assigned_member_ids(self, round_id: int) -> tuple[int, ...]: ...

    def schedule_lines(self, round_id: int, member_id: int) -> tuple[ScheduleLine, ...]: ...

    def save_notice(self, draft: NoticeDraft) -> NoticeWrite: ...

    def queue_deliveries(
        self,
        notification_id: int,
        recipient_member_id: int,
        channels: tuple[str | None, bool, bool],
        *,
        only_channel: str | None = None,
        urgent_email: bool = False,
    ) -> None: ...

    def problem_count(self, notification_ids: tuple[int, ...]) -> int: ...

    def own_notifications(self, member_ids: tuple[int, ...]) -> tuple[OwnNotification, ...]: ...

    def delivery_diagnostics(
        self, committee_ids: tuple[int, ...], *, problems_only: bool
    ) -> tuple[DeliveryDiagnostic, ...]: ...

    def plan_change_notices(
        self, round_id: int, recipient_member_id: int, newer_revision_id: int
    ) -> tuple[PlanChangeNotice, ...]: ...

    def plan_revision(self, revision_id: int) -> PlanRevision | None: ...

    def latest_plan_revision(self, round_id: int) -> PlanRevision | None: ...

    def delivery_attempts(self, notification_id: int) -> tuple[DeliveryAttempt, ...]: ...

    def supersede_plan_change(
        self, notification_id: int, newer_revision_id: int, at: str
    ) -> None: ...

    def push_subscription_by_endpoint(self, endpoint: str) -> PushSubscriptionSnapshot | None: ...

    def add_push_subscription(self, person_id: int, endpoint: str, at: str) -> int: ...

    def reactivate_push_subscription(self, subscription_id: int, at: str) -> None: ...

    def push_subscription(self, subscription_id: int) -> PushSubscriptionSnapshot | None: ...

    def invalidate_push_subscription(self, subscription_id: int, at: str) -> None: ...

    def confirm_push_deliveries(
        self, notification_id: int, member_ids: tuple[int, ...], at: str
    ) -> bool: ...

    def synthetic_member(self, member_id: int) -> SyntheticMember | None: ...

    def delivery_diagnostics_for_notice(
        self, notification_id: int
    ) -> tuple[DeliveryDiagnostic, ...]: ...

    def delivery_fallback_candidates(self) -> tuple[DeliveryFallbackCandidate, ...]: ...

    def queue_email(self, notification_id: int, recipient_member_id: int) -> None: ...


class NotificationUnitOfWorkFactory(Protocol):
    """Open a fresh unit of work for one notification command or query."""

    def __call__(
        self, *, begin_immediate: bool = False
    ) -> AbstractContextManager[NotificationUnitOfWork]: ...


class NotificationDeliveryUnitOfWork(Protocol):
    """Short transaction for acquiring or completing notification claims."""

    def claim_due(
        self,
        current: datetime,
        claim_token: str,
        *,
        batch_size: int,
    ) -> list[ClaimedDelivery]: ...

    def complete_claim(
        self,
        claimed: ClaimedDelivery,
        result: DeliveryResult,
        completed_at: datetime,
    ) -> bool: ...


class NotificationDeliveryUnitOfWorkFactory(Protocol):
    """Open one claim-acquisition or claim-completion transaction."""

    def __call__(self) -> AbstractContextManager[NotificationDeliveryUnitOfWork]: ...
