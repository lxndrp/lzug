"""SQLite claim Unit of Work for notification delivery."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from backend.notifications.delivery import (
    DELIVERY_CLAIM_TTL_SECONDS,
    ClaimedDelivery,
    DeliveryResult,
)
from backend.notifications.repository import (
    AvailabilityResponse,
    DeliveryAttempt,
    DeliveryDiagnostic,
    DeliveryFallbackCandidate,
    NoticeDraft,
    NoticeWrite,
    NotificationMember,
    NotificationRound,
    OwnNotification,
    PlanChangeNotice,
    PlanRevision,
    PushSubscriptionSnapshot,
    ScheduleLine,
    SyntheticMember,
)
from backend.persistence.database import DEFAULT_DB_PATH, session_scope
from backend.persistence.models import (
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

if TYPE_CHECKING:
    from backend.notifications.repository import (
        NotificationDeliveryUnitOfWork,
        NotificationUnitOfWork,
    )


def _timestamp(value: datetime) -> str:
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat(timespec="seconds")


class SQLiteNotificationDeliveryUnitOfWorkFactory:
    """Create a distinct SQLite transaction for one claim transition."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path

    def __call__(self) -> AbstractContextManager[NotificationDeliveryUnitOfWork]:
        return self._unit_of_work()

    @contextmanager
    def _unit_of_work(self) -> Iterator[NotificationDeliveryUnitOfWork]:
        with session_scope(self.db_path) as session:
            yield SQLiteNotificationDeliveryUnitOfWork(session)


