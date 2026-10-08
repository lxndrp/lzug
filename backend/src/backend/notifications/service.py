"""Channel-neutral notifications and best-effort technical delivery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

from backend.notifications.delivery import (
    DELIVERY_CLAIM_TTL_SECONDS,
    ClaimedDelivery,
    DeliveryEnvelope,
    DeliveryGateway,
    DeliveryResult,
    ProviderOutcome,
    ProviderOutcomeKind,
)
from backend.notifications.repository import (
    AvailabilityResponse,
    DeliveryDiagnostic,
    NoticeDraft,
    NotificationDeliveryUnitOfWorkFactory,
    NotificationRound,
    NotificationScope,
    NotificationUnitOfWork,
    NotificationUnitOfWorkFactory,
    PlanChangeNotice,
    PlanRevision,
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
DELIVERY_BATCH_SIZE = 20
DELIVERY_CLAIM_TTL = timedelta(seconds=DELIVERY_CLAIM_TTL_SECONDS)


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


class NotificationService:
    """Persist domain notices once and process optional channels independently."""

    def __init__(
        self,
        *,
        external_delivery_enabled: bool = True,
        delivery_gateway: DeliveryGateway | None = None,
        delivery_unit_of_work_factory: NotificationDeliveryUnitOfWorkFactory,
        notification_unit_of_work_factory: NotificationUnitOfWorkFactory,
    ):
        self.external_delivery_enabled = external_delivery_enabled
        if delivery_gateway is None:
            raise ValueError("A notification delivery gateway is required")
        self.delivery_gateway = delivery_gateway
        self._delivery_unit_of_work_factory = delivery_unit_of_work_factory
        self._notification_unit_of_work_factory = notification_unit_of_work_factory

    def _channel_configuration(self) -> tuple[str | None, bool, bool]:
        if not self.external_delivery_enabled:
            return None, False, False
        channels = self.channels()
        return channels.push_public_key, channels.email_configured, channels.sink_enabled

    def _delivery_gateway(self) -> DeliveryGateway:
        return self.delivery_gateway

    def channels(self) -> NotificationChannels:
        if not self.external_delivery_enabled:
            return NotificationChannels(None, False, False)
        public_key, email_configured, sink_enabled = self._delivery_gateway().channels()
        return NotificationChannels(
            push_public_key=public_key,
            email_configured=email_configured,
            sink_enabled=sink_enabled,
        )

    def create_for_event(self, event_type: str, round_id: int) -> dict[str, int]:
        """Create at most one notice per eligible recipient and event origin."""
        with self._notification_unit_of_work_factory() as unit_of_work:
            exam_round = unit_of_work.round(round_id)
            if exam_round is None:
                raise NotificationError("Exam round not found")
            recipients = self._recipients(unit_of_work, event_type, exam_round)
            created = 0
            notification_ids: list[int] = []
            for member_id in sorted(recipients):
                title, message, action_path = self._content(
                    unit_of_work, event_type, exam_round, member_id
                )
                write = unit_of_work.save_notice(
                    NoticeDraft(
                        committee_id=exam_round.committee_id,
                        round_id=exam_round.id,
                        recipient_member_id=member_id,
                        event_type=event_type,
                        origin_key=f"exam-round:{exam_round.id}",
                        title=title,
                        message=message,
                        action_path=action_path,
                    )
                )
                notification_ids.append(write.id)
                if write.created:
                    created += 1
                    if self.external_delivery_enabled:
                        unit_of_work.queue_deliveries(
                            write.id, member_id, self._channel_configuration()
                        )
        dispatched = self.process_deliveries()
        with self._notification_unit_of_work_factory() as unit_of_work:
            problems = unit_of_work.problem_count(tuple(notification_ids))
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
        with self._notification_unit_of_work_factory() as unit_of_work:
            for member_id in sorted(recipient_member_ids):
                write = unit_of_work.save_notice(
                    NoticeDraft(
                        committee_id=committee_id,
                        round_id=round_id,
                        recipient_member_id=member_id,
                        event_type=event_type,
                        origin_key=f"{origin_key}:{member_id}",
                        title=title,
                        message=message,
                        action_path=action_path,
                    )
                )
                created_ids.append(write.id)
                if write.created and self.external_delivery_enabled:
                    unit_of_work.queue_deliveries(
                        write.id,
                        member_id,
                        self._channel_configuration(),
                        urgent_email=urgent,
                    )
        self.process_deliveries()
        return len(created_ids)

    def create_direct_if_current(
        self,
        *,
        is_current: Callable[[], bool],
        committee_id: int,
        round_id: int | None,
        recipient_member_id: int,
        event_type: str,
        title: str,
        message: str,
        action_path: str,
        origin_key: str,
    ) -> bool:
        """Persist a targeted notice only while its source still matches.

        The read-only guard runs under SQLite write intent so a concurrent
        domain write cannot commit between source validation and notice
        persistence. It must not perform writes or external effects.
        """
        with self._notification_unit_of_work_factory(begin_immediate=True) as unit_of_work:
            if not is_current():
                return False
            write = unit_of_work.save_notice(
                NoticeDraft(
                    committee_id=committee_id,
                    round_id=round_id,
                    recipient_member_id=recipient_member_id,
                    event_type=event_type,
                    origin_key=f"{origin_key}:{recipient_member_id}",
                    title=title,
                    message=message,
                    action_path=action_path,
                )
            )
            if write.created and self.external_delivery_enabled:
                unit_of_work.queue_deliveries(
                    write.id,
                    recipient_member_id,
                    self._channel_configuration(),
                )
        self.process_deliveries()
        return True

    def create_plan_change(
        self,
        *,
        committee_id: int,
        round_id: int,
        recipient_member_id: int,
        revision_id: int,
        title: str,
        message: str,
        action_path: str,
    ) -> tuple[bool, set[int]]:
        """Atomically accept recipient-relevant revisions and supersede older notices.

        The notification UoW factory serializes this read/write sequence. A
        worker that resumes after a newer notice for this recipient therefore
        cannot insert an older notice after it.
        """
        superseded_revision_ids: set[int] = set()
        accepted = False
        with self._notification_unit_of_work_factory(begin_immediate=True) as unit_of_work:
            revision = unit_of_work.plan_revision(revision_id)
            if revision is not None and revision.round_id == round_id:
                superseded = self._supersede_unsent_plan_changes(
                    unit_of_work,
                    round_id=round_id,
                    recipient_member_id=recipient_member_id,
                    newer_revision_id=revision_id,
                )
                if superseded is not None:
                    superseded_revision_ids = superseded
                    write = unit_of_work.save_notice(
                        NoticeDraft(
                            committee_id=committee_id,
                            round_id=round_id,
                            recipient_member_id=recipient_member_id,
                            event_type="plan_changed",
                            origin_key=f"confirmed-plan-revision:{revision_id}:{recipient_member_id}",
                            title=title,
                            message=message,
                            action_path=action_path,
                        )
                    )
                    if write.created and self.external_delivery_enabled:
                        unit_of_work.queue_deliveries(
                            write.id,
                            recipient_member_id,
                            self._channel_configuration(),
                        )
                    accepted = True
        if accepted:
            self.process_deliveries()
        return accepted, superseded_revision_ids

    def process_due_events(self, *, now: datetime | None = None) -> dict[str, int]:
        current = _now(now)
        created = 0
        with self._notification_unit_of_work_factory() as unit_of_work:
            rounds = unit_of_work.due_rounds()
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

    def list_own(self, scope: NotificationScope) -> list[dict[str, object]]:
        if not scope.member_ids:
            return []
        with self._notification_unit_of_work_factory() as unit_of_work:
            rows = unit_of_work.own_notifications(tuple(sorted(scope.member_ids)))
            return [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "title": row.title,
                    "message": row.message,
                    "action_path": row.action_path,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def problems(self, scope: NotificationScope) -> list[dict[str, object]]:
        return self._management_deliveries(scope, problems_only=True)

    def management_overview(self, scope: NotificationScope) -> list[dict[str, object]]:
        """Return content-free delivery metadata for committees managed by the actor."""
        return self._management_deliveries(scope, problems_only=False)

    def _management_deliveries(
        self, scope: NotificationScope, *, problems_only: bool
    ) -> list[dict[str, object]]:
        if not scope.management_committee_ids:
            return []
        with self._notification_unit_of_work_factory() as unit_of_work:
            rows = unit_of_work.delivery_diagnostics(
                tuple(sorted(scope.management_committee_ids)),
                problems_only=problems_only,
            )
            current = _now()
            return [
                {
                    "notification_id": row.notification_id,
                    "event_type": row.event_type,
                    "recipient_member_id": row.recipient_member_id,
                    "channel": row.channel,
                    "status": row.status,
                    "attempt_count": row.attempt_count,
                    "error_code": row.error_code,
                    "claim_state": self._claim_state(row, current),
                    "claimed_at": row.claimed_at,
                    "claim_expires_at": row.claim_expires_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]

    @staticmethod
    def _supersede_unsent_plan_changes(
        unit_of_work: NotificationUnitOfWork,
        *,
        round_id: int,
        recipient_member_id: int,
        newer_revision_id: int,
    ) -> set[int] | None:
        superseded_revision_ids: set[int] = set()
        current = _timestamp(_now())
        newer_revision = unit_of_work.plan_revision(newer_revision_id)
        if newer_revision is None:
            return None
        notices = unit_of_work.plan_change_notices(round_id, recipient_member_id, newer_revision_id)
        notice_revisions: list[tuple[PlanChangeNotice, PlanRevision]] = []
        for notice in notices:
            parts = notice.origin_key.split(":")
            if len(parts) < 3 or parts[0] != "confirmed-plan-revision":
                continue
            try:
                notice_revision_id = int(parts[1])
            except ValueError:
                continue
            notice_revision = unit_of_work.plan_revision(notice_revision_id)
            if notice_revision is None or notice_revision.round_id != newer_revision.round_id:
                continue
            if notice_revision.resulting_revision > newer_revision.resulting_revision:
                return None
            notice_revisions.append((notice, notice_revision))

        for notice, notice_revision in notice_revisions:
            if notice_revision.resulting_revision >= newer_revision.resulting_revision:
                continue
            attempted = any(
                delivery.attempt_count > 0
                or delivery.technical_confirmed_at is not None
                or delivery.claim_token is not None
                for delivery in unit_of_work.delivery_attempts(notice.id)
            )
            if attempted:
                continue
            unit_of_work.supersede_plan_change(notice.id, newer_revision_id, current)
            superseded_revision_ids.add(notice_revision_id)
        return superseded_revision_ids

    def register_push(self, scope: NotificationScope, endpoint: str) -> dict[str, object]:
        if scope.person_id is None:
            raise ValueError("An active person is required")
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or len(endpoint) > 2048:
            raise ValueError("A valid HTTPS push endpoint is required")
        with self._notification_unit_of_work_factory() as unit_of_work:
            existing = unit_of_work.push_subscription_by_endpoint(endpoint)
            if existing is not None:
                if existing.person_id != scope.person_id:
                    raise ValueError("Push endpoint is already registered")
                unit_of_work.reactivate_push_subscription(existing.id, _timestamp(_now()))
                subscription_id = existing.id
                active = True
            else:
                subscription_id = unit_of_work.add_push_subscription(
                    scope.person_id, endpoint, _timestamp(_now())
                )
                active = True
            return {"id": subscription_id, "active": active}

    def unregister_push(self, scope: NotificationScope, subscription_id: int) -> bool:
        with self._notification_unit_of_work_factory() as unit_of_work:
            row = unit_of_work.push_subscription(subscription_id)
            if row is None or row.person_id != scope.person_id:
                return False
            unit_of_work.invalidate_push_subscription(subscription_id, _timestamp(_now()))
            return True

    def confirm_push(self, scope: NotificationScope, notification_id: int) -> bool:
        with self._notification_unit_of_work_factory() as unit_of_work:
            return unit_of_work.confirm_push_deliveries(
                notification_id,
                tuple(sorted(scope.member_ids)),
                _timestamp(_now()),
            )

    def synthetic_test(self, member_id: int, channel: str) -> dict[str, object]:
        if channel not in {"web_push", "email"}:
            raise ValueError("Channel must be web_push or email")
        with self._notification_unit_of_work_factory() as unit_of_work:
            member = unit_of_work.synthetic_member(member_id)
            if member is None or not member.active:
                raise ValueError("Active committee member not found")
            origin = f"synthetic:{_timestamp(_now())}:{member_id}:{channel}"
            write = unit_of_work.save_notice(
                NoticeDraft(
                    committee_id=member.committee_id,
                    round_id=None,
                    recipient_member_id=member.id,
                    event_type="synthetic_test",
                    origin_key=origin,
                    title="Synthetischer Zustellungstest",
                    message="Diese Nachricht enthält keine echten Fachdaten.",
                    action_path="/notifications",
                )
            )
            notice_id = write.id
            if write.created and self.external_delivery_enabled:
                unit_of_work.queue_deliveries(
                    notice_id,
                    member.id,
                    self._channel_configuration(),
                    only_channel=channel,
                )
        self.process_deliveries()
        with self._notification_unit_of_work_factory() as unit_of_work:
            deliveries = unit_of_work.delivery_diagnostics_for_notice(notice_id)
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
        self._queue_email_fallbacks(fallback_time)
        return processed

    def _claim_due_deliveries(
        self,
        current: datetime,
        claim_token: str,
        *,
        batch_size: int = DELIVERY_BATCH_SIZE,
    ) -> list[ClaimedDelivery]:
        """Acquire and commit one bounded claim before returning its snapshot."""
        with self._delivery_unit_of_work_factory() as unit_of_work:
            return unit_of_work.claim_due(
                current,
                claim_token,
                batch_size=batch_size,
            )

    def _recipients(
        self, unit_of_work: NotificationUnitOfWork, event_type: str, exam_round: NotificationRound
    ) -> set[int]:
        active = unit_of_work.active_members(exam_round.committee_id)
        if event_type == "availability_requested":
            return {member.id for member in active}
        if event_type in {"availability_reminder", "availability_deadline_expired"}:
            availabilities = unit_of_work.availability_responses(exam_round.id)
            by_member: dict[int, list[AvailabilityResponse]] = {}
            for availability in availabilities:
                by_member.setdefault(availability.member_id, []).append(availability)
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
            return set(unit_of_work.assigned_member_ids(exam_round.id))
        raise NotificationError("Unknown notification event")

    def _content(
        self,
        unit_of_work: NotificationUnitOfWork,
        event_type: str,
        exam_round: NotificationRound,
        member_id: int,
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
                self._confirmed_schedule_message(
                    unit_of_work.schedule_lines(exam_round.id, member_id)
                ),
                f"/confirmed-plans/{exam_round.id}",
            ),
        }
        return content[event_type]

    @staticmethod
    def _confirmed_schedule_message(rows) -> str:
        appointments = list(dict.fromkeys(f"{row.date} – {row.venue}, {row.room}" for row in rows))
        return "Ihre Einsätze: " + "; ".join(appointments)

    def _dispatch_claimed(self, delivery: ClaimedDelivery, current: datetime) -> DeliveryResult:
        terminal = self._dispatch_precondition(delivery)
        if terminal is not None:
            return terminal
        outcome = self._send_claimed(delivery)
        if outcome.kind is ProviderOutcomeKind.SENT:
            return self._sent_result(delivery, current)
        if outcome.kind is ProviderOutcomeKind.INVALID_SUBSCRIPTION:
            return self._permanent_result(
                delivery,
                "invalid_subscription",
                invalidate_subscription_id=delivery.push_subscription_id,
            )
        if outcome.kind is ProviderOutcomeKind.PERMANENT_FAILURE:
            return self._permanent_result(delivery, outcome.error_code or "provider_rejected")
        return self._temporary_result(
            delivery,
            outcome.error_code or f"{delivery.channel}_unavailable",
            current,
        )

    def _dispatch_precondition(self, delivery: ClaimedDelivery) -> DeliveryResult | None:
        """Decide terminal push outcomes before accessing a provider."""
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
        if delivery.channel == "web_push" and delivery.push_endpoint is None:
            return self._permanent_result(delivery, "invalid_subscription")
        return None

    def _send_claimed(self, delivery: ClaimedDelivery) -> ProviderOutcome:
        """Perform channel I/O after the claim transaction has committed."""
        if delivery.channel == "sink":
            return self._send_sink(delivery.notification_id)
        if delivery.channel == "web_push":
            if delivery.push_endpoint is None:
                return ProviderOutcome(
                    ProviderOutcomeKind.INVALID_SUBSCRIPTION, "invalid_subscription"
                )
            return self._send_web_push(delivery.push_endpoint, delivery.notification_id)
        if delivery.channel == "email":
            if delivery.recipient_email is None:
                return ProviderOutcome(ProviderOutcomeKind.TEMPORARY_FAILURE, "email_unavailable")
            return self._send_email(delivery)
        return ProviderOutcome(ProviderOutcomeKind.UNAVAILABLE, "unsupported_channel")

    @staticmethod
    def _sent_result(delivery: ClaimedDelivery, current: datetime) -> DeliveryResult:
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
        """Persist a result through a new UoW while the claim lease is valid."""
        with self._delivery_unit_of_work_factory() as unit_of_work:
            return unit_of_work.complete_claim(claimed, result, completed_at)

    def _queue_email_fallbacks(self, current: datetime) -> None:
        if not self.channels().email_configured:
            return
        with self._notification_unit_of_work_factory() as unit_of_work:
            candidates = unit_of_work.delivery_fallback_candidates()
        recipients = set()
        for push in candidates:
            timed_out = (
                push.status == "pending"
                and push.next_attempt_at is not None
                and self._parse_timestamp(push.next_attempt_at) <= current
            )
            if push.status == "permanently_failed" or timed_out:
                recipients.add((push.notification_id, push.recipient_member_id))
        if recipients:
            with self._notification_unit_of_work_factory() as unit_of_work:
                for notification_id, recipient_member_id in sorted(recipients):
                    unit_of_work.queue_email(notification_id, recipient_member_id)

    def _send_sink(self, _notification_id: int) -> ProviderOutcome:
        """Compatibility hook used by provider doubles in focused tests."""
        return self._delivery_gateway().deliver(
            DeliveryEnvelope(
                notification_id=_notification_id,
                channel="sink",
                target=None,
                title="",
                message="",
                action_path="",
            )
        )

    def _send_web_push(self, endpoint: str, notification_id: int) -> ProviderOutcome:
        return self._delivery_gateway().deliver(
            DeliveryEnvelope(
                notification_id=notification_id,
                channel="web_push",
                target=endpoint,
                title="",
                message="",
                action_path="",
            )
        )

    def _send_email(self, delivery: ClaimedDelivery) -> ProviderOutcome:
        return self._delivery_gateway().deliver(
            DeliveryEnvelope(
                notification_id=delivery.notification_id,
                channel="email",
                target=delivery.recipient_email,
                title=delivery.title,
                message=delivery.message,
                action_path=delivery.action_path,
            )
        )

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _now(parsed)

    @classmethod
    def _delivery_diagnostic(cls, row: DeliveryDiagnostic) -> dict[str, object]:
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
    def _claim_state(cls, row: DeliveryDiagnostic, current: datetime) -> str:
        if row.claim_token is None:
            return "idle"
        if row.claim_expires_at is None:
            return "expired"
        return "active" if cls._parse_timestamp(row.claim_expires_at) > current else "expired"
