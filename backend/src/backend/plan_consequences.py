"""Reliable, revision-aware consequences of confirmed plan changes."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from .calendar import CalendarService
from .database import DEFAULT_DB_PATH, session_scope
from .models import (
    CalendarEvent,
    CommitteeMember,
    ConfirmedPlanRevision,
    ExamRound,
    Notification,
    PlanConsequence,
    PlanConsequenceBatch,
)
from .notifications import NotificationService

MAX_CONSEQUENCE_ATTEMPTS = 4


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
        notification_service: NotificationService | None = None,
        calendar_service: CalendarService | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.notifications = notification_service or NotificationService(self.db_path)
        self.calendar = calendar_service or CalendarService(self.db_path)

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
        with session_scope(self.db_path) as session:
            revision_ids = list(
                session.scalars(
                    select(ConfirmedPlanRevision.id)
                    .outerjoin(
                        PlanConsequenceBatch,
                        PlanConsequenceBatch.confirmed_plan_revision_id == ConfirmedPlanRevision.id,
                    )
                    .where(
                        or_(
                            PlanConsequenceBatch.id.is_(None),
                            (
                                PlanConsequenceBatch.status.in_({"pending", "temporarily_failed"})
                                & (
                                    PlanConsequenceBatch.next_attempt_at.is_(None)
                                    | (PlanConsequenceBatch.next_attempt_at <= _timestamp(current))
                                )
                            ),
                        ),
                    )
                    .order_by(
                        ConfirmedPlanRevision.exam_round_id,
                        ConfirmedPlanRevision.resulting_revision,
                    )
                )
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
        with session_scope(self.db_path) as session:
            due_task_ids = list(
                session.scalars(
                    select(PlanConsequence.id)
                    .join(PlanConsequenceBatch)
                    .where(
                        PlanConsequenceBatch.origin_type == "confirmed_plan_revision",
                        PlanConsequence.status.in_({"pending", "temporarily_failed"}),
                        (
                            PlanConsequence.next_attempt_at.is_(None)
                            | (PlanConsequence.next_attempt_at <= _timestamp(current))
                        ),
                    )
                )
            )
        self._process_tasks(batch_id=None, current=current)
        with session_scope(self.db_path) as session:
            remaining_problems = (
                session.query(PlanConsequence)
                .join(PlanConsequenceBatch)
                .filter(PlanConsequence.status.in_({"temporarily_failed", "permanently_failed"}))
                .filter(PlanConsequenceBatch.origin_type == "confirmed_plan_revision")
                .count()
            )
            failed_batches = (
                session.query(PlanConsequenceBatch)
                .filter(
                    PlanConsequenceBatch.origin_type == "confirmed_plan_revision",
                    PlanConsequenceBatch.status.in_({"temporarily_failed", "permanently_failed"}),
                )
                .count()
            )
        return {
            "revisions": len(revision_ids),
            "processed": len(due_task_ids),
            "problems": derivation_problems + failed_batches + remaining_problems,
        }

    def retry_revision(self, revision_id: int) -> dict[str, Any]:
        """Retry only missing or failed current effects for one revision."""
        current = _now()
        with session_scope(self.db_path) as session:
            revision = session.get(ConfirmedPlanRevision, revision_id)
            if revision is None:
                raise ValueError("Confirmed plan revision not found")
            exam_round = session.get(ExamRound, revision.exam_round_id)
            if exam_round is None:
                raise ValueError("Exam round not found")
            round_id = revision.exam_round_id
            resulting_revision = revision.resulting_revision
            batch = session.scalar(
                select(PlanConsequenceBatch).where(
                    PlanConsequenceBatch.confirmed_plan_revision_id == revision_id
                )
            )
            if batch is not None:
                batch.status = "pending"
                batch.next_attempt_at = None
                batch.error_code = None
                batch.updated_at = _timestamp(current)
                tasks = session.scalars(
                    select(PlanConsequence).where(
                        PlanConsequence.batch_id == batch.id,
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
        with session_scope(self.db_path) as session:
            window = list(
                session.scalars(
                    select(ConfirmedPlanRevision.id)
                    .where(
                        ConfirmedPlanRevision.exam_round_id == round_id,
                        ConfirmedPlanRevision.resulting_revision >= resulting_revision,
                    )
                    .order_by(ConfirmedPlanRevision.resulting_revision)
                )
            )
        batch_ids = [self._derive_revision(item, current) for item in window]
        self._reconcile_round(round_id, current)
        for batch_id in batch_ids:
            self._process_tasks(batch_id=batch_id, current=current)
        return self._summary(revision_id)

    def list_for_round(self, round_id: int) -> list[dict[str, Any]]:
        """Return recipient-specific status for chair and deputy views."""
        with session_scope(self.db_path) as session:
            rows = session.execute(
                select(PlanConsequence, PlanConsequenceBatch, ConfirmedPlanRevision)
                .join(PlanConsequenceBatch, PlanConsequenceBatch.id == PlanConsequence.batch_id)
                .join(
                    ConfirmedPlanRevision,
                    ConfirmedPlanRevision.id == PlanConsequenceBatch.confirmed_plan_revision_id,
                )
                .where(ConfirmedPlanRevision.exam_round_id == round_id)
                .order_by(
                    ConfirmedPlanRevision.resulting_revision.desc(),
                    PlanConsequence.id,
                )
            ).all()
            return [self._task_view(task, batch, revision) for task, batch, revision in rows]

    def operator_status(self, revision_id: int) -> dict[str, int | str | None]:
        """Expose technical identifiers and counts, never notification details."""
        return self._summary(revision_id)

    def _derive_revision(self, revision_id: int, current: datetime) -> int:
        with session_scope(self.db_path) as session:
            revision = session.get(ConfirmedPlanRevision, revision_id)
            if revision is None:
                raise ValueError("Confirmed plan revision not found")
            batch = session.scalar(
                select(PlanConsequenceBatch).where(
                    PlanConsequenceBatch.confirmed_plan_revision_id == revision_id
                )
            )
            if batch is None:
                batch = PlanConsequenceBatch(
                    origin_type="confirmed_plan_revision",
                    origin_key=str(revision_id),
                    confirmed_plan_revision_id=revision_id,
                )
                try:
                    with session.begin_nested():
                        session.add(batch)
                        session.flush()
                except IntegrityError:
                    batch = session.scalar(
                        select(PlanConsequenceBatch).where(
                            PlanConsequenceBatch.confirmed_plan_revision_id == revision_id
                        )
                    )
                    if batch is None:
                        raise
            try:
                before = json.loads(revision.before_state_json)
                after = json.loads(revision.after_state_json)
                derived, notification_scope = self._derive_tasks(session, revision, before, after)
                batch.notification_scope_json = json.dumps(sorted(notification_scope))
                for item in derived:
                    existing = session.scalar(
                        select(PlanConsequence.id).where(
                            PlanConsequence.batch_id == batch.id,
                            PlanConsequence.recipient_member_id == item["recipient_member_id"],
                            PlanConsequence.consequence_type == item["consequence_type"],
                            PlanConsequence.identity_key == item["identity_key"],
                        )
                    )
                    if existing is None:
                        try:
                            with session.begin_nested():
                                session.add(PlanConsequence(batch_id=batch.id, **item))
                                session.flush()
                        except IntegrityError:
                            pass
                batch.status = "succeeded"
                batch.attempt_count += 1
                batch.next_attempt_at = None
                batch.error_code = None
                batch.updated_at = _timestamp(current)
                session.flush()
                return batch.id
            except KeyError, TypeError, ValueError, json.JSONDecodeError:
                batch.attempt_count += 1
                batch.status = "permanently_failed"
                batch.next_attempt_at = None
                batch.error_code = "invalid_revision_snapshot"
                batch.updated_at = _timestamp(current)
                session.flush()
                return batch.id

    def _derive_tasks(
        self,
        session,
        revision: ConfirmedPlanRevision,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], set[int]]:
        old_assignments = self._assignments(before)
        new_assignments = self._assignments(after)
        calendar_tasks: list[dict[str, Any]] = []
        notices: dict[int, set[str]] = defaultdict(set)
        personnel_days: set[int] = set()

        for assignment_id in sorted(set(old_assignments) | set(new_assignments)):
            old = old_assignments.get(assignment_id)
            new = new_assignments.get(assignment_id)
            if old is None or new is None:
                raise ValueError("Confirmed plan assignment identity changed")
            old_member = int(old["committee_member_id"])
            new_member = int(new["committee_member_id"])
            if old_member != new_member:
                personnel_days.update({int(old["day_id"]), int(new["day_id"])})
                notices[old_member].add("removed")
                notices[new_member].add("added")
                calendar_tasks.extend(
                    (
                        self._calendar_task(old_member, assignment_id, "cancel"),
                        self._calendar_task(new_member, assignment_id, "create"),
                    )
                )
            elif self._calendar_signature(old) != self._calendar_signature(new):
                notices[new_member].add("changed")
                calendar_tasks.append(self._calendar_task(new_member, assignment_id, "update"))

        if personnel_days:
            old_by_day = self._members_by_day(old_assignments)
            new_by_day = self._members_by_day(new_assignments)
            for day_id in personnel_days:
                for member_id in old_by_day[day_id] & new_by_day[day_id]:
                    notices[member_id].add("crew_changed")

        if notices:
            exam_round = session.get(ExamRound, revision.exam_round_id)
            if exam_round is None:
                raise ValueError("Exam round not found")
            managers = session.scalars(
                select(CommitteeMember).where(
                    CommitteeMember.committee_id == exam_round.committee_id,
                    CommitteeMember.is_active == 1,
                    CommitteeMember.committee_role.in_({"chair", "deputy_chair"}),
                )
            ).all()
            for manager in managers:
                notices[manager.id].add("overview")

        notification_scope = set(notices)
        tasks = calendar_tasks
        for member_id, categories in sorted(notices.items()):
            if member_id == revision.actor_member_id:
                continue
            tasks.append(
                {
                    "recipient_member_id": member_id,
                    "consequence_type": "notification",
                    "action": "notify",
                    "identity_key": f"member:{member_id}",
                    "details_json": json.dumps(
                        {"categories": sorted(categories)},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )
        return tasks, notification_scope

    @staticmethod
    def _assignments(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        for day in payload["exam_days"]:
            slots = list(day["slots"])
            for assignment in day["assignments"]:
                assignment_id = int(assignment["id"])
                day_part = str(assignment["day_part"])
                section = slots
                if day_part != "full_day":
                    section = [
                        slot
                        for slot in slots
                        if (str(slot["starts_at"])[11:16] < "12:00") == (day_part == "morning")
                    ]
                if not section:
                    raise ValueError("Assignment has no calendar section")
                result[assignment_id] = {
                    **assignment,
                    "day_id": int(day["id"]),
                    "date": day["date"],
                    "room_id": int(day["room_id"]),
                    "starts_at": min(str(slot["starts_at"]) for slot in section),
                    "ends_at": max(str(slot["ends_at"]) for slot in section),
                }
        return result

    @staticmethod
    def _calendar_signature(assignment: dict[str, Any]) -> tuple[Any, ...]:
        return (
            assignment["committee_member_id"],
            assignment["day_id"],
            assignment["date"],
            assignment["room_id"],
            assignment["assignment_role"],
            assignment["day_part"],
            assignment["starts_at"],
            assignment["ends_at"],
        )

    @staticmethod
    def _members_by_day(assignments: dict[int, dict[str, Any]]) -> dict[int, set[int]]:
        by_day: dict[int, set[int]] = defaultdict(set)
        for assignment in assignments.values():
            by_day[int(assignment["day_id"])].add(int(assignment["committee_member_id"]))
        return by_day

    @staticmethod
    def _calendar_task(member_id: int, assignment_id: int, action: str) -> dict[str, Any]:
        return {
            "recipient_member_id": member_id,
            "consequence_type": "calendar",
            "action": action,
            "identity_key": f"assignment:{assignment_id}",
            "details_json": json.dumps({"assignment_id": assignment_id}, separators=(",", ":")),
        }

    def _supersede_older(self, revision_id: int, current: datetime) -> None:
        with session_scope(self.db_path) as session:
            revision = session.get(ConfirmedPlanRevision, revision_id)
            if revision is None:
                return
            current_batch = session.scalar(
                select(PlanConsequenceBatch).where(
                    PlanConsequenceBatch.confirmed_plan_revision_id == revision_id
                )
            )
            if current_batch is None:
                return
            notification_scope = set(json.loads(current_batch.notification_scope_json))
            calendar_keys = set(
                session.scalars(
                    select(PlanConsequence.identity_key).where(
                        PlanConsequence.batch_id == current_batch.id,
                        PlanConsequence.consequence_type == "calendar",
                    )
                )
            )
            if not notification_scope and not calendar_keys:
                return
            older_rows = session.execute(
                select(PlanConsequence, ConfirmedPlanRevision)
                .join(PlanConsequenceBatch, PlanConsequenceBatch.id == PlanConsequence.batch_id)
                .join(
                    ConfirmedPlanRevision,
                    ConfirmedPlanRevision.id == PlanConsequenceBatch.confirmed_plan_revision_id,
                )
                .where(
                    ConfirmedPlanRevision.exam_round_id == revision.exam_round_id,
                    ConfirmedPlanRevision.resulting_revision < revision.resulting_revision,
                    PlanConsequence.status.in_(
                        {"pending", "temporarily_failed", "permanently_failed"}
                    ),
                    or_(
                        (
                            (PlanConsequence.consequence_type == "notification")
                            & PlanConsequence.recipient_member_id.in_(notification_scope)
                        ),
                        (
                            (PlanConsequence.consequence_type == "calendar")
                            & PlanConsequence.identity_key.in_(calendar_keys)
                        ),
                    ),
                )
            ).all()
            for task, _older_revision in older_rows:
                task.status = "superseded"
                task.next_attempt_at = None
                task.error_code = "superseded_by_newer_revision"
                task.updated_at = _timestamp(current)

    def _reconcile_round(self, round_id: int, current: datetime) -> None:
        with session_scope(self.db_path) as session:
            revision_ids = list(
                session.scalars(
                    select(ConfirmedPlanRevision.id)
                    .join(
                        PlanConsequenceBatch,
                        PlanConsequenceBatch.confirmed_plan_revision_id == ConfirmedPlanRevision.id,
                    )
                    .where(ConfirmedPlanRevision.exam_round_id == round_id)
                    .order_by(ConfirmedPlanRevision.resulting_revision)
                )
            )
        for revision_id in revision_ids:
            self._supersede_older(revision_id, current)

    def _round_id(self, revision_id: int) -> int:
        with session_scope(self.db_path) as session:
            revision = session.get(ConfirmedPlanRevision, revision_id)
            if revision is None:
                raise ValueError("Confirmed plan revision not found")
            return revision.exam_round_id

    def _process_tasks(self, *, batch_id: int | None, current: datetime) -> None:
        with session_scope(self.db_path) as session:
            statement = (
                select(PlanConsequence.id)
                .join(PlanConsequenceBatch)
                .where(
                    PlanConsequenceBatch.origin_type == "confirmed_plan_revision",
                    PlanConsequence.status.in_({"pending", "temporarily_failed"}),
                    (
                        PlanConsequence.next_attempt_at.is_(None)
                        | (PlanConsequence.next_attempt_at <= _timestamp(current))
                    ),
                )
            )
            if batch_id is not None:
                statement = statement.where(PlanConsequence.batch_id == batch_id)
            task_ids = list(session.scalars(statement.order_by(PlanConsequence.id)))
        calendar_ids: list[int] = []
        for task_id in task_ids:
            with session_scope(self.db_path) as session:
                task = session.get(PlanConsequence, task_id)
                if task is None:
                    continue
                if task.consequence_type == "calendar":
                    calendar_ids.append(task_id)
                    continue
            self._process_notification(task_id, current)
        if calendar_ids:
            self._process_calendars(calendar_ids, current)

    def _process_notification(self, task_id: int, current: datetime) -> None:
        with session_scope(self.db_path) as session:
            loaded = self._load_task_context(session, task_id)
            if loaded is None:
                return
            task, _batch, revision, exam_round = loaded
            details = json.loads(task.details_json)
            categories = set(details.get("categories", []))
            member_id = task.recipient_member_id
            round_id = revision.exam_round_id
            revision_id = revision.id
            committee_id = exam_round.committee_id
        try:
            superseded_notice_ids = self.notifications.supersede_unsent_plan_changes(
                round_id=round_id,
                recipient_member_id=member_id,
                newer_revision_id=revision_id,
            )
            self._mark_superseded_notification_tasks(
                superseded_notice_ids,
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
        with session_scope(self.db_path) as session:
            task = session.get(PlanConsequence, task_id)
            if task is not None:
                task.status = "succeeded"
                task.attempt_count += 1
                task.next_attempt_at = None
                task.error_code = None
                task.updated_at = _timestamp(current)

    def _mark_superseded_notification_tasks(
        self,
        notification_ids: set[int],
        current: datetime,
    ) -> None:
        if not notification_ids:
            return
        with session_scope(self.db_path) as session:
            notices = session.scalars(
                select(Notification).where(Notification.id.in_(notification_ids))
            ).all()
            revision_ids = set()
            for notice in notices:
                parts = notice.origin_key.split(":")
                if len(parts) >= 3 and parts[0] == "confirmed-plan-revision":
                    try:
                        revision_ids.add(int(parts[1]))
                    except ValueError:
                        continue
            if not revision_ids:
                return
            tasks = session.scalars(
                select(PlanConsequence)
                .join(PlanConsequenceBatch)
                .where(
                    PlanConsequenceBatch.confirmed_plan_revision_id.in_(revision_ids),
                    PlanConsequence.consequence_type == "notification",
                    PlanConsequence.status == "succeeded",
                )
            ).all()
            for task in tasks:
                self._mark_superseded(task, current)

    def _process_calendars(self, task_ids: list[int], current: datetime) -> None:
        by_round: dict[int, list[int]] = defaultdict(list)
        with session_scope(self.db_path) as session:
            for task_id in task_ids:
                loaded = self._load_task_context(session, task_id)
                if loaded is None:
                    continue
                task, _batch, revision, exam_round = loaded
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

    def _complete_calendar_task(self, task_id: int, current: datetime) -> None:
        with session_scope(self.db_path) as session:
            task = session.get(PlanConsequence, task_id)
            if task is None:
                return
            assignment_id = int(json.loads(task.details_json)["assignment_id"])
            prefix = f"assignment:{assignment_id}"
            event = session.scalars(
                select(CalendarEvent)
                .where(
                    CalendarEvent.recipient_member_id == task.recipient_member_id,
                    (
                        (CalendarEvent.source_key == prefix)
                        | CalendarEvent.source_key.like(f"{prefix}:%")
                    ),
                )
                .order_by(CalendarEvent.id.desc())
            ).first()
            valid = (
                task.action == "cancel" and (event is None or event.status == "cancelled")
            ) or (
                task.action in {"create", "update"}
                and event is not None
                and event.status != "cancelled"
            )
            if not valid:
                self._apply_failure(task, "calendar_state_missing", current)
                return
            task.status = "succeeded"
            task.attempt_count += 1
            task.next_attempt_at = None
            task.error_code = None
            task.calendar_event_id = event.id if event is not None else None
            task.calendar_event_version = event.version if event is not None else None
            task.updated_at = _timestamp(current)

    def _fail_task(self, task_id: int, code: str, current: datetime) -> None:
        with session_scope(self.db_path) as session:
            task = session.get(PlanConsequence, task_id)
            if task is not None:
                self._apply_failure(task, code, current)

    @staticmethod
    def _apply_failure(task: PlanConsequence, code: str, current: datetime) -> None:
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
    def _mark_superseded(task: PlanConsequence, current: datetime) -> None:
        task.status = "superseded"
        task.next_attempt_at = None
        task.error_code = "superseded_by_newer_revision"
        task.updated_at = _timestamp(current)

    @staticmethod
    def _load_task_context(session, task_id: int):
        return session.execute(
            select(
                PlanConsequence,
                PlanConsequenceBatch,
                ConfirmedPlanRevision,
                ExamRound,
            )
            .join(PlanConsequenceBatch, PlanConsequenceBatch.id == PlanConsequence.batch_id)
            .join(
                ConfirmedPlanRevision,
                ConfirmedPlanRevision.id == PlanConsequenceBatch.confirmed_plan_revision_id,
            )
            .join(ExamRound, ExamRound.id == ConfirmedPlanRevision.exam_round_id)
            .where(PlanConsequence.id == task_id)
        ).first()

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
        with session_scope(self.db_path) as session:
            batch = session.scalar(
                select(PlanConsequenceBatch).where(
                    PlanConsequenceBatch.confirmed_plan_revision_id == revision_id
                )
            )
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
            tasks = session.scalars(
                select(PlanConsequence).where(PlanConsequence.batch_id == batch.id)
            ).all()
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
        task: PlanConsequence,
        batch: PlanConsequenceBatch,
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
