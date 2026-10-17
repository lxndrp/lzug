"""SQLite adapter for the execution day-closure snapshot read contract."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from backend.execution.day_closure_snapshot import ExamDayClosureReadSnapshot

from backend.persistence.models import (
    ExamDay,
    ExamDayAuditEvent,
    ExamDayClosure,
    ExamDayExport,
    ExamDayReopening,
    ExamDayTask,
)


class _ExamDayClosureReadSnapshot(NamedTuple):
    day: dict[str, object]
    history: tuple[dict[str, object], ...]
    tasks: tuple[dict[str, object], ...]


class SQLiteExamDayClosureReadSnapshotReader:
    """Map a caller-owned SQLAlchemy session to detached closure read data."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_day_closure_read_snapshot(self, day_id: int) -> ExamDayClosureReadSnapshot | None:
        day = self._session.get(ExamDay, day_id)
        if day is None:
            return None
        history: list[dict[str, object]] = []
        for item in self._session.scalars(
            select(ExamDayClosure)
            .where(ExamDayClosure.exam_day_id == day_id)
            .order_by(ExamDayClosure.id)
        ):
            history.append(
                {
                    "kind": "closure",
                    "id": item.id,
                    "revision": item.resulting_revision,
                    "closure_type": item.closure_type,
                    "actor_member_id": item.actor_member_id,
                    "reason": item.reason,
                    "clarification_attempts": item.clarification_attempts,
                    "status": item.status,
                    "created_at": item.closed_at,
                    "checklist": json.loads(item.checklist_json),
                    "warnings": json.loads(item.warnings_json),
                    "protocol_references": json.loads(item.protocol_references_json),
                    "result_references": json.loads(item.result_references_json),
                }
            )
        for item in self._session.scalars(
            select(ExamDayReopening)
            .where(ExamDayReopening.exam_day_id == day_id)
            .order_by(ExamDayReopening.id)
        ):
            history.append(
                {
                    "kind": "reopening",
                    "id": item.id,
                    "revision": item.resulting_revision,
                    "actor_member_id": item.actor_member_id,
                    "occasion": item.occasion,
                    "source": item.source,
                    "reason": item.reason,
                    "requested_scope": json.loads(item.requested_scope_json),
                    "expanded_scope": json.loads(item.scope_json),
                    "completed_scope": json.loads(item.completed_scope_json),
                    "impacts": json.loads(item.impacts_json),
                    "status": item.status,
                    "created_at": item.opened_at,
                    "completed_at": item.completed_at,
                }
            )
        for item in self._session.scalars(
            select(ExamDayAuditEvent)
            .where(ExamDayAuditEvent.exam_day_id == day_id)
            .order_by(ExamDayAuditEvent.id)
        ):
            history.append(
                {
                    "kind": "audit",
                    "id": item.id,
                    "revision": item.day_revision,
                    "event_type": item.event_type,
                    "actor_member_id": item.actor_member_id,
                    "closure_id": item.closure_id,
                    "reopening_id": item.reopening_id,
                    "reason": item.reason,
                    "scope": json.loads(item.scope_json),
                    "created_at": item.created_at,
                }
            )
        for item in self._session.scalars(
            select(ExamDayExport)
            .where(ExamDayExport.exam_day_id == day_id)
            .order_by(ExamDayExport.id)
        ):
            history.append(
                {
                    "kind": "export",
                    "id": item.id,
                    "revision": day.revision,
                    "export_kind": item.export_kind,
                    "closure_id": item.closure_id,
                    "status": item.status,
                    "actor_member_id": item.generated_by_member_id,
                    "created_at": item.generated_at,
                }
            )
        history.sort(key=lambda item: (item["revision"], item["id"]))
        tasks = tuple(
            {
                "id": item.id,
                "reopening_id": item.reopening_id,
                "recipient_member_id": item.recipient_member_id,
                "task_type": item.task_type,
                "origin_key": item.origin_key,
                "exam_protocol_revision_id": item.exam_protocol_revision_id,
                "result_determination_id": item.result_determination_id,
                "details": json.loads(item.details_json),
                "status": item.status,
                "created_at": item.created_at,
                "completed_at": item.completed_at,
            }
            for item in self._session.scalars(
                select(ExamDayTask)
                .where(ExamDayTask.exam_day_id == day_id)
                .order_by(ExamDayTask.id)
            )
        )
        return _ExamDayClosureReadSnapshot(
            day={
                "id": day.id,
                "date": day.date,
                "exam_round_id": day.exam_round_id,
                "revision": day.revision,
                "closure_status": day.closure_status,
                "status": day.status,
            },
            history=tuple(history),
            tasks=tasks,
        )
