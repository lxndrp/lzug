"""Channel-neutral notifications and best-effort technical delivery."""

from __future__ import annotations

import base64
import json
import os
import smtplib
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .authorization import AuthorizationScope
from .database import DEFAULT_DB_PATH, session_scope
from .models import (
    CommitteeMember,
    ExamDay,
    ExamDayAssignment,
    ExamRound,
    Location,
    MemberAvailability,
    Notification,
    NotificationDelivery,
    Person,
    PushSubscription,
)

DELIVERY_STATUSES = frozenset(
    {
        "pending",
        "technically_confirmed",
        "temporarily_failed",
        "permanently_failed",
        "unavailable",
    }
)
MAX_DELIVERY_ATTEMPTS = 4
PUSH_CONFIRMATION_TIMEOUT = timedelta(minutes=15)


class NotificationError(RuntimeError):
    """A safe notification failure that must not roll back the domain event."""


@dataclass(frozen=True)
class NotificationChannels:
    push_public_key: str | None
    email_configured: bool
    sink_enabled: bool


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _now(value).isoformat(timespec="seconds")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class NotificationService:
    """Persist domain notices once and process optional channels independently."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path

    def channels(self) -> NotificationChannels:
        subject = self._vapid_subject()
        return NotificationChannels(
            push_public_key=self._push_public_key() if subject else None,
            email_configured=bool(os.environ.get("LZUG_SMTP_HOST")),
            sink_enabled=os.environ.get("LZUG_NOTIFICATION_SINK", "").lower()
            in {"1", "true", "operator"},
        )

    def create_for_event(self, event_type: str, round_id: int) -> dict[str, int]:
        """Create at most one notice per eligible recipient and event origin."""
        with session_scope(self.db_path) as session:
            exam_round = session.get(ExamRound, round_id)
            if exam_round is None:
                raise NotificationError("Exam round not found")
            recipients = self._recipients(session, event_type, exam_round)
            created = 0
            notification_ids: list[int] = []
            for member_id in sorted(recipients):
                title, message, action_path = self._content(
                    session, event_type, exam_round, member_id
                )
                notification = Notification(
                    committee_id=exam_round.committee_id,
                    exam_round_id=exam_round.id,
                    recipient_member_id=member_id,
                    event_type=event_type,
                    origin_key=f"exam-round:{exam_round.id}",
                    title=title,
                    message=message,
                    action_path=action_path,
                )
                try:
                    with session.begin_nested():
                        session.add(notification)
                        session.flush()
                except IntegrityError:
                    existing_id = session.scalar(
                        select(Notification.id).where(
                            Notification.recipient_member_id == member_id,
                            Notification.event_type == event_type,
                            Notification.origin_key == f"exam-round:{exam_round.id}",
                        )
                    )
                    if existing_id is not None:
                        notification_ids.append(existing_id)
                    continue
                created += 1
                notification_ids.append(notification.id)
                self._queue_deliveries(session, notification)
        dispatched = self.process_deliveries()
        with session_scope(self.db_path) as session:
            problems = (
                session.query(NotificationDelivery)
                .filter(
                    NotificationDelivery.notification_id.in_(notification_ids),
                    NotificationDelivery.status.in_(
                        {"temporarily_failed", "permanently_failed", "unavailable"}
                    ),
                )
                .count()
                if notification_ids
                else 0
            )
        return {"created": created, "dispatched": dispatched, "problems": problems}

    def process_due_events(self, *, now: datetime | None = None) -> dict[str, int]:
        current = _now(now)
        created = 0
        with session_scope(self.db_path) as session:
            rounds = session.scalars(
                select(ExamRound).where(ExamRound.status == "availability_requested")
            ).all()
            due = [
                (
                    round_row.id,
                    round_row.availability_reminder_at,
                    round_row.availability_deadline,
                )
                for round_row in rounds
            ]
        for round_id, reminder_at, deadline in due:
            if reminder_at and self._parse_timestamp(reminder_at) <= current:
                created += self.create_for_event("availability_reminder", round_id)["created"]
            if deadline and self._parse_timestamp(deadline) <= current:
                created += self.create_for_event("availability_deadline_expired", round_id)[
                    "created"
                ]
        return {"created": created, "dispatched": self.process_deliveries(now=current)}

    def list_own(self, scope: AuthorizationScope) -> list[dict[str, object]]:
        if not scope.member_ids:
            return []
        with session_scope(self.db_path) as session:
            rows = session.scalars(
                select(Notification)
                .where(Notification.recipient_member_id.in_(scope.member_ids))
                .order_by(Notification.created_at.desc(), Notification.id.desc())
            ).all()
            return [self._notification_view(row) for row in rows]

    def problems(self, scope: AuthorizationScope) -> list[dict[str, object]]:
        return self._management_deliveries(scope, problems_only=True)

    def management_overview(self, scope: AuthorizationScope) -> list[dict[str, object]]:
        """Return content-free delivery metadata for committees managed by the actor."""
        return self._management_deliveries(scope, problems_only=False)

    def _management_deliveries(
        self, scope: AuthorizationScope, *, problems_only: bool
    ) -> list[dict[str, object]]:
        if not scope.management_committee_ids:
            return []
        with session_scope(self.db_path) as session:
            statement = (
                select(NotificationDelivery, Notification)
                .join(Notification, Notification.id == NotificationDelivery.notification_id)
                .where(Notification.committee_id.in_(scope.management_committee_ids))
            )
            if problems_only:
                statement = statement.where(
                    NotificationDelivery.status.in_(
                        {"temporarily_failed", "permanently_failed", "unavailable"}
                    )
                )
            rows = session.execute(statement.order_by(NotificationDelivery.updated_at.desc())).all()
            return [
                {
                    "notification_id": notice.id,
                    "event_type": notice.event_type,
                    "recipient_member_id": notice.recipient_member_id,
                    "channel": delivery.channel,
                    "status": delivery.status,
                    "attempt_count": delivery.attempt_count,
                    "error_code": delivery.error_code,
                    "updated_at": delivery.updated_at,
                }
                for delivery, notice in rows
            ]

    def register_push(self, scope: AuthorizationScope, endpoint: str) -> dict[str, object]:
        if scope.person_id is None:
            raise ValueError("An active person is required")
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or len(endpoint) > 2048:
            raise ValueError("A valid HTTPS push endpoint is required")
        with session_scope(self.db_path) as session:
            existing = session.scalars(
                select(PushSubscription).where(PushSubscription.endpoint == endpoint)
            ).first()
            if existing is not None:
                if existing.person_id != scope.person_id:
                    raise ValueError("Push endpoint is already registered")
                existing.invalidated_at = None
                existing.updated_at = _timestamp(_now())
                row = existing
            else:
                row = PushSubscription(person_id=scope.person_id, endpoint=endpoint)
                session.add(row)
            session.flush()
            return {"id": row.id, "active": row.invalidated_at is None}

    def unregister_push(self, scope: AuthorizationScope, subscription_id: int) -> bool:
        with session_scope(self.db_path) as session:
            row = session.get(PushSubscription, subscription_id)
            if row is None or row.person_id != scope.person_id:
                return False
            row.invalidated_at = _timestamp(_now())
            return True

    def confirm_push(self, scope: AuthorizationScope, notification_id: int) -> bool:
        with session_scope(self.db_path) as session:
            notification = session.get(Notification, notification_id)
            if notification is None or notification.recipient_member_id not in scope.member_ids:
                return False
            rows = session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.notification_id == notification_id,
                    NotificationDelivery.channel == "web_push",
                    NotificationDelivery.status == "pending",
                )
            ).all()
            confirmed_at = _timestamp(_now())
            for row in rows:
                row.status = "technically_confirmed"
                row.technical_confirmed_at = confirmed_at
                row.updated_at = confirmed_at
            return bool(rows)

    def synthetic_test(self, member_id: int, channel: str) -> dict[str, object]:
        if channel not in {"web_push", "email"}:
            raise ValueError("Channel must be web_push or email")
        with session_scope(self.db_path) as session:
            member = session.get(CommitteeMember, member_id)
            if member is None or not member.is_active:
                raise ValueError("Active committee member not found")
            origin = f"synthetic:{_timestamp(_now())}:{member_id}:{channel}"
            notice = Notification(
                committee_id=member.committee_id,
                exam_round_id=None,
                recipient_member_id=member.id,
                event_type="synthetic_test",
                origin_key=origin,
                title="Synthetischer Zustellungstest",
                message="Diese Nachricht enthält keine echten Fachdaten.",
                action_path="/notifications",
            )
            session.add(notice)
            session.flush()
            self._queue_deliveries(session, notice, only_channel=channel)
            notice_id = notice.id
        self.process_deliveries()
        with session_scope(self.db_path) as session:
            deliveries = session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.notification_id == notice_id
                )
            ).all()
            return {
                "notification_id": notice_id,
                "deliveries": [self._delivery_diagnostic(row) for row in deliveries],
            }

    def process_deliveries(self, *, now: datetime | None = None) -> int:
        current = _now(now)
        processed = 0
        with session_scope(self.db_path) as session:
            rows = session.scalars(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.status.in_({"pending", "temporarily_failed"}),
                )
                .order_by(NotificationDelivery.id)
            ).all()
            for delivery in rows:
                if (
                    delivery.next_attempt_at
                    and self._parse_timestamp(delivery.next_attempt_at) > current
                ):
                    continue
                if (
                    delivery.channel == "web_push"
                    and delivery.status == "pending"
                    and delivery.attempt_count
                ):
                    self._permanent_failure(
                        delivery, "confirmation_timeout", current, increment=False
                    )
                    processed += 1
                    continue
                notice = session.get(Notification, delivery.notification_id)
                if notice is None:
                    continue
                self._dispatch(session, delivery, notice, current)
                processed += 1
            self._queue_email_fallbacks(session, current)
        return processed

    def _recipients(self, session, event_type: str, exam_round: ExamRound) -> set[int]:
        active = session.scalars(
            select(CommitteeMember).where(
                CommitteeMember.committee_id == exam_round.committee_id,
                CommitteeMember.is_active == 1,
            )
        ).all()
        if event_type == "availability_requested":
            return {member.id for member in active}
        if event_type in {"availability_reminder", "availability_deadline_expired"}:
            availabilities = session.scalars(
                select(MemberAvailability).where(
                    MemberAvailability.exam_round_id == exam_round.id,
                )
            ).all()
            by_member: dict[int, list[MemberAvailability]] = {}
            for availability in availabilities:
                by_member.setdefault(availability.committee_member_id, []).append(availability)
            open_members = {
                member.id
                for member in active
                if not by_member.get(member.id)
                or any(
                    row.responded_at is None or row.availability == "pending"
                    for row in by_member[member.id]
                )
            }
            if event_type == "availability_deadline_expired":
                open_members.update(
                    member.id
                    for member in active
                    if member.committee_role in {"chair", "deputy_chair"}
                )
            return open_members
        if event_type == "plan_confirmed":
            return set(
                session.scalars(
                    select(ExamDayAssignment.committee_member_id)
                    .join(ExamDay, ExamDay.id == ExamDayAssignment.exam_day_id)
                    .where(
                        ExamDay.exam_round_id == exam_round.id,
                        ExamDayAssignment.assignment_role.in_({"examiner", "fallback"}),
                    )
                    .distinct()
                ).all()
            )
        raise NotificationError("Unknown notification event")

    def _content(
        self, session, event_type: str, exam_round: ExamRound, member_id: int
    ) -> tuple[str, str, str]:
        content = {
            "availability_requested": (
                "Verfügbarkeit angefragt",
                "Bitte melden Sie Ihre Verfügbarkeit bis "
                f"{exam_round.availability_deadline} zurück.",
                f"/scheduling-overview/{exam_round.id}",
            ),
            "availability_reminder": (
                "Verfügbarkeitsrückmeldung offen",
                f"Ihre Rückmeldung ist noch bis {exam_round.availability_deadline} möglich.",
                f"/scheduling-overview/{exam_round.id}",
            ),
            "availability_deadline_expired": (
                "Rückmeldefrist abgelaufen",
                "Für diese Terminorganisation ist noch eine Rückmeldung offen.",
                f"/scheduling-overview/{exam_round.id}",
            ),
            "plan_confirmed": (
                "Prüfungsplan bestätigt",
                self._confirmed_schedule_message(session, exam_round.id, member_id),
                f"/confirmed-plans/{exam_round.id}",
            ),
        }
        return content[event_type]

    @staticmethod
    def _confirmed_schedule_message(session, round_id: int, member_id: int) -> str:
        rows = session.execute(
            select(ExamDay, Location)
            .join(ExamDayAssignment, ExamDayAssignment.exam_day_id == ExamDay.id)
            .join(Location, Location.id == ExamDay.location_id)
            .where(
                ExamDay.exam_round_id == round_id,
                ExamDayAssignment.committee_member_id == member_id,
            )
            .order_by(ExamDay.date, Location.name)
        ).all()
        appointments = list(
            dict.fromkeys(
                f"{day.date} – {location.name}, {location.room}" for day, location in rows
            )
        )
        return "Ihre Einsätze: " + "; ".join(appointments)

    def _queue_deliveries(
        self, session, notice: Notification, *, only_channel: str | None = None
    ) -> None:
        channels = self.channels()
        if channels.sink_enabled:
            session.add(
                NotificationDelivery(
                    notification_id=notice.id,
                    channel="sink",
                    target_key="operator-sink",
                    status="pending",
                )
            )
            return
        if only_channel in {None, "web_push"}:
            member = session.get(CommitteeMember, notice.recipient_member_id)
            subscriptions = session.scalars(
                select(PushSubscription).where(
                    PushSubscription.person_id == (member.person_id if member else -1),
                    PushSubscription.invalidated_at.is_(None),
                )
            ).all()
            if subscriptions and channels.push_public_key:
                for subscription in subscriptions:
                    session.add(
                        NotificationDelivery(
                            notification_id=notice.id,
                            channel="web_push",
                            target_key=str(subscription.id),
                            status="pending",
                        )
                    )
            else:
                session.add(
                    NotificationDelivery(
                        notification_id=notice.id,
                        channel="web_push",
                        target_key="none",
                        status="unavailable",
                        error_code=(
                            "not_registered" if channels.push_public_key else "not_configured"
                        ),
                    )
                )
        if only_channel == "email" and channels.email_configured:
            self._queue_email(session, notice)
        elif only_channel == "email":
            session.add(
                NotificationDelivery(
                    notification_id=notice.id,
                    channel="email",
                    target_key="none",
                    status="unavailable",
                    error_code="not_configured",
                )
            )

    def _dispatch(self, session, delivery, notice, current: datetime) -> None:
        try:
            if delivery.channel == "sink":
                pass
            elif delivery.channel == "web_push":
                subscription = session.get(PushSubscription, int(delivery.target_key))
                if subscription is None or subscription.invalidated_at:
                    self._permanent_failure(delivery, "invalid_subscription", current)
                    return
                self._send_web_push(subscription.endpoint, notice.id)
            elif delivery.channel == "email":
                self._send_email(session, notice)
            delivery.attempt_count += 1
            delivery.status = (
                "technically_confirmed" if delivery.channel in {"email", "sink"} else "pending"
            )
            delivery.technical_confirmed_at = (
                _timestamp(current) if delivery.status == "technically_confirmed" else None
            )
            delivery.next_attempt_at = (
                _timestamp(current + PUSH_CONFIRMATION_TIMEOUT)
                if delivery.channel == "web_push"
                else None
            )
            delivery.error_code = None
            delivery.updated_at = _timestamp(current)
        except urllib.error.HTTPError as error:
            if error.code in {404, 410}:
                subscription = session.get(PushSubscription, int(delivery.target_key))
                if subscription is not None:
                    subscription.invalidated_at = _timestamp(current)
                self._permanent_failure(delivery, "invalid_subscription", current)
            elif 400 <= error.code < 500:
                self._permanent_failure(delivery, "push_rejected", current)
            else:
                self._temporary_failure(delivery, "push_unavailable", current)
        except OSError, smtplib.SMTPException:
            self._temporary_failure(delivery, f"{delivery.channel}_unavailable", current)

    def _temporary_failure(self, delivery, code: str, current: datetime) -> None:
        delivery.attempt_count += 1
        if delivery.attempt_count >= MAX_DELIVERY_ATTEMPTS:
            self._permanent_failure(delivery, code, current, increment=False)
            return
        delivery.status = "temporarily_failed"
        delivery.error_code = code
        delivery.next_attempt_at = _timestamp(
            current + timedelta(minutes=2 ** (delivery.attempt_count - 1))
        )
        delivery.updated_at = _timestamp(current)

    @staticmethod
    def _permanent_failure(
        delivery, code: str, current: datetime, *, increment: bool = True
    ) -> None:
        if increment:
            delivery.attempt_count += 1
        delivery.status = "permanently_failed"
        delivery.error_code = code
        delivery.next_attempt_at = None
        delivery.updated_at = _timestamp(current)

    def _queue_email_fallbacks(self, session, current: datetime) -> None:
        if not self.channels().email_configured:
            return
        candidates = session.scalars(
            select(NotificationDelivery).where(NotificationDelivery.channel == "web_push")
        ).all()
        for push in candidates:
            timed_out = (
                push.status == "pending"
                and push.next_attempt_at is not None
                and self._parse_timestamp(push.next_attempt_at) <= current
            )
            if push.status == "permanently_failed" or timed_out:
                notice = session.get(Notification, push.notification_id)
                if notice is not None:
                    self._queue_email(session, notice)

    @staticmethod
    def _queue_email(session, notice: Notification) -> None:
        existing = session.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notice.id,
                NotificationDelivery.channel == "email",
            )
        ).first()
        if existing is None:
            session.add(
                NotificationDelivery(
                    notification_id=notice.id,
                    channel="email",
                    target_key=f"member:{notice.recipient_member_id}",
                    status="pending",
                )
            )

    def _send_web_push(self, endpoint: str, notification_id: int) -> None:
        private_key = self._vapid_private_key()
        if private_key is None:
            raise OSError("Web Push is not configured")
        audience_parts = urlsplit(endpoint)
        audience = f"{audience_parts.scheme}://{audience_parts.netloc}"
        now = int(_now().timestamp())
        header = _base64url(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
        claims = _base64url(
            json.dumps(
                {
                    "aud": audience,
                    "exp": now + 12 * 60 * 60,
                    "sub": self._vapid_subject() or "",
                },
                separators=(",", ":"),
            ).encode()
        )
        signed = f"{header}.{claims}".encode("ascii")
        der_signature = private_key.sign(signed, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_signature)
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        token = f"{header}.{claims}.{_base64url(signature)}"
        public_key = self._push_public_key()
        request = urllib.request.Request(endpoint, method="POST", data=b"")
        request.add_header("Authorization", f"vapid t={token}, k={public_key}")
        request.add_header("TTL", "300")
        request.add_header("Urgency", "normal")
        request.add_header("Topic", _base64url(f"lzug-{notification_id}".encode())[:32])
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status not in {201, 202}:
                raise OSError("Web Push endpoint rejected request")

    def _send_email(self, session, notice: Notification) -> None:
        member = session.get(CommitteeMember, notice.recipient_member_id)
        person = session.get(Person, member.person_id) if member is not None else None
        if person is None:
            raise OSError("Recipient is unavailable")
        message = EmailMessage()
        message["Subject"] = notice.title
        message["From"] = os.environ.get("LZUG_SMTP_FROM", "lzug@localhost")
        message["To"] = person.email
        base_url = os.environ.get("LZUG_EXTERNAL_URL", "").rstrip("/")
        message.set_content(f"{notice.message}\n\n{base_url}{notice.action_path}")
        host = os.environ["LZUG_SMTP_HOST"]
        port = int(os.environ.get("LZUG_SMTP_PORT", "25"))
        with smtplib.SMTP(host, port, timeout=10) as client:
            if os.environ.get("LZUG_SMTP_STARTTLS", "").lower() in {"1", "true"}:
                client.starttls()
            username = os.environ.get("LZUG_SMTP_USERNAME")
            password = os.environ.get("LZUG_SMTP_PASSWORD")
            if username and password:
                client.login(username, password)
            client.send_message(message)

    def _vapid_private_key(self):
        value = os.environ.get("LZUG_WEB_PUSH_VAPID_PRIVATE_KEY")
        if not value:
            return None
        try:
            key = serialization.load_pem_private_key(value.replace("\\n", "\n").encode(), None)
        except ValueError as error:
            raise NotificationError("Invalid Web Push VAPID private key") from error
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(
            key.curve, ec.SECP256R1
        ):
            raise NotificationError("Web Push VAPID key must use P-256")
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

    @staticmethod
    def _vapid_subject() -> str | None:
        value = os.environ.get("LZUG_WEB_PUSH_SUBJECT", "").strip()
        if not value:
            return None
        parsed = urlsplit(value)
        if value.startswith("mailto:") and "@" in value.removeprefix("mailto:"):
            return value
        if parsed.scheme == "https" and parsed.netloc:
            return value
        raise NotificationError("Web Push subject must be a mailto or HTTPS URI")

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _now(parsed)

    @staticmethod
    def _notification_view(row: Notification) -> dict[str, object]:
        return {
            "id": row.id,
            "event_type": row.event_type,
            "title": row.title,
            "message": row.message,
            "action_path": row.action_path,
            "created_at": row.created_at,
        }

    @staticmethod
    def _delivery_diagnostic(row: NotificationDelivery) -> dict[str, object]:
        return {
            "channel": row.channel,
            "status": row.status,
            "attempt_count": row.attempt_count,
            "error_code": row.error_code,
        }
