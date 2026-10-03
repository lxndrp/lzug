"""Compatibility exports for notification consumers during module handoff."""

from backend.notifications.service import (
    DELIVERY_CLAIM_TTL,
    ClaimedDelivery,
    DeliveryResult,
    NotificationChannels,
    NotificationError,
    NotificationService,
)

__all__ = [
    "DELIVERY_CLAIM_TTL",
    "ClaimedDelivery",
    "DeliveryResult",
    "NotificationChannels",
    "NotificationError",
    "NotificationService",
]
