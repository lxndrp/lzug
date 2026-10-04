"""Typed contracts shared by notification policy and delivery adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


@dataclass(frozen=True)
class DeliveryEnvelope:
    """Materialized message values passed to one channel adapter."""

    notification_id: int
    channel: str
    target: str | None
    title: str
    message: str
    action_path: str


@dataclass(frozen=True)
class ClaimedDelivery:
    """Immutable channel input captured by a committed claim transaction."""

    id: int
    claim_token: str
    notification_id: int
    channel: str
    status: str
    attempt_count: int
    push_subscription_id: int | None
    push_endpoint: str | None
    recipient_email: str | None
    title: str
    message: str
    action_path: str


@dataclass(frozen=True)
class DeliveryResult:
    """Policy result persisted only while its claim remains current."""

    status: str
    attempt_count: int
    next_attempt_at: str | None
    technical_confirmed_at: str | None
    error_code: str | None
    invalidate_subscription_id: int | None = None


DELIVERY_CLAIM_TTL_SECONDS = 120


class ProviderOutcomeKind(StrEnum):
    """Transport-neutral result of one provider attempt."""

    SENT = "sent"
    TEMPORARY_FAILURE = "temporary_failure"
    PERMANENT_FAILURE = "permanent_failure"
    INVALID_SUBSCRIPTION = "invalid_subscription"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ProviderOutcome:
    """Normalized provider result with a stable diagnostic code."""

    kind: ProviderOutcomeKind
    error_code: str | None = None


class DeliveryGateway(Protocol):
    """One configured adapter for the notification module's supported channels."""

    def deliver(self, envelope: DeliveryEnvelope) -> ProviderOutcome: ...

    def channels(self) -> tuple[str | None, bool, bool]: ...
