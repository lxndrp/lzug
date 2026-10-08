"""Reliable, revision-aware consequences of confirmed plan changes."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.application.consequence_ports import (
    ApplicationConsequenceStore,
    ConsequenceBatchSnapshot,
    ConsequenceTaskDraft,
    ConsequenceTaskSnapshot,
    NotificationApplicationPort,
    PlanConsequencePlanningPort,
)
from backend.calendar.ports import CalendarApplicationPort
from backend.persistence.database import DEFAULT_DB_PATH
from backend.planning.plan_consequences import PlanConsequenceDescriptions
from backend.planning.proposals import ConfirmedPlanRevision

MAX_CONSEQUENCE_ATTEMPTS = 4
CONSEQUENCE_CLAIM_LEASE = timedelta(minutes=5)


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    return current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return _now(value).isoformat(timespec="seconds")


class PlanConsequenceService:
    """Derive and process plan-change effects without reopening the plan transaction."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        notification_service: NotificationApplicationPort,
        calendar_service: CalendarApplicationPort,
        planning_service: PlanConsequencePlanningPort,
        consequence_store: ApplicationConsequenceStore,
    ) -> None:
        self.db_path = Path(db_path)
        self.notifications = notification_service
        self.calendar = calendar_service
        self.planning = planning_service
        self.consequence_store = consequence_store

    def process_revision(
        self,
        revision_id: int,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Idempotently derive and process one revision's independent effects."""
        current = _now(now)
        batch_id = self._derive_revision(revision_id, current)
        round_id = self._round_id(revision_id)
        self._reconcile_round(round_id, current)
        self._process_tasks(batch_id=batch_id, current=current)
        return self._summary(revision_id)

    def process_due(self, *, now: datetime | None = None) -> dict[str, int]:
        """Retry due derivations and consequences without exposing their contents."""
        current = _now(now)
        revision_ids = self.consequence_store.due_revision_ids(
            self.planning.confirmed_plan_revision_ids(),
            now=_timestamp(current),
        )
        derived_revision_ids: list[int] = []
        derivation_problems = 0
        for revision_id in revision_ids:
            try:
                self._derive_revision(revision_id, current)
                derived_revision_ids.append(revision_id)
            except Exception:
                derivation_problems += 1
        round_ids = {self._round_id(revision_id) for revision_id in derived_revision_ids}
        for round_id in round_ids:
            self._reconcile_round(round_id, current)
        due_task_ids = self.consequence_store.due_task_ids(
            origin_type="confirmed_plan_revision",
            now=_timestamp(current),
        )
        self._process_tasks(batch_id=None, current=current)
        batches = self.consequence_store.batches_by_origin("confirmed_plan_revision")
        batch_tasks = tuple(
            task for batch in batches for task in self.consequence_store.tasks_for_batch(batch.id)
        )
        remaining_problems = sum(
            task.status in {"temporarily_failed", "permanently_failed"} for task in batch_tasks
        )
        failed_batches = sum(
            batch.status in {"temporarily_failed", "permanently_failed"} for batch in batches
        )
        return {
            "revisions": len(revision_ids),
            "processed": len(due_task_ids),
            "problems": derivation_problems + failed_batches + remaining_problems,
        }

    def retry_revision(self, revision_id: int) -> dict[str, Any]:
        """Retry only missing or failed current effects for one revision."""
        current = _now()
        revision = self.planning.confirmed_plan_revision(revision_id)
        if revision is None:
            raise ValueError("Confirmed plan revision not found")
        round_id = revision.exam_round_id
        batch = self.consequence_store.batch_by_origin("confirmed_plan_revision", str(revision_id))
        if batch is not None:
            self.consequence_store.set_batch_state(
                batch.id,
                status="pending",
                attempt_count=batch.attempt_count,
                next_attempt_at=None,
                error_code=None,
                updated_at=_timestamp(current),
            )
            for task in self.consequence_store.tasks_for_batch(
                batch.id,
                statuses=frozenset({"pending", "temporarily_failed", "permanently_failed"}),
            ):
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
        window = [
            item.id
            for item in self.planning.confirmed_plan_revisions(round_id)
            if item.resulting_revision >= revision.resulting_revision
        ]
        batch_ids = [self._derive_revision(item, current) for item in window]
        self._reconcile_round(round_id, current)
        for batch_id in batch_ids:
            self._process_tasks(batch_id=batch_id, current=current)
        return self._summary(revision_id)

    def list_for_round(self, round_id: int) -> list[dict[str, Any]]:
        """Return recipient-specific status for chair and deputy views."""
        result: list[dict[str, Any]] = []
        revisions = self.planning.confirmed_plan_revisions(round_id)
        for revision in sorted(revisions, key=lambda item: item.resulting_revision, reverse=True):
            batch = self.consequence_store.batch_by_origin(
                "confirmed_plan_revision", str(revision.id)
            )
            if batch is None:
                continue
            result.extend(
                self._task_view(task, batch, revision)
                for task in self.consequence_store.tasks_for_batch(batch.id)
            )
        return result

    def operator_status(self, revision_id: int) -> dict[str, int | str | None]:
        """Expose technical identifiers and counts, never notification details."""
        return self._summary(revision_id)

    def pending_ids_for_round(self, round_id: int) -> tuple[int, ...]:
        """Return technical follow-up identifiers for the round readiness projection."""
        ids: list[int] = []
        for revision in self.planning.confirmed_plan_revisions(round_id):
            batch = self.consequence_store.batch_by_origin(
                "confirmed_plan_revision", str(revision.id)
            )
            if batch is None:
                continue
            ids.extend(
                task.id
                for task in self.consequence_store.tasks_for_batch(
                    batch.id, statuses=frozenset({"pending", "temporarily_failed"})
                )
            )
        return tuple(sorted(ids))

    def _derive_revision(self, revision_id: int, current: datetime) -> int:
        source = self.planning.plan_consequence_source(revision_id)
        if source is None:
            raise ValueError("Confirmed plan revision not found")
        tasks: tuple[ConsequenceTaskDraft, ...] = ()
        notification_scope: tuple[int, ...] = ()
        error_code = source.error_code
        if error_code is None:
            try:
                assert source.descriptions is not None
                derived, scope = self._derive_tasks(source.descriptions)
                tasks = tuple(ConsequenceTaskDraft(**item) for item in derived)
                notification_scope = tuple(sorted(scope))
            except KeyError, TypeError, ValueError, json.JSONDecodeError:
                error_code = "invalid_revision_snapshot"
        return self.consequence_store.record_batch(
            origin_type="confirmed_plan_revision",
            origin_key=str(revision_id),
            confirmed_plan_revision_id=revision_id,
            notification_scope=notification_scope,
            tasks=tasks,
            error_code=error_code,
            now=_timestamp(current),
        )

    @staticmethod
    def _derive_tasks(
        descriptions: PlanConsequenceDescriptions,
    ) -> tuple[list[dict[str, Any]], set[int]]:
        tasks = [
            {
                "recipient_member_id": item.recipient_member_id,
                "consequence_type": "calendar",
                "action": item.action,
                "identity_key": f"assignment:{item.assignment_id}",
                "details_json": json.dumps(
                    {"assignment_id": item.assignment_id}, separators=(",", ":")
                ),
            }
            for item in descriptions.calendar
        ]
        tasks.extend(
            {
                "recipient_member_id": item.recipient_member_id,
                "consequence_type": "notification",
                "action": "notify",
                "identity_key": f"member:{item.recipient_member_id}",
                "details_json": json.dumps(
                    {"categories": list(item.categories)},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
            for item in descriptions.notifications
        )
        return tasks, set(descriptions.notification_scope)

    def _supersede_older(self, revision_id: int, current: datetime) -> None:
        revision = self.planning.confirmed_plan_revision(revision_id)
        if revision is None:
            return
        current_batch = self.consequence_store.batch_by_origin(
            "confirmed_plan_revision", str(revision_id)
        )
        if current_batch is None:
            return
        current_tasks = self.consequence_store.tasks_for_batch(current_batch.id)
        notification_scope = set(json.loads(current_batch.notification_scope_json))
        calendar_keys = {
            task.identity_key for task in current_tasks if task.consequence_type == "calendar"
        }
        if not notification_scope and not calendar_keys:
            return
        statuses = frozenset({"pending", "temporarily_failed", "permanently_failed"})
        for older in self.planning.confirmed_plan_revisions(revision.exam_round_id):
            if older.resulting_revision >= revision.resulting_revision:
                continue
            older_batch = self.consequence_store.batch_by_origin(
                "confirmed_plan_revision", str(older.id)
            )
            if older_batch is None:
                continue
            for task in self.consequence_store.tasks_for_batch(older_batch.id, statuses=statuses):
                should_supersede = (
                    task.consequence_type == "notification"
                    and task.recipient_member_id in notification_scope
                ) or (task.consequence_type == "calendar" and task.identity_key in calendar_keys)
                if should_supersede:
                    self.consequence_store.set_task_state(
                        task.id,
                        status="superseded",
                        attempt_count=task.attempt_count,
                        next_attempt_at=None,
                        error_code="superseded_by_newer_revision",
                        calendar_event_id=task.calendar_event_id,
                        calendar_event_version=task.calendar_event_version,
                        updated_at=_timestamp(current),
                    )

    def _reconcile_round(self, round_id: int, current: datetime) -> None:
        for revision in self.planning.confirmed_plan_revisions(round_id):
            if (
                self.consequence_store.batch_by_origin("confirmed_plan_revision", str(revision.id))
                is not None
            ):
                self._supersede_older(revision.id, current)

    def _round_id(self, revision_id: int) -> int:
        revision = self.planning.confirmed_plan_revision(revision_id)
        if revision is None:
            raise ValueError("Confirmed plan revision not found")
        return revision.exam_round_id

    def _process_tasks(self, *, batch_id: int | None, current: datetime) -> None:
        task_ids = self.consequence_store.due_task_ids(
            origin_type="confirmed_plan_revision",
            now=_timestamp(current),
            batch_id=batch_id,
        )
        calendar_ids: list[int] = []
        for task_id in task_ids:
            task = self.consequence_store.task(task_id)
            if task is None:
                continue
            if task.consequence_type == "calendar":
                calendar_ids.append(task_id)
                continue
            self._process_notification(task_id, current)
        if calendar_ids:
            self._process_calendars(calendar_ids, current)

    def _process_notification(self, task_id: int, current: datetime) -> None:
        if not self._claim_task(task_id, current):
            return
        task = self.consequence_store.task(task_id)
        if task is None:
            return
        try:
            revision_id = int(task.origin_key)
        except ValueError:
            self._fail_task(task_id, "invalid_consequence_origin", current)
            return
        source = self.planning.plan_consequence_source(revision_id)
        if source is None:
            self._fail_task(task_id, "confirmed_revision_missing", current)
            return
        categories = set(json.loads(task.details_json).get("categories", []))
        member_id = task.recipient_member_id
        round_id = source.exam_round_id
        committee_id = source.committee_id
        try:
            superseded_revision_ids = self.notifications.supersede_unsent_plan_changes(
                round_id=round_id,
                recipient_member_id=member_id,
                newer_revision_id=revision_id,
            )
            self._mark_superseded_notification_tasks(
                superseded_revision_ids,
                current,
            )
            self.notifications.create_direct(
                committee_id=committee_id,
                round_id=round_id,
                recipient_member_ids={member_id},
                event_type="plan_changed",
                title="Prüfungsplan geändert",
                message=self._notification_message(categories),
                action_path=f"/confirmed-plans/{round_id}",
                origin_key=f"confirmed-plan-revision:{revision_id}",
            )
        except Exception:
            self._fail_task(task_id, "notification_processing_failed", current)
            return
        self.consequence_store.set_task_state(
            task_id,
            status="succeeded",
            attempt_count=task.attempt_count + 1,
            next_attempt_at=None,
            error_code=None,
            calendar_event_id=task.calendar_event_id,
            calendar_event_version=task.calendar_event_version,
            updated_at=_timestamp(current),
        )

    def _mark_superseded_notification_tasks(
        self,
        revision_ids: set[int],
        current: datetime,
    ) -> None:
        if not revision_ids:
            return
        for revision_id in revision_ids:
            batch = self.consequence_store.batch_by_origin(
                "confirmed_plan_revision", str(revision_id)
            )
            if batch is None:
                continue
            for task in self.consequence_store.tasks_for_batch(
                batch.id, statuses=frozenset({"succeeded"})
            ):
                if task.consequence_type == "notification":
                    self.consequence_store.set_task_state(
                        task.id,
                        status="superseded",
                        attempt_count=task.attempt_count,
                        next_attempt_at=None,
                        error_code="superseded_by_newer_revision",
                        calendar_event_id=task.calendar_event_id,
                        calendar_event_version=task.calendar_event_version,
                        updated_at=_timestamp(current),
                    )

    def _process_calendars(self, task_ids: list[int], current: datetime) -> None:
        by_round: dict[int, list[int]] = defaultdict(list)
        claimed_task_ids = [task_id for task_id in task_ids if self._claim_task(task_id, current)]
        for task_id in claimed_task_ids:
            task = self.consequence_store.task(task_id)
            if task is None:
                continue
            try:
                revision_id = int(task.origin_key)
            except ValueError:
                self._fail_task(task_id, "invalid_consequence_origin", current)
                continue
            revision = self.planning.confirmed_plan_revision(revision_id)
            if revision is not None:
                by_round[revision.exam_round_id].append(task_id)
        for round_id, round_task_ids in by_round.items():
            try:
                self.calendar.sync_round(round_id)
            except Exception:
                for task_id in round_task_ids:
                    self._fail_task(task_id, "calendar_processing_failed", current)
                continue
            for task_id in round_task_ids:
                self._complete_calendar_task(task_id, current)

    def _claim_task(self, task_id: int, current: datetime) -> bool:
        """Lease a due task in its existing status before cross-module work starts.

        `next_attempt_at` carries the lease expiry, so this remains compatible
        with the existing schema status constraint and recovers after a crash.
        """
        claim_until = _timestamp(current + CONSEQUENCE_CLAIM_LEASE)
        return self.consequence_store.claim_task(
            task_id,
            now=_timestamp(current),
            lease_until=claim_until,
        )

    def _complete_calendar_task(self, task_id: int, current: datetime) -> None:
        task = self.consequence_store.task(task_id)
        if task is None:
            return
        assignment_id = int(json.loads(task.details_json)["assignment_id"])
        recipient_member_id = task.recipient_member_id
        event = self.calendar.event_for_assignment(assignment_id, recipient_member_id)
        valid = (task.action == "cancel" and (event is None or event.status == "cancelled")) or (
            task.action in {"create", "update"}
            and event is not None
            and event.status != "cancelled"
        )
        if not valid:
            self._fail_task(task_id, "calendar_state_missing", current)
            return
        self.consequence_store.set_task_state(
            task_id,
            status="succeeded",
            attempt_count=task.attempt_count + 1,
            next_attempt_at=None,
            error_code=None,
            calendar_event_id=event.id if event is not None else None,
            calendar_event_version=event.version if event is not None else None,
            updated_at=_timestamp(current),
        )

    def _fail_task(self, task_id: int, code: str, current: datetime) -> None:
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
        )

    @staticmethod
    def _notification_message(categories: set[str]) -> str:
        parts = []
        if "added" in categories:
            parts.append("Sie wurden neu eingeplant")
        if "removed" in categories:
            parts.append("Ihre bisherige Einplanung wurde aufgehoben")
        if "changed" in categories:
            parts.append("Zeit, Ort oder Rolle Ihrer Einplanung wurde geändert")
        if "crew_changed" in categories:
            parts.append("Die Besetzung Ihres Prüfungseinsatzes wurde geändert")
        if "overview" in categories and not parts:
            parts.append("Eine bestätigte Planänderung betrifft den Ausschuss")
        return ". ".join(parts) + ". Bitte prüfen Sie den aktuellen bestätigten Plan."

    def _summary(self, revision_id: int) -> dict[str, Any]:
        batch = self.consequence_store.batch_by_origin("confirmed_plan_revision", str(revision_id))
        if batch is None:
            return {
                "revision_id": revision_id,
                "derivation_status": "missing",
                "processed": 0,
                "problems": 1,
                "pending": 0,
                "superseded": 0,
                "technical_items": [],
            }
        tasks = self.consequence_store.tasks_for_batch(batch.id)
        return {
            "revision_id": revision_id,
            "derivation_status": batch.status,
            "processed": sum(task.status == "succeeded" for task in tasks),
            "problems": sum(
                task.status in {"temporarily_failed", "permanently_failed"} for task in tasks
            )
            + int(batch.status in {"temporarily_failed", "permanently_failed"}),
            "pending": sum(task.status == "pending" for task in tasks),
            "superseded": sum(task.status == "superseded" for task in tasks),
            "technical_items": [
                {
                    "id": task.id,
                    "status": task.status,
                    "attempt_count": task.attempt_count,
                    "next_attempt_at": task.next_attempt_at,
                    "error_code": task.error_code,
                    "updated_at": task.updated_at,
                }
                for task in tasks
            ],
        }

    @staticmethod
    def _task_view(
        task: ConsequenceTaskSnapshot,
        batch: ConsequenceBatchSnapshot,
        revision: ConfirmedPlanRevision,
    ) -> dict[str, Any]:
        return {
            "id": task.id,
            "revision_id": revision.id,
            "resulting_revision": revision.resulting_revision,
            "recipient_member_id": task.recipient_member_id,
            "consequence_type": task.consequence_type,
            "action": task.action,
            "status": task.status,
            "attempt_count": task.attempt_count,
            "error_code": task.error_code,
            "calendar_event_id": task.calendar_event_id,
            "calendar_event_version": task.calendar_event_version,
            "derivation_status": batch.status,
            "updated_at": task.updated_at,
        }
