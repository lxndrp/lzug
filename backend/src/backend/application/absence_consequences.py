"""Restartable Application processing for immutable absence source records."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.application.calendar_ports import CalendarApplicationPort
from backend.application.consequence_ports import (
    ApplicationConsequenceStore,
    ConsequenceTaskDraft,
    NotificationApplicationPort,
)
from backend.application.exam_lifecycle_ports import ExamLifecycleUnitOfWorkFactory

CLAIM_LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 4


def _timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now(UTC)
    current = current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)
    return current.replace(microsecond=0).isoformat()


class AbsenceConsequenceApplication:
    """Re-derive durable tasks from sources and resume their independent effects."""

    def __init__(
        self,
        *,
        unit_of_work_factory: ExamLifecycleUnitOfWorkFactory,
        consequence_store: ApplicationConsequenceStore,
        notification_service: NotificationApplicationPort,
        calendar_service: CalendarApplicationPort,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.consequence_store = consequence_store
        self.notifications = notification_service
        self.calendar = calendar_service

    def process_due(self, *, now: datetime | None = None) -> dict[str, int]:
        current = now or datetime.now(UTC)
        with self.unit_of_work_factory.read_scope() as unit_of_work:
            sources = tuple(unit_of_work.absence.sources_after_cutover())
            legacy_unreplayable = unit_of_work.absence.legacy_unreplayable_count()
        errors = 0
        for source in sources:
            try:
                self._record_source(source, current)
            except Exception:
                errors += 1
        self.consequence_store.retry_permanently_failed_tasks(
            origin_type="absence_audit_event", now=_timestamp(current)
        )
        task_ids = self.consequence_store.due_task_ids(
            origin_type="absence_audit_event", now=_timestamp(current)
        )
        for task_id in task_ids:
            if not self._process_task(task_id, current):
                errors += 1
        failures = sum(
            task.status in {"temporarily_failed", "permanently_failed"}
            for source in sources
            if (
                batch := self.consequence_store.batch_by_origin(
                    "absence_audit_event", str(source["origin_id"])
                )
            )
            for task in self.consequence_store.tasks_for_batch(batch.id)
        )
        return {
            "sources": len(sources),
            "processed": len(task_ids),
            "problems": errors + failures,
            "legacy_unreplayable": legacy_unreplayable,
        }

    def process_source(self, origin_id: str, *, now: datetime | None = None) -> dict[str, int]:
        """Record and process only one source created by the just-committed command."""
        current = now or datetime.now(UTC)
        with self.unit_of_work_factory.read_scope() as unit_of_work:
            source = unit_of_work.absence.source_by_origin(origin_id)
        if source is None:
            return {"sources": 0, "processed": 0, "problems": 0}
        try:
            batch = self._record_source(source, current)
        except Exception:
            return {"sources": 1, "processed": 0, "problems": 1}
        task_ids = self.consequence_store.due_task_ids(
            origin_type="absence_audit_event",
            now=_timestamp(current),
            batch_id=batch,
        )
        problems = sum(not self._process_task(task_id, current) for task_id in task_ids)
        return {"sources": 1, "processed": len(task_ids), "problems": problems}

    def _record_source(self, source: dict[str, Any], current: datetime) -> int:
        details = json.loads(str(source["source_json"]))
        return self.consequence_store.record_batch(
            origin_type="absence_audit_event",
            origin_key=str(source["origin_id"]),
            confirmed_plan_revision_id=None,
            notification_scope=tuple(details["recipient_member_ids"]),
            tasks=self._drafts(details),
            error_code=None,
            now=_timestamp(current),
        )

    def _drafts(self, source: dict[str, Any]) -> tuple[ConsequenceTaskDraft, ...]:
        origin = str(source["origin_id"])
        notice = source["notice"]
        report_id = int(source["report_id"])
        tasks: list[ConsequenceTaskDraft] = [
            {
                "recipient_member_id": int(member_id),
                "consequence_type": "notification",
                "action": "notify",
                "identity_key": origin,
                "details_json": json.dumps(
                    {
                        "committee_id": source["committee_id"],
                        "round_id": source["round_id"],
                        "report_id": report_id,
                        "event_type": notice["event_type"],
                        "origin_key": notice.get("origin_key"),
                        "title": notice["title"],
                        "message": notice["message"],
                        "action_path": notice["action_path"],
                        "urgent": bool(notice.get("urgent", False)),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
            for member_id in sorted(set(source["recipient_member_ids"]))
        ]
        if source.get("calendar_enabled"):
            member_id = int(source.get("previous_member_id") or source["report_id"])
            tasks.append(
                {
                    "recipient_member_id": member_id,
                    "consequence_type": "calendar",
                    "action": ("cancel" if source.get("calendar_action") == "cancel" else "update"),
                    "identity_key": f"assignment:{source['assignment_id']}",
                    "details_json": json.dumps(
                        {
                            "round_id": source["round_id"],
                            "assignment_id": source["assignment_id"],
                            "assignment_revision": source["assignment_revision"],
                            "calendar_action": source.get("calendar_action", "update"),
                            "before_image": source["calendar_before_image"],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )
        return tuple(tasks)

    def _process_task(self, task_id: int, current: datetime) -> bool:
        now = _timestamp(current)
        lease_until = _timestamp(current + CLAIM_LEASE)
        if not self.consequence_store.claim_task(task_id, now=now, lease_until=lease_until):
            return True
        task = self.consequence_store.task(task_id)
        if task is None:
            return False
        try:
            details = json.loads(task.details_json)
            if task.consequence_type == "calendar":
                if not self._owns_claim(task_id, lease_until):
                    return True
                result = self.calendar.apply_absence_follow_up(
                    assignment_id=int(details["assignment_id"]),
                    round_id=int(details["round_id"]),
                    origin_id=task.origin_key,
                    execution_version=int(details["assignment_revision"]),
                    action=str(details["calendar_action"]),
                    before_image=tuple(details["before_image"]),
                )
                if result == "conflict":
                    raise ValueError("calendar_execution_origin_conflict")
                event_id = None
                event_version = None
            elif task.consequence_type == "notification":
                if not self._owns_claim(task_id, lease_until):
                    return True
                self.notifications.create_direct(
                    committee_id=int(details["committee_id"]),
                    round_id=int(details["round_id"]),
                    recipient_member_ids={task.recipient_member_id},
                    event_type=str(details["event_type"]),
                    title=str(details["title"]),
                    message=str(details["message"]),
                    action_path=str(details["action_path"]),
                    origin_key=str(
                        details.get("origin_key") or f"absence-source:{task.origin_key}"
                    ),
                    urgent=bool(details.get("urgent", False)),
                )
                event_id = None
                event_version = None
            else:
                raise ValueError("unsupported_absence_consequence")
            status, next_attempt, error_code = "succeeded", None, None
        except Exception:
            attempt = task.attempt_count + 1
            status = "permanently_failed" if attempt >= MAX_ATTEMPTS else "temporarily_failed"
            next_attempt = (
                None
                if status == "permanently_failed"
                else _timestamp(current + timedelta(minutes=2**attempt))
            )
            error_code = "absence_consequence_failed"
            event_id = task.calendar_event_id
            event_version = task.calendar_event_version
        return self.consequence_store.set_task_state(
            task_id,
            status=status,
            attempt_count=task.attempt_count + 1,
            next_attempt_at=next_attempt,
            error_code=error_code,
            calendar_event_id=event_id,
            calendar_event_version=event_version,
            updated_at=now,
            expected_claim_until=lease_until,
        )

    def _owns_claim(self, task_id: int, lease_until: str) -> bool:
        task = self.consequence_store.task(task_id)
        return task is not None and task.status == "pending" and task.next_attempt_at == lease_until
