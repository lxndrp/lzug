"""SQLite implementations of transaction-bound execution day mutations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models import (
    ExamDay,
    ExamDayAuditEvent,
    ExamDayReopening,
    ExamDayTask,
)

POST_CLOSE_RESULT_KINDS = {
    "result_external",
    "result_determine",
    "result_confirm_record",
    "result_communicate",
    "result_retention",
}


class ExecutionDayMutationConflictError(ValueError):
    """Signal a stale or disallowed day mutation at the persistence adapter boundary."""


def _domain_mutation_token(kind: str, entity_id: int) -> str:
    if kind in {"protocol_response", "protocol_correction_request"}:
        kind = "exam_protocol"
    elif kind.startswith("result_"):
        kind = "exam_result"
    return f"{kind}:{entity_id}"


def _supplied_day_revision(payload: dict[str, Any], day_id: int) -> object | None:
    revisions = payload.get("day_revisions")
    if isinstance(revisions, dict):
        return revisions.get(str(day_id), revisions.get(day_id))
    return payload.get("day_revision")


@dataclass(frozen=True)
class DayMutationGuard:
    """Persistence-local state needed to finish a guarded day mutation."""

    day: ExamDay
    token: str
    reopening: ExamDayReopening | None
    touch_revision: bool
    late_protocol_response: bool = False


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def guard_day_mutation(
    session: Session,
    *,
    day: ExamDay,
    kind: str,
    entity_id: int,
    payload: dict[str, Any] | None = None,
    expected_day_revision: object | None = None,
    actor_member_id: int | None,
    protocol_revision_id: int | None = None,
) -> DayMutationGuard:
    """Check revision, closure, and reopening rules in the caller's transaction."""
    token = _domain_mutation_token(kind, entity_id)
    supplied = (
        _supplied_day_revision(payload, day.id) if payload is not None else expected_day_revision
    )
    if day.closure_status == "open":
        return _guard_open_day_mutation(day, token, supplied)

    if kind in POST_CLOSE_RESULT_KINDS or kind == "protocol_correction_request":
        return DayMutationGuard(day, token, None, False)

    if day.closure_status == "closed_exception" and kind == "protocol_response":
        return _guard_late_protocol_response(
            session, day, token, actor_member_id, protocol_revision_id
        )
    return _guard_reopening_mutation(session, day, token, supplied)


def _guard_open_day_mutation(day: ExamDay, token: str, supplied: object | None) -> DayMutationGuard:
    if supplied is not None and supplied != day.revision:
        raise ExecutionDayMutationConflictError("Der Prüfungstag wurde zwischenzeitlich geändert")
    return DayMutationGuard(day, token, None, True)


def _guard_late_protocol_response(
    session: Session,
    day: ExamDay,
    token: str,
    actor_member_id: int | None,
    protocol_revision_id: int | None,
) -> DayMutationGuard:
    if actor_member_id is None or protocol_revision_id is None:
        raise PermissionError("Forbidden.")
    task = session.scalar(
        select(ExamDayTask).where(
            ExamDayTask.exam_day_id == day.id,
            ExamDayTask.task_type == "protocol_follow_up",
            ExamDayTask.recipient_member_id == actor_member_id,
            ExamDayTask.exam_protocol_revision_id == protocol_revision_id,
            ExamDayTask.status == "open",
        )
    )
    if task is None:
        raise ExecutionDayMutationConflictError(
            "Für diesen geschlossenen Protokollstand besteht keine offene Nachfassaufgabe"
        )
    return DayMutationGuard(day, token, None, False, late_protocol_response=True)


def _guard_reopening_mutation(
    session: Session, day: ExamDay, token: str, supplied: object | None
) -> DayMutationGuard:
    if day.closure_status != "reopening":
        raise ExecutionDayMutationConflictError(
            "Geschlossene Tagesdaten können nur über eine zielgerichtete "
            "Wiederöffnung geändert werden"
        )
    reopening = session.scalar(
        select(ExamDayReopening).where(
            ExamDayReopening.exam_day_id == day.id,
            ExamDayReopening.status == "open",
        )
    )
    if reopening is None:
        raise ExecutionDayMutationConflictError(
            "Der Wiederöffnungsstand des Prüfungstags ist inkonsistent"
        )
    if not isinstance(supplied, int) or isinstance(supplied, bool):
        raise ExecutionDayMutationConflictError(
            "Eine Korrektur benötigt die aktuelle Tagesrevision"
        )
    if supplied != day.revision:
        raise ExecutionDayMutationConflictError("Der Prüfungstag wurde zwischenzeitlich geändert")
    if token not in set(json.loads(reopening.scope_json)):
        raise ExecutionDayMutationConflictError(
            "Diese Daten gehören nicht zum ausdrücklich wieder geöffneten Korrekturumfang"
        )
    return DayMutationGuard(day, token, reopening, True)


def complete_day_mutation(
    session: Session,
    guard: DayMutationGuard,
    *,
    actor_member_id: int,
    reason: str | None = None,
    protocol_revision_id: int | None = None,
) -> None:
    """Complete a guarded mutation in the caller's transaction without committing."""
    now = _now()
    if guard.touch_revision:
        guard.day.revision += 1
        guard.day.updated_at = now
        if guard.reopening is not None:
            completed = set(json.loads(guard.reopening.completed_scope_json))
            completed.add(guard.token)
            guard.reopening.completed_scope_json = _json(sorted(completed))
            session.add(
                ExamDayAuditEvent(
                    exam_day_id=guard.day.id,
                    day_revision=guard.day.revision,
                    event_type="correction",
                    actor_member_id=actor_member_id,
                    reopening_id=guard.reopening.id,
                    reason=reason,
                    scope_json=_json([guard.token]),
                    created_at=now,
                )
            )
    if guard.late_protocol_response:
        task = session.scalar(
            select(ExamDayTask).where(
                ExamDayTask.exam_day_id == guard.day.id,
                ExamDayTask.task_type == "protocol_follow_up",
                ExamDayTask.recipient_member_id == actor_member_id,
                ExamDayTask.exam_protocol_revision_id == protocol_revision_id,
                ExamDayTask.status == "open",
            )
        )
        if task is not None:
            task.status = "completed"
            task.completed_at = now
        session.add(
            ExamDayAuditEvent(
                exam_day_id=guard.day.id,
                day_revision=guard.day.revision,
                event_type="late_protocol_response",
                actor_member_id=actor_member_id,
                reason=reason,
                scope_json=_json([guard.token]),
                created_at=now,
            )
        )