class SQLiteNotificationDeliveryUnitOfWork:
    """Claim and finalize deliveries with token and lease fencing."""

    def __init__(self, session) -> None:
        self._session = session

    def claim_due(
        self,
        current: datetime,
        claim_token: str,
        *,
        batch_size: int,
    ) -> list[ClaimedDelivery]:
        current_timestamp = _timestamp(current)
        expires_at = _timestamp(current + timedelta(seconds=DELIVERY_CLAIM_TTL_SECONDS))
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
        claimed_ids = list(
            self._session.scalars(
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
        rows = self._session.execute(
            select(NotificationDelivery, Notification)
            .join(Notification, Notification.id == NotificationDelivery.notification_id)
            .where(
                NotificationDelivery.id.in_(claimed_ids),
                NotificationDelivery.claim_token == claim_token,
            )
            .order_by(NotificationDelivery.id)
        ).all()
        snapshots = []
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
                    self._session.get(PushSubscription, subscription_id)
                    if subscription_id is not None
                    else None
                )
                if subscription is not None and subscription.invalidated_at is None:
                    push_endpoint = subscription.endpoint
            elif delivery.channel == "email":
                member = self._session.get(CommitteeMember, notice.recipient_member_id)
                person = self._session.get(Person, member.person_id) if member is not None else None
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

    def complete_claim(
        self,
        claimed: ClaimedDelivery,
        result: DeliveryResult,
        completed_at: datetime,
    ) -> bool:
        completed_timestamp = _timestamp(completed_at)
        delivery = self._session.scalar(
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
            subscription = self._session.get(PushSubscription, result.invalidate_subscription_id)
            if subscription is not None:
                subscription.invalidated_at = completed_timestamp
        return True


class SQLiteNotificationUnitOfWorkFactory:
    """Create short SQLite UoWs for notification content and delivery storage."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path

    def __call__(
        self, *, begin_immediate: bool = False
    ) -> AbstractContextManager[NotificationUnitOfWork]:
        return self._unit_of_work(begin_immediate=begin_immediate)

    @contextmanager
    def _unit_of_work(self, *, begin_immediate: bool = False) -> Iterator[NotificationUnitOfWork]:
        with session_scope(self.db_path, begin_immediate=begin_immediate) as session:
            yield SQLiteNotificationUnitOfWork(session)


class SQLiteNotificationUnitOfWork:
    """Translate typed notification queries and writes to existing SQLite tables."""

    def __init__(self, session) -> None:
        self._session = session

    @staticmethod
    def _round(row: ExamRound) -> NotificationRound:
        return NotificationRound(
            id=row.id,
            committee_id=row.committee_id,
            status=row.status,
            availability_deadline=row.availability_deadline,
            availability_reminder_at=row.availability_reminder_at,
        )

    def round(self, round_id: int) -> NotificationRound | None:
        row = self._session.get(ExamRound, round_id)
        return self._round(row) if row is not None else None

    def due_rounds(self) -> tuple[NotificationRound, ...]:
        rows = self._session.scalars(
            select(ExamRound).where(ExamRound.status == "availability_requested")
        ).all()
        return tuple(self._round(row) for row in rows)

    def active_members(self, committee_id: int) -> tuple[NotificationMember, ...]:
        rows = self._session.scalars(
            select(CommitteeMember).where(
                CommitteeMember.committee_id == committee_id,
                CommitteeMember.is_active == 1,
            )
        ).all()
        return tuple(
            NotificationMember(
                id=row.id,
                person_id=row.person_id,
                committee_role=row.committee_role,
                is_active=bool(row.is_active),
                committee_id=row.committee_id,
            )
            for row in rows
        )

    def availability_responses(self, round_id: int) -> tuple[AvailabilityResponse, ...]:
        rows = self._session.scalars(
            select(MemberAvailability).where(MemberAvailability.exam_round_id == round_id)
        ).all()
        return tuple(
            AvailabilityResponse(
                member_id=row.committee_member_id,
                responded_at=row.responded_at,
                availability=row.availability,
            )
            for row in rows
        )

    def assigned_member_ids(self, round_id: int) -> tuple[int, ...]:
        rows = self._session.scalars(
            select(ExamDayAssignment.committee_member_id)
            .join(ExamDay, ExamDay.id == ExamDayAssignment.exam_day_id)
            .where(
                ExamDay.exam_round_id == round_id,
                ExamDayAssignment.assignment_role.in_({"examiner", "fallback"}),
            )
            .distinct()
        ).all()
        return tuple(int(member_id) for member_id in rows)

    def schedule_lines(self, round_id: int, member_id: int) -> tuple[ScheduleLine, ...]:
        rows = self._session.execute(
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
        return tuple(
            ScheduleLine(date=day.date, venue=venue.name, room=room.name)
            for day, venue, room in rows
        )

    def save_notice(self, draft: NoticeDraft) -> NoticeWrite:
        notification = Notification(
            committee_id=draft.committee_id,
            exam_round_id=draft.round_id,
            recipient_member_id=draft.recipient_member_id,
            event_type=draft.event_type,
            origin_key=draft.origin_key,
            title=draft.title,
            message=draft.message,
            action_path=draft.action_path,
        )
        try:
            with self._session.begin_nested():
                self._session.add(notification)
                self._session.flush()
        except IntegrityError:
            existing_id = self._session.scalar(
                select(Notification.id).where(
                    Notification.recipient_member_id == draft.recipient_member_id,
                    Notification.event_type == draft.event_type,
                    Notification.origin_key == draft.origin_key,
                )
            )
            if existing_id is None:
                raise
            return NoticeWrite(id=existing_id, created=False)
        return NoticeWrite(id=notification.id, created=True)

    def queue_deliveries(
        self,
        notification_id: int,
        recipient_member_id: int,
        channels: tuple[str | None, bool, bool],
        *,
        only_channel: str | None = None,
        urgent_email: bool = False,
    ) -> None:
        push_public_key, email_configured, sink_enabled = channels
        if sink_enabled:
            self._session.add(
                NotificationDelivery(
                    notification_id=notification_id,
                    channel="sink",
                    target_key="operator-sink",
                    status="pending",
                )
            )
            return
        if only_channel in {None, "web_push"}:
            member = self._session.get(CommitteeMember, recipient_member_id)
            subscriptions = self._session.scalars(
                select(PushSubscription).where(
                    PushSubscription.person_id == (member.person_id if member else -1),
                    PushSubscription.invalidated_at.is_(None),
                )
            ).all()
            if subscriptions and push_public_key:
                for subscription in subscriptions:
                    self._session.add(
                        NotificationDelivery(
                            notification_id=notification_id,
                            channel="web_push",
                            target_key=str(subscription.id),
                            status="pending",
                        )
                    )
            else:
                self._session.add(
                    NotificationDelivery(
                        notification_id=notification_id,
                        channel="web_push",
                        target_key="none",
                        status="unavailable",
                        error_code=("not_registered" if push_public_key else "not_configured"),
                    )
                )
        if only_channel == "email" and email_configured:
            self._queue_email(notification_id, recipient_member_id)
        elif only_channel == "email":
            self._session.add(
                NotificationDelivery(
                    notification_id=notification_id,
                    channel="email",
                    target_key="none",
                    status="unavailable",
                    error_code="not_configured",
                )
            )
        elif urgent_email:
            if email_configured:
                self._queue_email(notification_id, recipient_member_id)
            else:
                self._session.add(
                    NotificationDelivery(
                        notification_id=notification_id,
                        channel="email",
                        target_key="none",
                        status="unavailable",
                        error_code="not_configured",
                    )
                )

    def _queue_email(self, notification_id: int, recipient_member_id: int) -> None:
        existing = self._session.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification_id,
                NotificationDelivery.channel == "email",
            )
        ).first()
        if existing is None:
            try:
                with self._session.begin_nested():
                    self._session.add(
                        NotificationDelivery(
                            notification_id=notification_id,
                            channel="email",
                            target_key=f"member:{recipient_member_id}",
                            status="pending",
                        )
                    )
                    self._session.flush()
            except IntegrityError:
                pass

    def problem_count(self, notification_ids: tuple[int, ...]) -> int:
        if not notification_ids:
            return 0
        return int(
            self._session.scalar(
                select(func.count(NotificationDelivery.id)).where(
                    NotificationDelivery.notification_id.in_(notification_ids),
                    NotificationDelivery.status.in_(
                        {"temporarily_failed", "permanently_failed", "unavailable"}
                    ),
                )
            )
            or 0
        )

    def own_notifications(self, member_ids: tuple[int, ...]) -> tuple[OwnNotification, ...]:
        if not member_ids:
            return ()
        rows = self._session.scalars(
            select(Notification)
            .where(
                Notification.recipient_member_id.in_(member_ids),
                Notification.superseded_at.is_(None),
            )
            .order_by(Notification.created_at.desc(), Notification.id.desc())
        ).all()
        return tuple(
            OwnNotification(
                id=row.id,
                event_type=row.event_type,
                title=row.title,
                message=row.message,
                action_path=row.action_path,
                created_at=row.created_at,
            )
            for row in rows
        )

    def delivery_diagnostics(
        self, committee_ids: tuple[int, ...], *, problems_only: bool
    ) -> tuple[DeliveryDiagnostic, ...]:
        if not committee_ids:
            return ()
        statement = (
            select(NotificationDelivery, Notification)
            .join(Notification, Notification.id == NotificationDelivery.notification_id)
            .where(Notification.committee_id.in_(committee_ids))
        )
        if problems_only:
            statement = statement.where(
                NotificationDelivery.status.in_(
                    {"temporarily_failed", "permanently_failed", "unavailable"}
                ),
                NotificationDelivery.error_code != "superseded_by_newer_revision",
            )
        rows = self._session.execute(
            statement.order_by(NotificationDelivery.updated_at.desc())
        ).all()
        return tuple(
            DeliveryDiagnostic(
                notification_id=notice.id,
                event_type=notice.event_type,
                recipient_member_id=notice.recipient_member_id,
                channel=delivery.channel,
                status=delivery.status,
                attempt_count=delivery.attempt_count,
                error_code=delivery.error_code,
                claim_token=delivery.claim_token,
                claimed_at=delivery.claimed_at,
                claim_expires_at=delivery.claim_expires_at,
                updated_at=delivery.updated_at,
            )
            for delivery, notice in rows
        )

    def plan_change_notices(
        self, round_id: int, recipient_member_id: int, newer_revision_id: int
    ) -> tuple[PlanChangeNotice, ...]:
        rows = self._session.scalars(
            select(Notification).where(
                Notification.exam_round_id == round_id,
                Notification.recipient_member_id == recipient_member_id,
                Notification.event_type == "plan_changed",
                Notification.origin_key
                != f"confirmed-plan-revision:{newer_revision_id}:{recipient_member_id}",
                Notification.superseded_at.is_(None),
            )
        ).all()
        return tuple(PlanChangeNotice(id=row.id, origin_key=row.origin_key) for row in rows)

    def plan_revision(self, revision_id: int) -> PlanRevision | None:
        row = self._session.get(ConfirmedPlanRevision, revision_id)
        if row is None:
            return None
        return PlanRevision(
            id=row.id,
            round_id=row.exam_round_id,
            resulting_revision=row.resulting_revision,
        )

    def delivery_attempts(self, notification_id: int) -> tuple[DeliveryAttempt, ...]:
        rows = self._session.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification_id
            )
        ).all()
        return tuple(
            DeliveryAttempt(
                attempt_count=row.attempt_count,
                technical_confirmed_at=row.technical_confirmed_at,
                claim_token=row.claim_token,
            )
            for row in rows
        )

    def supersede_plan_change(self, notification_id: int, newer_revision_id: int, at: str) -> None:
        notice = self._session.get(Notification, notification_id)
        if notice is None:
            return
        notice.superseded_at = at
        notice.superseded_by_revision_id = newer_revision_id
        deliveries = self._session.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification_id
            )
        ).all()
        for delivery in deliveries:
            delivery.status = "permanently_failed"
            delivery.next_attempt_at = None
            delivery.error_code = "superseded_by_newer_revision"
            delivery.updated_at = at

    def push_subscription_by_endpoint(self, endpoint: str) -> PushSubscriptionSnapshot | None:
        row = self._session.scalars(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        ).first()
        if row is None:
            return None
        return PushSubscriptionSnapshot(
            id=row.id,
            person_id=row.person_id,
            active=row.invalidated_at is None,
        )

    def add_push_subscription(self, person_id: int, endpoint: str, at: str) -> int:
        row = PushSubscription(
            person_id=person_id,
            endpoint=endpoint,
            created_at=at,
            updated_at=at,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def reactivate_push_subscription(self, subscription_id: int, at: str) -> None:
        row = self._session.get(PushSubscription, subscription_id)
        if row is not None:
            row.invalidated_at = None
            row.updated_at = at

    def push_subscription(self, subscription_id: int) -> PushSubscriptionSnapshot | None:
        row = self._session.get(PushSubscription, subscription_id)
        if row is None:
            return None
        return PushSubscriptionSnapshot(
            id=row.id,
            person_id=row.person_id,
            active=row.invalidated_at is None,
        )

    def invalidate_push_subscription(self, subscription_id: int, at: str) -> None:
        row = self._session.get(PushSubscription, subscription_id)
        if row is not None:
            row.invalidated_at = at

    def confirm_push_deliveries(
        self, notification_id: int, member_ids: tuple[int, ...], at: str
    ) -> bool:
        if not member_ids:
            return False
        notification = self._session.get(Notification, notification_id)
        if notification is None or notification.recipient_member_id not in member_ids:
            return False
        rows = self._session.scalars(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification_id,
                NotificationDelivery.channel == "web_push",
                NotificationDelivery.status == "pending",
            )
        ).all()
        for row in rows:
            row.status = "technically_confirmed"
            row.technical_confirmed_at = at
            row.claim_token = None
            row.claimed_at = None
            row.claim_expires_at = None
            row.updated_at = at
        return bool(rows)

    def synthetic_member(self, member_id: int) -> SyntheticMember | None:
        row = self._session.get(CommitteeMember, member_id)
        if row is None:
            return None
        return SyntheticMember(
            id=row.id,
            committee_id=row.committee_id,
            active=bool(row.is_active),
        )

    def delivery_diagnostics_for_notice(
        self, notification_id: int
    ) -> tuple[DeliveryDiagnostic, ...]:
        rows = self._session.execute(
            select(NotificationDelivery, Notification)
            .join(Notification, Notification.id == NotificationDelivery.notification_id)
            .where(Notification.id == notification_id)
            .order_by(NotificationDelivery.id)
        ).all()
        return tuple(
            DeliveryDiagnostic(
                notification_id=notice.id,
                event_type=notice.event_type,
                recipient_member_id=notice.recipient_member_id,
                channel=delivery.channel,
                status=delivery.status,
                attempt_count=delivery.attempt_count,
                error_code=delivery.error_code,
                claim_token=delivery.claim_token,
                claimed_at=delivery.claimed_at,
                claim_expires_at=delivery.claim_expires_at,
                updated_at=delivery.updated_at,
            )
            for delivery, notice in rows
        )

    def delivery_fallback_candidates(self) -> tuple[DeliveryFallbackCandidate, ...]:
        rows = self._session.execute(
            select(NotificationDelivery, Notification)
            .join(Notification, Notification.id == NotificationDelivery.notification_id)
            .where(
                NotificationDelivery.channel == "web_push",
                NotificationDelivery.claim_token.is_(None),
            )
        ).all()
        return tuple(
            DeliveryFallbackCandidate(
                notification_id=notice.id,
                recipient_member_id=notice.recipient_member_id,
                status=delivery.status,
                next_attempt_at=delivery.next_attempt_at,
                claim_token=delivery.claim_token,
            )
            for delivery, notice in rows
        )

    def queue_email(self, notification_id: int, recipient_member_id: int) -> None:
        self._queue_email(notification_id, recipient_member_id)
