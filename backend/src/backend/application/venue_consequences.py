"""Reliable calendar and notification consequences of venue master-data changes."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from backend.application.calendar_ports import CalendarApplicationPort
from backend.application.consequence_ports import (
    ApplicationConsequenceStore,
    ConsequenceTaskDraft,
    NotificationApplicationPort,
    VenueConsequencePlanningPort,
)
from backend.planning.venue_consequences import VenueAuditConsequenceSource
from backend.planning_ports import VenueAuditEventSnapshot

MAX_CONSEQUENCE_ATTEMPTS = 4
CONSEQUENCE_CLAIM_LEASE = timedelta(minutes=5)


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return _now(value).isoformat(timespec="seconds")


class VenueConsequenceService:
    """Derive and retry independent effects from immutable venue audit events."""

    def __init__(
        self,
        *,
        notification_service: NotificationApplicationPort,
        calendar_service: CalendarApplicationPort,
        consequence_store: ApplicationConsequenceStore,
        venue_planner: VenueConsequencePlanningPort,
    ) -> None:
        self.notifications = notification_service
        self.calendar = calendar_service
        self.consequence_store = consequence_store
        self.venue_planner = venue_planner

    def preview(
        self,
        *,
        venue_id: int,
        entity_type: str,
        entity_id: int,
        before: dict[str, Any],
        after: dict[str, Any],
        meaningful_change: bool,
        today: date | None = None,
    ) -> dict[str, Any]:
        return self.venue_planner.preview(
            venue_id=venue_id,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            meaningful_change=meaningful_change,
            today=today,
        )

    def process_audit(self, audit_id: int, *, now: datetime | None = None) -> dict[str, Any]:
        current = _now(now)
        batch_id = self._derive(audit_id, current)
        self._supersede_stale(audit_id, current)
        self._process_tasks(batch_id, current)
        return self.summary(audit_id)

    def process_due(self, *, now: datetime | None = None) -> dict[str, int]:
        """Re-derive missing audit batches and resume due tasks after a crash."""
        current = _now(now)
        audit_ids: list[int] = []
        due_task_ids: set[int] = set()
        derivation_problems = 0
        for audit in self.venue_planner.consequence_audits():
            if self._audit_details(audit).get("consequence_version") != 1:
                continue
            audit_ids.append(audit.id)
            batch = self.consequence_store.batch_by_origin("exam_venue_audit_event", str(audit.id))
            try:
                batch_id = batch.id if batch is not None else self._derive(audit.id, current)
                due_task_ids.update(
                    self.consequence_store.due_task_ids(
                        origin_type="exam_venue_audit_event",
                        now=_timestamp(current),
                        batch_id=batch_id,
                    )
                )
                self._supersede_stale(audit.id, current)
                self._process_tasks(batch_id, current)
            except Exception:
                derivation_problems += 1
        batches = self.consequence_store.batches_by_origin("exam_venue_audit_event")
        failed_tasks = sum(
            task.status in {"temporarily_failed", "permanently_failed"}
            for batch in batches
            for task in self.consequence_store.tasks_for_batch(batch.id)
        )
        return {
            "audits": len(audit_ids),
            "processed": len(due_task_ids),
            "problems": derivation_problems + failed_tasks,
        }

    def retry_audit(self, audit_id: int) -> dict[str, Any]:
        current = _now()
        batch_id = self._derive(audit_id, current)
        tasks = self.consequence_store.tasks_for_batch(
            batch_id,
            statuses=frozenset({"temporarily_failed", "permanently_failed"}),
        )
        for task in tasks:
            self.consequence_store.set_task_state(
                task.id,
                status="pending",
                attempt_count=task.attempt_count,
                next_attempt_at=None,
                error_code=None,
                calendar_event_id=task.calendar_event_id,
                calendar_event_version=task.calendar_event_version,
                updated_at=_timestamp(current),
            )
        self._supersede_stale(audit_id, current)
        self._process_tasks(batch_id, current)
        return self.summary(audit_id)

    def problems_for_venue(self, venue_id: int) -> list[dict[str, Any]]:
        audits = self.venue_planner.audits_for_venue(venue_id)
        result: list[dict[str, Any]] = []
        for audit in audits:
            details = self._audit_details(audit)
            if details.get("consequence_version") != 1:
                continue
            batch = self.consequence_store.batch_by_origin("exam_venue_audit_event", str(audit.id))
            if batch is None:
                result.append(self._problem_view(audit, None, "derivation_missing"))
                continue
            for task in self.consequence_store.tasks_for_batch(batch.id):
                expired_claim = (
                    task.status == "pending"
                    and task.next_attempt_at is not None
                    and task.next_attempt_at <= _timestamp()
                )
                if task.status in {"temporarily_failed", "permanently_failed"}:
                    result.append(self._problem_view(audit, task, task.error_code))
                elif expired_claim:
                    result.append(self._problem_view(audit, task, "claim_expired"))
        return result

    def summary(self, audit_id: int) -> dict[str, Any]:
        batch = self.consequence_store.batch_by_origin("exam_venue_audit_event", str(audit_id))
        if batch is None:
            return {"audit_id": audit_id, "processed": 0, "problems": 1, "pending": 0}
        tasks = self.consequence_store.tasks_for_batch(batch.id)
        return {
            "audit_id": audit_id,
            "processed": sum(task.status == "succeeded" for task in tasks),
            "problems": sum(
                task.status in {"temporarily_failed", "permanently_failed"} for task in tasks
            ),
            "pending": sum(task.status == "pending" for task in tasks),
            "superseded": sum(task.status == "superseded" for task in tasks),
        }

    def _derive(self, audit_id: int, current: datetime) -> int:
        existing = self.consequence_store.batch_by_origin("exam_venue_audit_event", str(audit_id))
        if existing is not None and existing.status == "succeeded":
            return existing.id
        source = self.venue_planner.source_for_audit(audit_id, today=current.date())
        if source is None:
            raise ValueError("Venue change audit not found")
        audit = source.audit
        details = self._audit_details(audit)
        if details.get("consequence_version") != 1:
            raise ValueError("Venue change has no retryable consequence contract")
        task_drafts = tuple(ConsequenceTaskDraft(**task) for task in self._tasks(source))
        return self.consequence_store.record_batch(
            origin_type="exam_venue_audit_event",
            origin_key=str(audit_id),
            confirmed_plan_revision_id=None,
            notification_scope=(),
            tasks=task_drafts,
            error_code=None,
            now=_timestamp(current),
        )

    def _tasks(self, source: VenueAuditConsequenceSource) -> list[dict[str, Any]]:
        audit = source.audit
        descriptions = source.descriptions
        tasks: list[dict[str, Any]] = []
        for calendar_item in descriptions.calendar:
            tasks.append(
                {
                    "recipient_member_id": calendar_item.recipient_member_id,
                    "consequence_type": "calendar",
                    "action": "update",
                    "identity_key": f"assignment:{calendar_item.assignment_id}",
                    "details_json": json.dumps(
                        {
                            "audit_id": audit.id,
                            "venue_id": audit.venue_id,
                            "assignment_ids": [calendar_item.assignment_id],
                            "entity_type": calendar_item.entity_type,
                            "entity_id": calendar_item.entity_id,
                            "expected_signature": dict(calendar_item.expected_signature),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )
        for notification_item in descriptions.notifications:
            tasks.append(
                {
                    "recipient_member_id": notification_item.recipient_member_id,
                    "consequence_type": "notification",
                    "action": "notify",
                    "identity_key": (
                        f"member:{notification_item.recipient_member_id}:committee:{notification_item.committee_id}"
                    ),
                    "details_json": json.dumps(
                        {
                            "audit_id": audit.id,
                            "assignment_ids": list(notification_item.assignment_ids),
                            "committee_id": notification_item.committee_id,
                            "venue_id": notification_item.venue_id,
                            "entity_type": notification_item.entity_type,
                            "entity_id": notification_item.entity_id,
                            "expected_signature": dict(notification_item.expected_signature),
                            "fields": list(notification_item.fields),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )
        return tasks

    def _process_tasks(self, batch_id: int, current: datetime) -> None:
        task_ids = self.consequence_store.due_task_ids(
            origin_type="exam_venue_audit_event",
            now=_timestamp(current),
            batch_id=batch_id,
        )
        for task_id in task_ids:
            self._process_task(task_id, current)

    def _process_task(self, task_id: int, current: datetime) -> None:
        claim_until = self._claim_task(task_id, current)
        if claim_until is None:
            return
        today = date.today()
        task = self.consequence_store.task(task_id)
        if task is None or not self._owns_claim(task_id, claim_until):
            return
        details = json.loads(task.details_json)
        assignment_ids = [int(value) for value in details["assignment_ids"]]
        consequence_type = task.consequence_type
        member_id = task.recipient_member_id
        is_current = self._is_current(task.consequence_type, details, today)
        if not is_current:
            self._supersede(task, current)
            return
        try:
            if not self._owns_claim(task_id, claim_until):
                return
            if not self._is_current(task.consequence_type, details, date.today()):
                self._supersede(task, current)
                return
            if consequence_type == "calendar":
                event = self.calendar.sync_assignment(assignment_ids[0], future_from=today)
                if event is None:
                    raise RuntimeError("Calendar event could not be synchronized")
            else:
                self.notifications.create_direct(
                    committee_id=int(details["committee_id"]),
                    round_id=None,
                    recipient_member_ids={member_id},
                    event_type="exam_venue_changed",
                    title="Prüfungsort geändert",
                    message=(
                        "Angaben zu Ihrem bestätigten zukünftigen Prüfungseinsatz wurden geändert: "
                        + ", ".join(details["fields"])
                        + ". Bitte prüfen Sie den aktuellen Ort."
                    ),
                    action_path=f"/locations/{details['venue_id']}",
                    origin_key=f"exam-venue-change:{details['audit_id']}",
                )
        except Exception:
            self._fail(task_id, f"{consequence_type}_processing_failed", current, claim_until)
            return
        self.consequence_store.set_task_state(
            task.id,
            status="succeeded",
            attempt_count=task.attempt_count + 1,
            next_attempt_at=None,
            error_code=None,
            calendar_event_id=(
                event.id if consequence_type == "calendar" else task.calendar_event_id
            ),
            calendar_event_version=(
                event.version if consequence_type == "calendar" else task.calendar_event_version
            ),
            updated_at=_timestamp(current),
            expected_claim_until=claim_until,
        )

    def _claim_task(self, task_id: int, current: datetime) -> str | None:
        """Lease a due task in its existing status before Calendar or Notification work.

        `next_attempt_at` carries the lease expiry without changing the existing
        schema status constraint; an expired lease can be claimed after restart.
        """
        claim_until = _timestamp(current + CONSEQUENCE_CLAIM_LEASE)
        claimed = self.consequence_store.claim_task(
            task_id,
            now=_timestamp(current),
            lease_until=claim_until,
        )
        return claim_until if claimed else None

    def _owns_claim(self, task_id: int, claim_until: str) -> bool:
        task = self.consequence_store.task(task_id)
        return task is not None and task.status == "pending" and task.next_attempt_at == claim_until

    def _is_current(self, consequence_type: str, details, today: date) -> bool:
        return self.venue_planner.is_current(consequence_type, details, today=today)

    def _supersede_stale(self, audit_id: int, current: datetime) -> None:
        today = date.today()
        current_source = self.venue_planner.source_for_audit(audit_id, today=today)
        if current_source is None:
            return
        current_audit = current_source.audit
        entity_type = current_audit.entity_type
        entity_id = current_audit.entity_id
        batches = self.consequence_store.batches_by_origin(
            "exam_venue_audit_event", excluding_origin_key=str(audit_id)
        )
        pending_statuses = frozenset({"pending", "temporarily_failed", "permanently_failed"})
        for batch in batches:
            try:
                other_audit_id = int(batch.origin_key)
            except ValueError:
                continue
            other_source = self.venue_planner.source_for_audit(other_audit_id, today=today)
            other_audit = other_source.audit if other_source is not None else None
            if (
                other_audit is None
                or other_audit.entity_type != entity_type
                or other_audit.entity_id != entity_id
            ):
                continue
            for task in self.consequence_store.tasks_for_batch(batch.id, statuses=pending_statuses):
                details = json.loads(task.details_json)
                is_current = self._is_current(task.consequence_type, details, today)
                if not is_current:
                    self._supersede(task, current)

    def _fail(
        self, task_id: int, code: str, current: datetime, claim_until: str | None = None
    ) -> None:
        task = self.consequence_store.task(task_id)
        if task is None:
            return
        attempt_count = task.attempt_count + 1
        permanently_failed = attempt_count >= MAX_CONSEQUENCE_ATTEMPTS
        self.consequence_store.set_task_state(
            task_id,
            status="permanently_failed" if permanently_failed else "temporarily_failed",
            attempt_count=attempt_count,
            next_attempt_at=(
                None
                if permanently_failed
                else _timestamp(current + timedelta(minutes=2 ** (attempt_count - 1)))
            ),
            error_code=code,
            calendar_event_id=task.calendar_event_id,
            calendar_event_version=task.calendar_event_version,
            updated_at=_timestamp(current),
            expected_claim_until=claim_until,
        )

    def _supersede(self, task, current: datetime) -> None:
        self.consequence_store.set_task_state(
            task.id,
            status="superseded",
            attempt_count=task.attempt_count,
            next_attempt_at=None,
            error_code="superseded_by_newer_venue_change",
            calendar_event_id=task.calendar_event_id,
            calendar_event_version=task.calendar_event_version,
            updated_at=_timestamp(current),
        )

    @staticmethod
    def _audit_details(audit: VenueAuditEventSnapshot) -> dict[str, Any]:
        try:
            value = json.loads(audit.details_json)
        except TypeError, json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _problem_view(audit: VenueAuditEventSnapshot, task, error_code):
        return {
            "audit_id": audit.id,
            "venue_id": audit.venue_id,
            "entity_type": audit.entity_type,
            "entity_id": audit.entity_id,
            "consequence_type": task.consequence_type if task else "derivation",
            "status": task.status if task else "permanently_failed",
            "attempt_count": task.attempt_count if task else 0,
            "error_code": error_code,
            "updated_at": task.updated_at if task else audit.created_at,
        }
