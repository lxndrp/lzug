"""SQLite adapter for Application-owned consequence state transitions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from backend.persistence.application_consequence_ports import (
    ConsequenceBatchSnapshot,
    ConsequenceTaskSnapshot,
)
from backend.persistence.application_consequences import PlanConsequence, PlanConsequenceBatch
from backend.persistence.database import DEFAULT_DB_PATH, session_scope


class SQLiteApplicationConsequenceStore:
    """Persist Application follow-up state without exposing ORM values."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def claim_task(self, task_id: int, *, now: str, lease_until: str) -> bool:
        with session_scope(self.db_path) as session:
            result = session.execute(
                update(PlanConsequence)
                .where(
                    PlanConsequence.id == task_id,
                    PlanConsequence.status.in_({"pending", "temporarily_failed"}),
                    or_(
                        PlanConsequence.next_attempt_at.is_(None),
                        PlanConsequence.next_attempt_at <= now,
                    ),
                )
                .values(status="pending", next_attempt_at=lease_until, updated_at=now)
            )
            return result.rowcount == 1

    def due_task_ids(
        self,
        *,
        origin_type: str,
        now: str,
        batch_id: int | None = None,
    ) -> tuple[int, ...]:
        statement = (
            select(PlanConsequence.id)
            .join(PlanConsequenceBatch)
            .where(
                PlanConsequenceBatch.origin_type == origin_type,
                PlanConsequence.status.in_({"pending", "temporarily_failed"}),
                or_(
                    PlanConsequence.next_attempt_at.is_(None),
                    PlanConsequence.next_attempt_at <= now,
                ),
            )
        )
        if batch_id is not None:
            statement = statement.where(PlanConsequence.batch_id == batch_id)
        with session_scope(self.db_path) as session:
            return tuple(session.scalars(statement.order_by(PlanConsequence.id)))

    def due_revision_ids(self, revision_ids: tuple[int, ...], *, now: str) -> tuple[int, ...]:
        if not revision_ids:
            return ()
        with session_scope(self.db_path) as session:
            batches = session.execute(
                select(
                    PlanConsequenceBatch.confirmed_plan_revision_id,
                    PlanConsequenceBatch.status,
                    PlanConsequenceBatch.next_attempt_at,
                ).where(PlanConsequenceBatch.confirmed_plan_revision_id.in_(revision_ids))
            )
            by_revision = {
                revision_id: (status, next_attempt_at)
                for revision_id, status, next_attempt_at in batches
            }
        return tuple(
            revision_id
            for revision_id in revision_ids
            if revision_id not in by_revision
            or (
                by_revision[revision_id][0] in {"pending", "temporarily_failed"}
                and (by_revision[revision_id][1] is None or by_revision[revision_id][1] <= now)
            )
        )

    def record_batch(
        self,
        *,
        origin_type: str,
        origin_key: str,
        confirmed_plan_revision_id: int | None,
        notification_scope: tuple[int, ...],
        tasks: tuple[Mapping[str, Any], ...],
        error_code: str | None,
        now: str,
    ) -> int:
        with session_scope(self.db_path) as session:
            batch = session.scalar(
                select(PlanConsequenceBatch).where(
                    PlanConsequenceBatch.origin_type == origin_type,
                    PlanConsequenceBatch.origin_key == origin_key,
                )
            )
            if batch is None:
                batch = PlanConsequenceBatch(
                    origin_type=origin_type,
                    origin_key=origin_key,
                    confirmed_plan_revision_id=confirmed_plan_revision_id,
                )
                try:
                    with session.begin_nested():
                        session.add(batch)
                        session.flush()
                except IntegrityError:
                    batch = session.scalar(
                        select(PlanConsequenceBatch).where(
                            PlanConsequenceBatch.origin_type == origin_type,
                            PlanConsequenceBatch.origin_key == origin_key,
                        )
                    )
                    if batch is None:
                        raise
            if error_code is None:
                batch.notification_scope_json = json.dumps(list(notification_scope))
                for task in tasks:
                    exists = session.scalar(
                        select(PlanConsequence.id).where(
                            PlanConsequence.batch_id == batch.id,
                            PlanConsequence.recipient_member_id == task["recipient_member_id"],
                            PlanConsequence.consequence_type == task["consequence_type"],
                            PlanConsequence.identity_key == task["identity_key"],
                        )
                    )
                    if exists is not None:
                        continue
                    try:
                        with session.begin_nested():
                            session.add(
                                PlanConsequence(
                                    batch_id=batch.id,
                                    recipient_member_id=task["recipient_member_id"],
                                    consequence_type=task["consequence_type"],
                                    action=task["action"],
                                    identity_key=task["identity_key"],
                                    details_json=task["details_json"],
                                )
                            )
                            session.flush()
                    except IntegrityError:
                        pass
                batch.status = "succeeded"
                batch.next_attempt_at = None
                batch.error_code = None
            else:
                batch.status = "permanently_failed"
                batch.next_attempt_at = None
                batch.error_code = error_code
            batch.attempt_count += 1
            batch.updated_at = now
            session.flush()
            return batch.id

    def batch_by_origin(self, origin_type: str, origin_key: str) -> ConsequenceBatchSnapshot | None:
        with session_scope(self.db_path) as session:
            batch = session.scalar(
                select(PlanConsequenceBatch).where(
                    PlanConsequenceBatch.origin_type == origin_type,
                    PlanConsequenceBatch.origin_key == origin_key,
                )
            )
            return self._batch_snapshot(batch) if batch is not None else None

    def batches_by_origin(
        self, origin_type: str, *, excluding_origin_key: str | None = None
    ) -> tuple[ConsequenceBatchSnapshot, ...]:
        statement = select(PlanConsequenceBatch).where(
            PlanConsequenceBatch.origin_type == origin_type
        )
        if excluding_origin_key is not None:
            statement = statement.where(PlanConsequenceBatch.origin_key != excluding_origin_key)
        with session_scope(self.db_path) as session:
            return tuple(
                self._batch_snapshot(batch)
                for batch in session.scalars(statement.order_by(PlanConsequenceBatch.id))
            )

    def task(self, task_id: int) -> ConsequenceTaskSnapshot | None:
        with session_scope(self.db_path) as session:
            task = session.get(PlanConsequence, task_id)
            if task is None:
                return None
            batch = session.get(PlanConsequenceBatch, task.batch_id)
            return self._task_snapshot(task, batch) if batch is not None else None

    def tasks_for_batch(
        self, batch_id: int, *, statuses: frozenset[str] | None = None
    ) -> tuple[ConsequenceTaskSnapshot, ...]:
        statement = (
            select(PlanConsequence, PlanConsequenceBatch)
            .join(PlanConsequenceBatch, PlanConsequenceBatch.id == PlanConsequence.batch_id)
            .where(PlanConsequence.batch_id == batch_id)
        )
        if statuses is not None:
            statement = statement.where(PlanConsequence.status.in_(statuses))
        with session_scope(self.db_path) as session:
            return tuple(
                self._task_snapshot(task, batch)
                for task, batch in session.execute(statement.order_by(PlanConsequence.id))
            )

    def set_batch_state(
        self,
        batch_id: int,
        *,
        status: str,
        attempt_count: int,
        next_attempt_at: str | None,
        error_code: str | None,
        updated_at: str,
    ) -> None:
        with session_scope(self.db_path) as session:
            batch = session.get(PlanConsequenceBatch, batch_id)
            if batch is None:
                return
            batch.status = status
            batch.attempt_count = attempt_count
            batch.next_attempt_at = next_attempt_at
            batch.error_code = error_code
            batch.updated_at = updated_at

    def set_task_state(
        self,
        task_id: int,
        *,
        status: str,
        attempt_count: int,
        next_attempt_at: str | None,
        error_code: str | None,
        calendar_event_id: int | None,
        calendar_event_version: int | None,
        updated_at: str,
        expected_claim_until: str | None = None,
    ) -> bool:
        with session_scope(self.db_path) as session:
            statement = update(PlanConsequence).where(PlanConsequence.id == task_id)
            if expected_claim_until is not None:
                statement = statement.where(
                    PlanConsequence.status == "pending",
                    PlanConsequence.next_attempt_at == expected_claim_until,
                )
            result = session.execute(
                statement.values(
                    status=status,
                    attempt_count=attempt_count,
                    next_attempt_at=next_attempt_at,
                    error_code=error_code,
                    calendar_event_id=calendar_event_id,
                    calendar_event_version=calendar_event_version,
                    updated_at=updated_at,
                )
            )
            return result.rowcount == 1

    @staticmethod
    def _batch_snapshot(batch: PlanConsequenceBatch) -> ConsequenceBatchSnapshot:
        return ConsequenceBatchSnapshot(
            id=batch.id,
            origin_type=batch.origin_type,
            origin_key=batch.origin_key,
            confirmed_plan_revision_id=batch.confirmed_plan_revision_id,
            notification_scope_json=batch.notification_scope_json,
            status=batch.status,
            attempt_count=batch.attempt_count,
            next_attempt_at=batch.next_attempt_at,
            error_code=batch.error_code,
            updated_at=batch.updated_at,
        )

    @staticmethod
    def _task_snapshot(
        task: PlanConsequence, batch: PlanConsequenceBatch
    ) -> ConsequenceTaskSnapshot:
        return ConsequenceTaskSnapshot(
            id=task.id,
            batch_id=task.batch_id,
            origin_type=batch.origin_type,
            origin_key=batch.origin_key,
            recipient_member_id=task.recipient_member_id,
            consequence_type=task.consequence_type,
            action=task.action,
            identity_key=task.identity_key,
            details_json=task.details_json,
            status=task.status,
            attempt_count=task.attempt_count,
            next_attempt_at=task.next_attempt_at,
            error_code=task.error_code,
            calendar_event_id=task.calendar_event_id,
            calendar_event_version=task.calendar_event_version,
            updated_at=task.updated_at,
        )
