"""Channel-neutral notifications and best-effort technical delivery."""

from __future__ import annotations

import base64
import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import Vapid, WebPushException, webpush
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from .authorization import AuthorizationScope
from .database import DEFAULT_DB_PATH, session_scope
from .models import (
    CommitteeMember,
    ConfirmedPlanRevision,
    ExamDay,
    ExamDayAssignment,
    ExamRoom,
    ExamRound,
    ExamVenue,
    MemberAvailability,
    Notification,
    NotificationDelivery,
    Person,
    PushSubscription,
)
from .settings import NotificationSettings, RuntimeSettings

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
DELIVERY_BATCH_SIZE = 20
DELIVERY_CLAIM_TTL = timedelta(minutes=2)


class NotificationError(RuntimeError):
    """A safe notification failure that must not roll back the domain event."""


@dataclass(frozen=True)
class NotificationChannels:
    push_public_key: str | None
    email_configured: bool
    sink_enabled: bool


@dataclass(frozen=True)
class ClaimedDelivery:
    """Immutable channel input captured while the short claim transaction is open."""

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
    """Result written only if the corresponding claim is still current."""

    status: str
    attempt_count: int
    next_attempt_at: str | None
    technical_confirmed_at: str | None
    error_code: str | None
    invalidate_subscription_id: int | None = None


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _now(value).isoformat(timespec="seconds")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class NotificationService:
    """Persist domain notices once and process optional channels independently."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        external_delivery_enabled: bool = True,
        settings: RuntimeSettings | None = None,
    ):
        self.db_path = db_path
        self.external_delivery_enabled = external_delivery_enabled
        self.settings = settings

    def _runtime_settings(self) -> RuntimeSettings:
        return self.settings or RuntimeSettings.from_environment()

    def _notification_settings(self) -> NotificationSettings:
        return self._runtime_settings().notifications

    def channels(self) -> NotificationChannels:
        if not self.external_delivery_enabled:
            return NotificationChannels(None, False, False)
        settings = self._notification_settings()
        subject = self._vapid_subject()
        return NotificationChannels(
            push_public_key=self._push_public_key() if subject else None,
            email_configured=settings.smtp_host is not None,
            sink_enabled=settings.sink_enabled,
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
    ) -> int:
        """Persist one targeted domain notice and queue its technical channels.

        This is the shared notification boundary for workflows whose recipients
        are determined by a domain decision rather than by a whole round event.
        Urgent absence searches queue push and configured email independently so
        neither channel waits for the other.
        """
        created_ids: list[int] = []
        with session_scope(self.db_path) as session:
            for member_id in sorted(recipient_member_ids):
                notice = Notification(
                    committee_id=committee_id,
                    exam_round_id=round_id,
                    recipient_member_id=member_id,
                    event_type=event_type,
                    origin_key=f"{origin_key}:{member_id}",
                    title=title,
                    message=message,
                    action_path=action_path,
                )
                try:
                    with session.begin_nested():
                        session.add(notice)
                        session.flush()
                except IntegrityError:
                    existing = session.scalar(
                        select(Notification.id).where(
                            Notification.recipient_member_id == member_id,
                            Notification.event_type == event_type,
                            Notification.origin_key == f"{origin_key}:{member_id}",
                        )
                    )
                    if existing is not None:
                        created_ids.append(existing)
                    continue
                created_ids.append(notice.id)
                self._queue_deliveries(session, notice, urgent_email=urgent)
        self.process_deliveries()
        return len(created_ids)

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
                .where(
                    Notification.recipient_member_id.in_(scope.member_ids),
                    Notification.superseded_at.is_(None),
                )
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
                    ),
                    NotificationDelivery.error_code != "superseded_by_newer_revision",
                )
            rows = session.execute(statement.order_by(NotificationDelivery.updated_at.desc())).all()
            current = _now()
            return [
                {
                    "notification_id": notice.id,
                    "event_type": notice.event_type,
                    "recipient_member_id": notice.recipient_member_id,
                    "channel": delivery.channel,
                    "status": delivery.status,
                    "attempt_count": delivery.attempt_count,
                    "error_code": delivery.error_code,
                    "claim_state": self._claim_state(delivery, current),
                    "claimed_at": delivery.claimed_at,
                    "claim_expires_at": delivery.claim_expires_at,
                    "updated_at": delivery.updated_at,
                }
                for delivery, notice in rows
            ]

    def supersede_unsent_plan_changes(
        self,
        *,
        round_id: int,
        recipient_member_id: int,
        newer_revision_id: int,
    ) -> set[int]:
        """Hide only plan-change notices that no channel has attempted yet."""
        superseded: set[int] = set()
        current = _timestamp(_now())
        with session_scope(self.db_path) as session:
            notices = session.scalars(
                select(Notification).where(
                    Notification.exam_round_id == round_id,
                    Notification.recipient_member_id == recipient_member_id,
                    Notification.event_type == "plan_changed",
                    Notification.origin_key
                    != f"confirmed-plan-revision:{newer_revision_id}:{recipient_member_id}",
                    Notification.superseded_at.is_(None),
                )
            ).all()
            for notice in notices:
                parts = notice.origin_key.split(":")
                if len(parts) < 3 or parts[0] != "confirmed-plan-revision":
                    continue
                try:
                    notice_revision_id = int(parts[1])
                except ValueError:
                    continue
                notice_revision = session.get(ConfirmedPlanRevision, notice_revision_id)
                newer_revision = session.get(ConfirmedPlanRevision, newer_revision_id)
                if (
                    notice_revision is None
                    or newer_revision is None
                    or notice_revision.exam_round_id != newer_revision.exam_round_id
                    or notice_revision.resulting_revision >= newer_revision.resulting_revision
                ):
                    continue
                deliveries = session.scalars(
                    select(NotificationDelivery).where(
                        NotificationDelivery.notification_id == notice.id
                    )
                ).all()
                attempted = any(
                    delivery.attempt_count > 0
                    or delivery.technical_confirmed_at is not None
                    or delivery.claim_token is not None
                    for delivery in deliveries
                )
                if attempted:
                    continue
                notice.superseded_at = current
                notice.superseded_by_revision_id = newer_revision_id
                for delivery in deliveries:
                    delivery.status = "permanently_failed"
                    delivery.next_attempt_at = None
                    delivery.error_code = "superseded_by_newer_revision"
                    delivery.updated_at = current
                superseded.add(notice.id)
        return superseded

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
                row.claim_token = None
                row.claimed_at = None
                row.claim_expires_at = None
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
        if not self.external_delivery_enabled:
            return 0
        current = _now(now)
        processed = 0
        for _index in range(DELIVERY_BATCH_SIZE):
            claim_started = current if now is not None else _now()
            claimed = self._claim_due_deliveries(claim_started, uuid4().hex, batch_size=1)
            if not claimed:
                break
            delivery = claimed[0]
            result = self._dispatch_claimed(delivery, claim_started)
            completed_at = claim_started if now is not None else _now()
            if self._complete_claim(delivery, result, completed_at):
                processed += 1
        fallback_time = current if now is not None else _now()
        with session_scope(self.db_path) as session:
            self._queue_email_fallbacks(session, fallback_time)
        return processed

    def _claim_due_deliveries(
        self,
        current: datetime,
        claim_token: str,
        *,
        batch_size: int = DELIVERY_BATCH_SIZE,
    ) -> list[ClaimedDelivery]:
        """Atomically claim one bounded batch and capture its channel inputs."""
        current_timestamp = _timestamp(current)
        expires_at = _timestamp(current + DELIVERY_CLAIM_TTL)
        claim_available = or_(
            NotificationDelivery.claim_token.is_(None),
            NotificationDelivery.claim_expires_at.is_(None),
            NotificationDelivery.claim_expires_at <= current_timestamp,
        )
        candidates = (
            select(NotificationDelivery.id)
            .where(
                NotificationDelivery.status.in_({"pending", "temporarily_failed"}),
                or_(
                    NotificationDelivery.next_attempt_at.is_(None),
                    NotificationDelivery.next_attempt_at <= current_timestamp,
                ),
                claim_available,
            )
            .order_by(NotificationDelivery.id)
            .limit(batch_size)
        )
        with session_scope(self.db_path) as session:
            claimed_ids = list(
                session.scalars(
                    update(NotificationDelivery)
                    .where(NotificationDelivery.id.in_(candidates), claim_available)
                    .values(
                        claim_token=claim_token,
                        claimed_at=current_timestamp,
                        claim_expires_at=expires_at,
                    )
                    .returning(NotificationDelivery.id)
                    .execution_options(synchronize_session=False)
                ).all()
            )
            if not claimed_ids:
                return []
            rows = session.execute(
                select(NotificationDelivery, Notification)
                .join(Notification, Notification.id == NotificationDelivery.notification_id)
                .where(
                    NotificationDelivery.id.in_(claimed_ids),
                    NotificationDelivery.claim_token == claim_token,
                )
                .order_by(NotificationDelivery.id)
            ).all()
            snapshots: list[ClaimedDelivery] = []
            for delivery, notice in rows:
                subscription_id: int | None = None
                push_endpoint: str | None = None
                recipient_email: str | None = None
                if delivery.channel == "web_push":
                    try:
                        subscription_id = int(delivery.target_key)
                    except ValueError:
                        subscription_id = None
                    subscription = (
                        session.get(PushSubscription, subscription_id)
                        if subscription_id is not None
                        else None
                    )
                    if subscription is not None and subscription.invalidated_at is None:
                        push_endpoint = subscription.endpoint
                elif delivery.channel == "email":
                    member = session.get(CommitteeMember, notice.recipient_member_id)
                    person = session.get(Person, member.person_id) if member is not None else None
                    recipient_email = person.email if person is not None else None
                snapshots.append(
                    ClaimedDelivery(
                        id=delivery.id,
                        claim_token=claim_token,
                        notification_id=notice.id,
                        channel=delivery.channel,
                        status=delivery.status,
                        attempt_count=delivery.attempt_count,
                        push_subscription_id=subscription_id,
                        push_endpoint=push_endpoint,
                        recipient_email=recipient_email,
                        title=notice.title,
                        message=notice.message,
                        action_path=notice.action_path,
                    )
                )
            return snapshots

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
            select(ExamDay, ExamVenue, ExamRoom)
            .join(ExamDayAssignment, ExamDayAssignment.exam_day_id == ExamDay.id)
            .join(ExamRoom, ExamRoom.id == ExamDay.room_id)
            .join(ExamVenue, ExamVenue.id == ExamRoom.venue_id)
            .where(
                ExamDay.exam_round_id == round_id,
                ExamDayAssignment.committee_member_id == member_id,
            )
            .order_by(ExamDay.date, ExamVenue.name, ExamRoom.name)
        ).all()
        appointments = list(
            dict.fromkeys(f"{day.date} – {venue.name}, {room.name}" for day, venue, room in rows)
        )
        return "Ihre Einsätze: " + "; ".join(appointments)

    def _queue_deliveries(
        self,
        session,
        notice: Notification,
        *,
        only_channel: str | None = None,
        urgent_email: bool = False,
    ) -> None:
        if not self.external_delivery_enabled:
            return
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
        elif urgent_email:
            if channels.email_configured:
                self._queue_email(session, notice)
            else:
                session.add(
                    NotificationDelivery(
                        notification_id=notice.id,
                        channel="email",
                        target_key="none",
                        status="unavailable",
                        error_code="not_configured",
                    )
                )

    def _dispatch_claimed(self, delivery: ClaimedDelivery, current: datetime) -> DeliveryResult:
        if (
            delivery.channel == "web_push"
            and delivery.status == "pending"
            and delivery.attempt_count
        ):
            return self._permanent_result(
                delivery,
                "confirmation_timeout",
                increment=False,
            )
        try:
            if delivery.channel == "sink":
                self._send_sink(delivery.notification_id)
            elif delivery.channel == "web_push":
                if delivery.push_endpoint is None:
                    return self._permanent_result(delivery, "invalid_subscription")
                self._send_web_push(delivery.push_endpoint, delivery.notification_id)
            elif delivery.channel == "email":
                if delivery.recipient_email is None:
                    raise OSError("Recipient is unavailable")
                self._send_email(delivery)
            confirmed_status = (
                "technically_confirmed" if delivery.channel in {"email", "sink"} else "pending"
            )
            return DeliveryResult(
                status=confirmed_status,
                attempt_count=delivery.attempt_count + 1,
                next_attempt_at=(
                    _timestamp(current + PUSH_CONFIRMATION_TIMEOUT)
                    if delivery.channel == "web_push"
                    else None
                ),
                technical_confirmed_at=(
                    _timestamp(current) if confirmed_status == "technically_confirmed" else None
                ),
                error_code=None,
            )
        except WebPushException as error:
            if error.status_code in {404, 410}:
                return self._permanent_result(
                    delivery,
                    "invalid_subscription",
                    invalidate_subscription_id=delivery.push_subscription_id,
                )
            if error.status_code is not None and 400 <= error.status_code < 500:
                if error.status_code == 429:
                    return self._temporary_result(delivery, "push_unavailable", current)
                return self._permanent_result(delivery, "push_rejected")
            return self._temporary_result(delivery, "push_unavailable", current)
        except OSError, smtplib.SMTPException:
            return self._temporary_result(delivery, f"{delivery.channel}_unavailable", current)

    def _temporary_result(
        self, delivery: ClaimedDelivery, code: str, current: datetime
    ) -> DeliveryResult:
        attempt_count = delivery.attempt_count + 1
        if attempt_count >= MAX_DELIVERY_ATTEMPTS:
            return self._permanent_result(delivery, code, attempt_count=attempt_count)
        return DeliveryResult(
            status="temporarily_failed",
            attempt_count=attempt_count,
            next_attempt_at=_timestamp(current + timedelta(minutes=2 ** (attempt_count - 1))),
            technical_confirmed_at=None,
            error_code=code,
        )

    @staticmethod
    def _permanent_result(
        delivery: ClaimedDelivery,
        code: str,
        *,
        increment: bool = True,
        attempt_count: int | None = None,
        invalidate_subscription_id: int | None = None,
    ) -> DeliveryResult:
        return DeliveryResult(
            status="permanently_failed",
            attempt_count=(
                attempt_count
                if attempt_count is not None
                else delivery.attempt_count + (1 if increment else 0)
            ),
            next_attempt_at=None,
            technical_confirmed_at=None,
            error_code=code,
            invalidate_subscription_id=invalidate_subscription_id,
        )

    def _complete_claim(
        self,
        claimed: ClaimedDelivery,
        result: DeliveryResult,
        completed_at: datetime,
    ) -> bool:
        """Persist a result only while the exact claim token is still valid."""
        completed_timestamp = _timestamp(completed_at)
        with session_scope(self.db_path) as session:
            delivery = session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.id == claimed.id,
                    NotificationDelivery.claim_token == claimed.claim_token,
                    NotificationDelivery.claim_expires_at > completed_timestamp,
                )
            )
            if delivery is None:
                return False
            delivery.status = result.status
            delivery.attempt_count = result.attempt_count
            delivery.next_attempt_at = result.next_attempt_at
            delivery.technical_confirmed_at = result.technical_confirmed_at
            delivery.error_code = result.error_code
            delivery.claim_token = None
            delivery.claimed_at = None
            delivery.claim_expires_at = None
            delivery.updated_at = completed_timestamp
            if result.invalidate_subscription_id is not None:
                subscription = session.get(PushSubscription, result.invalidate_subscription_id)
                if subscription is not None:
                    subscription.invalidated_at = completed_timestamp
            return True

    def _queue_email_fallbacks(self, session, current: datetime) -> None:
        if not self.channels().email_configured:
            return
        candidates = session.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.channel == "web_push",
                NotificationDelivery.claim_token.is_(None),
            )
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
            try:
                with session.begin_nested():
                    session.add(
                        NotificationDelivery(
                            notification_id=notice.id,
                            channel="email",
                            target_key=f"member:{notice.recipient_member_id}",
                            status="pending",
                        )
                    )
                    session.flush()
            except IntegrityError:
                pass

    @staticmethod
    def _send_sink(_notification_id: int) -> None:
        """Record-only sink boundary, kept outside the claim transaction."""

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

    def _send_email(self, delivery: ClaimedDelivery) -> None:
        if delivery.recipient_email is None:
            raise OSError("Recipient is unavailable")
        settings = self._notification_settings()
        message = EmailMessage()
        message["Subject"] = delivery.title
        message["From"] = settings.smtp_from
        message["To"] = delivery.recipient_email
        base_url = (self._runtime_settings().integrations.external_url or "").rstrip("/")
        message.set_content(f"{delivery.message}\n\n{base_url}{delivery.action_path}")
        if settings.smtp_host is None:
            raise OSError("SMTP is not configured")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            if settings.smtp_starttls:
                client.starttls()
            username = settings.smtp_username
            password = settings.smtp_password_value
            if username and password:
                client.login(username, password)
            client.send_message(message)

    def _vapid_private_key(self):
        value = self._notification_settings().push_private_key
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

    def _vapid_subject(self) -> str | None:
        value = self._notification_settings().web_push_subject
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

    @classmethod
    def _delivery_diagnostic(cls, row: NotificationDelivery) -> dict[str, object]:
        return {
            "channel": row.channel,
            "status": row.status,
            "attempt_count": row.attempt_count,
            "error_code": row.error_code,
            "claim_state": cls._claim_state(row, _now()),
            "claimed_at": row.claimed_at,
            "claim_expires_at": row.claim_expires_at,
        }

    @classmethod
    def _claim_state(cls, row: NotificationDelivery, current: datetime) -> str:
        if row.claim_token is None:
            return "idle"
        if row.claim_expires_at is None:
            return "expired"
        return "active" if cls._parse_timestamp(row.claim_expires_at) > current else "expired"
