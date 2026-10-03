from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from pywebpush import WebPushException

from backend.integrations.notification_delivery import NotificationDeliveryGateway
from backend.notifications.delivery import (
    DeliveryEnvelope,
    ProviderOutcomeKind,
)


class NotificationDeliveryGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = NotificationDeliveryGateway()
        self.envelope = DeliveryEnvelope(
            notification_id=17,
            channel="web_push",
            target="https://push.example.invalid/subscription",
            title="Title",
            message="Message",
            action_path="/notifications",
        )

    def test_web_push_transport_errors_are_normalized_without_retry_policy(self) -> None:
        cases = (
            (410, ProviderOutcomeKind.INVALID_SUBSCRIPTION, "invalid_subscription"),
            (400, ProviderOutcomeKind.PERMANENT_FAILURE, "push_rejected"),
            (429, ProviderOutcomeKind.TEMPORARY_FAILURE, "push_unavailable"),
            (503, ProviderOutcomeKind.TEMPORARY_FAILURE, "push_unavailable"),
        )
        for status, kind, error_code in cases:
            with (
                self.subTest(status=status),
                patch.object(
                    self.gateway,
                    "_send_web_push",
                    side_effect=WebPushException(
                        "provider response", MagicMock(status_code=status)
                    ),
                ),
            ):
                outcome = self.gateway.deliver(self.envelope)
            self.assertEqual((kind, error_code), (outcome.kind, outcome.error_code))

    def test_smtp_io_failure_is_normalized_as_temporary(self) -> None:
        envelope = DeliveryEnvelope(
            notification_id=17,
            channel="email",
            target="member@example.invalid",
            title="Title",
            message="Message",
            action_path="/notifications",
        )
        with patch.object(self.gateway, "_send_email", side_effect=OSError("offline")):
            outcome = self.gateway.deliver(envelope)
        self.assertEqual(ProviderOutcomeKind.TEMPORARY_FAILURE, outcome.kind)
        self.assertEqual("email_unavailable", outcome.error_code)

    def test_unsupported_channels_do_not_enter_a_provider(self) -> None:
        envelope = DeliveryEnvelope(
            notification_id=17,
            channel="unknown",
            target=None,
            title="Title",
            message="Message",
            action_path="/notifications",
        )
        outcome = self.gateway.deliver(envelope)
        self.assertEqual(ProviderOutcomeKind.UNAVAILABLE, outcome.kind)
        self.assertEqual("unsupported_channel", outcome.error_code)
