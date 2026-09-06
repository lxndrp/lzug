"""Reliable calendar and notification consequences of venue master-data changes."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .calendar import CalendarService
from .database import DEFAULT_DB_PATH, session_scope
from .models import (
    ExamDay,
    ExamDayAssignment,
    ExamRoom,
    ExamRound,
    ExamVenue,
    ExamVenueAuditEvent,
    PlanConsequence,
    PlanConsequenceBatch,
)
from .notifications import NotificationService

MAX_CONSEQUENCE_ATTEMPTS = 4
CALENDAR_VENUE_FIELDS = frozenset(
    {
        "name",
        "street",
        "postal_code",
        "city",
        "country",
        "site_name",
        "entrance",
        "travel_directions",
    }
)
CALENDAR_ROOM_FIELDS = frozenset(
    {"name", "building", "wing", "floor", "room_number", "access_notes"}
)
NOTIFICATION_VENUE_FIELDS = frozenset(
    {
        "street",
        "postal_code",
        "city",
        "country",
        "site_name",
        "entrance",
        "travel_directions",
        "is_accessible",
        "accessibility_status",
        "accessibility_notes",
    }
)
NOTIFICATION_ROOM_FIELDS = frozenset(
    {"name", "building", "wing", "floor", "room_number", "access_notes"}
)
FIELD_LABELS = {
    "name": "Bezeichnung",
    "street": "Anschrift",
    "postal_code": "Anschrift",
    "city": "Anschrift",
    "country": "Anschrift",
    "site_name": "Standort",
    "entrance": "Eingang oder Treffpunkt",
    "travel_directions": "Anreise- oder Auffindungshinweis",
    "building": "Gebäude",
    "wing": "Trakt",
    "floor": "Etage",
    "room_number": "Raumnummer",
    "access_notes": "Zugangs- oder Auffindungshinweis",
    "is_accessible": "Barrierefreiheit",
    "accessibility_status": "Barrierefreiheit",
    "accessibility_notes": "Barrierefreiheitshinweis",
}


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return _now(value).isoformat(timespec="seconds")


class VenueConsequenceService:
    """Derive and retry independent effects from immutable venue audit events."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        notification_service: NotificationService | None = None,
        calendar_service: CalendarService | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.notifications = notification_service or NotificationService(self.db_path)
        self.calendar = calendar_service or CalendarService(self.db_path)

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
        changed_fields = {key for key in before if before.get(key) != after.get(key)}
        calendar_fields = changed_fields & self._calendar_fields(entity_type)
        notification_fields = changed_fields & self._notification_fields(entity_type)
        if not meaningful_change:
            notification_fields.clear()
        with session_scope(self.db_path) as session:
            assignments = self._assignments(
                session,
                venue_id=venue_id,
                room_id=entity_id if entity_type == "room" else None,
                today=today or date.today(),
            )
            assignment_count = len(assignments)
            dates = [day.date for _assignment, day, _round in assignments]
            recipient_count = len(
                {assignment.committee_member_id for assignment, _day, _round in assignments}
            )
        return {
            "count": assignment_count,
            "date_from": min(dates, default=None),
            "date_to": max(dates, default=None),
            "requires_confirmation": bool(assignment_count and changed_fields),
            "calendar": {
                "event_count": assignment_count if calendar_fields else 0,
                "fields": self._labels(calendar_fields),
            },
            "notifications": {
                "recipient_count": recipient_count if notification_fields else 0,
                "fields": self._labels(notification_fields),
            },
        }

    def process_audit(self, audit_id: int, *, now: datetime | None = None) -> dict[str, Any]:
        current = _now(now)
        batch_id = self._derive(audit_id, current)
        self._supersede_stale(audit_id, current)
        self._process_tasks(batch_id, current)
        return self.summary(audit_id)

    def retry_audit(self, audit_id: int) -> dict[str, Any]:
        current = _now()
        batch_id = self._derive(audit_id, current)
        with session_scope(self.db_path) as session:
            tasks = session.scalars(
                select(PlanConsequence).where(
                    PlanConsequence.batch_id == batch_id,
                    PlanConsequence.status.in_(
                        {"pending", "temporarily_failed", "permanently_failed"}
                    ),
                )
            ).all()
            for task in tasks:
                task.status = "pending"
                task.next_attempt_at = None
                task.error_code = None
                task.updated_at = _timestamp(current)
        self._supersede_stale(audit_id, current)
        self._process_tasks(batch_id, current)
        return self.summary(audit_id)

    def problems_for_venue(self, venue_id: int) -> list[dict[str, Any]]:
        with session_scope(self.db_path) as session:
            audits = session.scalars(
                select(ExamVenueAuditEvent)
                .where(ExamVenueAuditEvent.venue_id == venue_id)
                .order_by(ExamVenueAuditEvent.id.desc())
            ).all()
            result: list[dict[str, Any]] = []
            for audit in audits:
                details = self._audit_details(audit)
                if details.get("consequence_version") != 1:
                    continue
                batch = self._batch(session, audit.id)
                if batch is None:
                    result.append(self._problem_view(audit, None, None, "derivation_missing"))
                    continue
                tasks = session.scalars(
                    select(PlanConsequence).where(
                        PlanConsequence.batch_id == batch.id,
                        PlanConsequence.status.in_({"temporarily_failed", "permanently_failed"}),
                    )
                ).all()
                result.extend(
                    self._problem_view(audit, batch, task, task.error_code) for task in tasks
                )
            return result

    def summary(self, audit_id: int) -> dict[str, Any]:
        with session_scope(self.db_path) as session:
            batch = self._batch(session, audit_id)
            if batch is None:
                return {"audit_id": audit_id, "processed": 0, "problems": 1, "pending": 0}
            tasks = session.scalars(
                select(PlanConsequence).where(PlanConsequence.batch_id == batch.id)
            ).all()
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
        with session_scope(self.db_path) as session:
            audit = session.get(ExamVenueAuditEvent, audit_id)
            if audit is None:
                raise ValueError("Venue change audit not found")
            details = self._audit_details(audit)
            if details.get("consequence_version") != 1:
                raise ValueError("Venue change has no retryable consequence contract")
            batch = self._batch(session, audit.id)
            if batch is None:
                batch = PlanConsequenceBatch(
                    origin_type="exam_venue_audit_event",
                    origin_key=str(audit.id),
                )
                try:
                    with session.begin_nested():
                        session.add(batch)
                        session.flush()
                except IntegrityError:
                    batch = self._batch(session, audit.id)
                    if batch is None:
                        raise
            if (
                session.scalar(
                    select(PlanConsequence.id).where(PlanConsequence.batch_id == batch.id).limit(1)
                )
                is None
            ):
                for task in self._tasks(session, audit, details):
                    session.add(PlanConsequence(batch_id=batch.id, **task))
            batch.status = "succeeded"
            batch.attempt_count += 1
            batch.next_attempt_at = None
            batch.error_code = None
            batch.updated_at = _timestamp(current)
            session.flush()
            return batch.id

    def _tasks(self, session, audit, details) -> list[dict[str, Any]]:
        after = details["after"]
        changed_fields = set(details["changed_fields"])
        entity_type = audit.entity_type
        calendar_fields = changed_fields & self._calendar_fields(entity_type)
        notification_fields = changed_fields & self._notification_fields(entity_type)
        if not details.get("meaningful_change", True):
            notification_fields.clear()
        assignments = self._assignments(
            session,
            venue_id=audit.venue_id,
            room_id=audit.entity_id if entity_type == "room" else None,
            today=date.today(),
        )
        expected_calendar = self._signature(after, self._calendar_fields(entity_type))
        expected_notification = self._signature(after, self._notification_fields(entity_type))
        tasks: list[dict[str, Any]] = []
        if calendar_fields:
            for assignment, _day, _round in assignments:
                tasks.append(
                    {
                        "recipient_member_id": assignment.committee_member_id,
                        "consequence_type": "calendar",
                        "action": "update",
                        "identity_key": f"assignment:{assignment.id}",
                        "details_json": json.dumps(
                            {
                                "audit_id": audit.id,
                                "assignment_ids": [assignment.id],
                                "entity_type": entity_type,
                                "entity_id": audit.entity_id,
                                "expected_signature": expected_calendar,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    }
                )
        if notification_fields:
            by_recipient: dict[tuple[int, int], list[int]] = defaultdict(list)
            for assignment, _day, exam_round in assignments:
                by_recipient[(assignment.committee_member_id, exam_round.committee_id)].append(
                    assignment.id
                )
            labels = self._labels(notification_fields)
            for (member_id, committee_id), assignment_ids in sorted(by_recipient.items()):
                tasks.append(
                    {
                        "recipient_member_id": member_id,
                        "consequence_type": "notification",
                        "action": "notify",
                        "identity_key": f"member:{member_id}:committee:{committee_id}",
                        "details_json": json.dumps(
                            {
                                "audit_id": audit.id,
                                "assignment_ids": sorted(assignment_ids),
                                "committee_id": committee_id,
                                "venue_id": audit.venue_id,
                                "entity_type": entity_type,
                                "entity_id": audit.entity_id,
                                "expected_signature": expected_notification,
                                "fields": labels,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    }
                )
        return tasks

    def _process_tasks(self, batch_id: int, current: datetime) -> None:
        with session_scope(self.db_path) as session:
            task_ids = list(
                session.scalars(
                    select(PlanConsequence.id).where(
                        PlanConsequence.batch_id == batch_id,
                        PlanConsequence.status.in_({"pending", "temporarily_failed"}),
                        (PlanConsequence.next_attempt_at.is_(None))
                        | (PlanConsequence.next_attempt_at <= _timestamp(current)),
                    )
                )
            )
        for task_id in task_ids:
            self._process_task(task_id, current)

    def _process_task(self, task_id: int, current: datetime) -> None:
        today = date.today()
        with session_scope(self.db_path) as session:
            task = session.get(PlanConsequence, task_id)
            if task is None:
                return
            details = json.loads(task.details_json)
            if not self._is_current(session, task, details, today):
                self._supersede(task, current)
                return
            assignment_ids = [int(value) for value in details["assignment_ids"]]
            consequence_type = task.consequence_type
            member_id = task.recipient_member_id
        try:
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
            self._fail(task_id, f"{consequence_type}_processing_failed", current)
            return
        with session_scope(self.db_path) as session:
            task = session.get(PlanConsequence, task_id)
            if task is None:
                return
            task.status = "succeeded"
            task.attempt_count += 1
            task.next_attempt_at = None
            task.error_code = None
            if consequence_type == "calendar":
                task.calendar_event_id = event.id
                task.calendar_event_version = event.version
            task.updated_at = _timestamp(current)

    def _is_current(self, session, task, details, today: date) -> bool:
        assignments = [
            session.get(ExamDayAssignment, int(value)) for value in details["assignment_ids"]
        ]
        assignments = [assignment for assignment in assignments if assignment is not None]
        if not assignments:
            return False
        for assignment in assignments:
            day = session.get(ExamDay, assignment.exam_day_id)
            if day and day.status == "confirmed" and day.date >= today.isoformat():
                if details["entity_type"] == "room" and day.room_id != details["entity_id"]:
                    continue
                room = session.get(ExamRoom, day.room_id)
                if room is None or room.venue_id != details.get("venue_id", room.venue_id):
                    continue
                entity = (
                    room
                    if details["entity_type"] == "room"
                    else session.get(ExamVenue, room.venue_id)
                )
                if entity is None:
                    continue
                fields = (
                    self._calendar_fields(details["entity_type"])
                    if task.consequence_type == "calendar"
                    else self._notification_fields(details["entity_type"])
                )
                if self._signature(vars(entity), fields) == details["expected_signature"]:
                    return True
        return False

    def _supersede_stale(self, audit_id: int, current: datetime) -> None:
        today = date.today()
        with session_scope(self.db_path) as session:
            current_audit = session.get(ExamVenueAuditEvent, audit_id)
            if current_audit is None:
                return
            batches = session.scalars(
                select(PlanConsequenceBatch).where(
                    PlanConsequenceBatch.origin_type == "exam_venue_audit_event",
                    PlanConsequenceBatch.origin_key != str(audit_id),
                )
            ).all()
            for batch in batches:
                try:
                    other_id = int(batch.origin_key)
                except ValueError:
                    continue
                other = session.get(ExamVenueAuditEvent, other_id)
                if (
                    other is None
                    or other.entity_type != current_audit.entity_type
                    or other.entity_id != current_audit.entity_id
                ):
                    continue
                tasks = session.scalars(
                    select(PlanConsequence).where(
                        PlanConsequence.batch_id == batch.id,
                        PlanConsequence.status.in_(
                            {"pending", "temporarily_failed", "permanently_failed"}
                        ),
                    )
                ).all()
                for task in tasks:
                    details = json.loads(task.details_json)
                    if not self._is_current(session, task, details, today):
                        self._supersede(task, current)

    def _fail(self, task_id: int, code: str, current: datetime) -> None:
        with session_scope(self.db_path) as session:
            task = session.get(PlanConsequence, task_id)
            if task is None:
                return
            task.attempt_count += 1
            task.error_code = code
            task.updated_at = _timestamp(current)
            if task.attempt_count >= MAX_CONSEQUENCE_ATTEMPTS:
                task.status = "permanently_failed"
                task.next_attempt_at = None
            else:
                task.status = "temporarily_failed"
                task.next_attempt_at = _timestamp(
                    current + timedelta(minutes=2 ** (task.attempt_count - 1))
                )

    @staticmethod
    def _supersede(task: PlanConsequence, current: datetime) -> None:
        task.status = "superseded"
        task.next_attempt_at = None
        task.error_code = "superseded_by_newer_venue_change"
        task.updated_at = _timestamp(current)

    @staticmethod
    def _assignments(session, *, venue_id: int, room_id: int | None, today: date):
        statement = (
            select(ExamDayAssignment, ExamDay, ExamRound)
            .join(ExamDay, ExamDay.id == ExamDayAssignment.exam_day_id)
            .join(ExamRound, ExamRound.id == ExamDay.exam_round_id)
            .join(ExamRoom, ExamRoom.id == ExamDay.room_id)
            .where(
                ExamRoom.venue_id == venue_id,
                ExamDay.status == "confirmed",
                ExamDay.date >= today.isoformat(),
            )
            .order_by(ExamDay.date, ExamDayAssignment.id)
        )
        if room_id is not None:
            statement = statement.where(ExamDay.room_id == room_id)
        return list(session.execute(statement))

    @staticmethod
    def _calendar_fields(entity_type: str) -> frozenset[str]:
        return CALENDAR_ROOM_FIELDS if entity_type == "room" else CALENDAR_VENUE_FIELDS

    @staticmethod
    def _notification_fields(entity_type: str) -> frozenset[str]:
        return NOTIFICATION_ROOM_FIELDS if entity_type == "room" else NOTIFICATION_VENUE_FIELDS

    @staticmethod
    def _signature(values: dict[str, Any], fields: frozenset[str]) -> dict[str, Any]:
        return {field: values.get(field) for field in sorted(fields)}

    @staticmethod
    def _labels(fields: set[str]) -> list[str]:
        return sorted({FIELD_LABELS[field] for field in fields})

    @staticmethod
    def _audit_details(audit: ExamVenueAuditEvent) -> dict[str, Any]:
        try:
            value = json.loads(audit.details_json)
        except TypeError, json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _batch(session, audit_id: int) -> PlanConsequenceBatch | None:
        return session.scalar(
            select(PlanConsequenceBatch).where(
                PlanConsequenceBatch.origin_type == "exam_venue_audit_event",
                PlanConsequenceBatch.origin_key == str(audit_id),
            )
        )

    @staticmethod
    def _problem_view(audit, batch, task, error_code):
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
