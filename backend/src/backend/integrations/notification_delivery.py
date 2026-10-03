"""SMTP, Web Push and recording adapters for notification delivery."""

from __future__ import annotations

import base64
import smtplib
from email.message import EmailMessage
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import Vapid, WebPushException, webpush
from requests.exceptions import RequestException

from backend.notifications.delivery import (
    DeliveryEnvelope,
    ProviderOutcome,
    ProviderOutcomeKind,
)
from backend.settings import RuntimeSettings


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class NotificationDeliveryGateway:
    """Translate provider and library errors into stable delivery outcomes."""

    def __init__(self, settings: RuntimeSettings | None = None) -> None:
        self._settings_override = settings

    def _runtime_settings(self) -> RuntimeSettings:
        return self._settings_override or RuntimeSettings.from_environment()

    def channels(self) -> tuple[str | None, bool, bool]:
        notification_settings = self._runtime_settings().notifications
        subject = self._vapid_subject()
        return (
            self._push_public_key() if subject else None,
            notification_settings.smtp_host is not None,
            notification_settings.sink_enabled,
        )

    def deliver(self, envelope: DeliveryEnvelope) -> ProviderOutcome:
        try:
            if envelope.channel == "sink":
                return ProviderOutcome(ProviderOutcomeKind.SENT)
            if envelope.channel == "web_push":
                if envelope.target is None:
                    return ProviderOutcome(
                        ProviderOutcomeKind.INVALID_SUBSCRIPTION, "invalid_subscription"
                    )
                self._send_web_push(envelope.target, envelope.notification_id)
                return ProviderOutcome(ProviderOutcomeKind.SENT)
            if envelope.channel == "email":
                if envelope.target is None:
                    return ProviderOutcome(
                        ProviderOutcomeKind.TEMPORARY_FAILURE, "email_unavailable"
                    )
                self._send_email(envelope)
                return ProviderOutcome(ProviderOutcomeKind.SENT)
            return ProviderOutcome(ProviderOutcomeKind.UNAVAILABLE, "unsupported_channel")
        except WebPushException as error:
            if error.status_code in {404, 410}:
                return ProviderOutcome(
                    ProviderOutcomeKind.INVALID_SUBSCRIPTION, "invalid_subscription"
                )
            if (
                error.status_code is not None
                and 400 <= error.status_code < 500
                and error.status_code != 429
            ):
                return ProviderOutcome(ProviderOutcomeKind.PERMANENT_FAILURE, "push_rejected")
            return ProviderOutcome(ProviderOutcomeKind.TEMPORARY_FAILURE, "push_unavailable")
        except OSError, smtplib.SMTPException, RequestException:
            return ProviderOutcome(
                ProviderOutcomeKind.TEMPORARY_FAILURE,
                f"{envelope.channel}_unavailable",
            )

    def _send_web_push(self, endpoint: str, notification_id: int) -> None:
        private_key = self._vapid_private_key()
        subject = self._vapid_subject()
        if private_key is None or subject is None:
            raise OSError("Web Push is not configured")
        webpush(
            subscription_info={"endpoint": endpoint},
            vapid_private_key=Vapid(private_key),
            vapid_claims={"sub": subject},
            ttl=300,
            timeout=10,
            headers={
                "Urgency": "normal",
                "Topic": _base64url(f"lzug-{notification_id}".encode())[:32],
            },
        )

    def _send_email(self, envelope: DeliveryEnvelope) -> None:
        runtime_settings = self._runtime_settings()
        settings = runtime_settings.notifications
        if settings.smtp_host is None or envelope.target is None:
            raise OSError("SMTP is not configured")
        message = EmailMessage()
        message["Subject"] = envelope.title
        message["From"] = settings.smtp_from
        message["To"] = envelope.target
        base_url = (runtime_settings.integrations.external_url or "").rstrip("/")
        message.set_content(f"{envelope.message}\n\n{base_url}{envelope.action_path}")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_starttls:
                client.starttls()
            username = settings.smtp_username
            password = settings.smtp_password_value
            if username and password:
                client.login(username, password)
            client.send_message(message)

    def _vapid_private_key(self):
        value = self._runtime_settings().notifications.push_private_key
        if not value:
            return None
        try:
            key = serialization.load_pem_private_key(value.replace("\\n", "\n").encode(), None)
        except ValueError as error:
            raise ValueError("Invalid Web Push VAPID private key") from error
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
            key.curve, ec.SECP256R1
        ):
            raise ValueError("Web Push VAPID key must use P-256")
        return key

    def _push_public_key(self) -> str | None:
        key = self._vapid_private_key()
        if key is None:
            return None
        return _base64url(
            key.public_key().public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        )

    def _vapid_subject(self) -> str | None:
        value = self._runtime_settings().notifications.web_push_subject
        if not value:
            return None
        parsed = urlsplit(value)
        if value.startswith("mailto:") and "@" in value.removeprefix("mailto:"):
            return value
        if parsed.scheme == "https" and parsed.netloc:
            return value
        raise ValueError("Web Push subject must be a mailto or HTTPS URI")
