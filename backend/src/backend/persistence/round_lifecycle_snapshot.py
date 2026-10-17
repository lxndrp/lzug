"""SQLite adapter for the round lifecycle read snapshot port."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from backend.execution.round_lifecycle_snapshot import ExamRoundLifecycleReadSnapshot

from backend.persistence.models import (
    AbsenceReport,
    ExamDay,
    ExamDayClosure,
    ExamDayTask,
    ExamProtocol,
    ExamProtocolCorrectionRequest,
    ExamProtocolRetention,
    ExamRoundAuditEvent,
    ExamRoundDecision,
    ExamRoundExport,
    ExamRoundIhkStatus,
    ExamRoundReopening,
    ExamRoundTask,
    ExamSlot,
)


class _RoundLifecycleReadSnapshot(NamedTuple):
    records: dict[str, object]


class SQLiteExamRoundLifecycleReadSnapshotReader:
    """Map a caller-owned session to plain Python round lifecycle records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_round_lifecycle_read_snapshot(
        self, round_id: int
    ) -> ExamRoundLifecycleReadSnapshot | None:
        days = list(
            self._session.scalars(
                select(ExamDay).where(ExamDay.exam_round_id == round_id).order_by(ExamDay.id)
            )
        )
        day_ids = [item.id for item in days]
        slots = (
            self._session.execute(
                select(
                    ExamProtocol.id,
                    ExamProtocol.exam_slot_id,
                    ExamProtocol.current_version,
                    ExamProtocolRetention.exam_protocol_id.label("retention_protocol_id"),
                    ExamProtocolRetention.retain_until,
                    ExamProtocolRetention.legal_hold,
                    ExamProtocolRetention.hold_reason,
                )
                .outerjoin(
                    ExamProtocolRetention, ExamProtocolRetention.exam_protocol_id == ExamProtocol.id
                )
                .join(ExamSlot, ExamSlot.id == ExamProtocol.exam_slot_id)
                .where(ExamSlot.exam_day_id.in_(day_ids))
                .order_by(ExamProtocol.id)
            ).all()
            if day_ids
            else []
        )
        protocol_ids = [row.id for row in slots]
        records: dict[str, object] = {
            "decisions": tuple(
                _model_row(item, ("checklist_json", "snapshot_json"))
                for item in self._session.scalars(
                    select(ExamRoundDecision)
                    .where(ExamRoundDecision.exam_round_id == round_id)
                    .order_by(ExamRoundDecision.id)
                )
            ),
            "reopenings": tuple(
                _model_row(item, ("requested_scope_json", "scope_json", "impacts_json"))
                for item in self._session.scalars(
                    select(ExamRoundReopening)
                    .where(ExamRoundReopening.exam_round_id == round_id)
                    .order_by(ExamRoundReopening.id)
                )
            ),
            "history": tuple(
                _model_row(item, ("scope_json",))
                for item in self._session.scalars(
                    select(ExamRoundAuditEvent)
                    .where(ExamRoundAuditEvent.exam_round_id == round_id)
                    .order_by(ExamRoundAuditEvent.id)
                )
            ),
            "tasks": tuple(
                _model_row(item, ("details_json",))
                for item in self._session.scalars(
                    select(ExamRoundTask)
                    .where(ExamRoundTask.exam_round_id == round_id)
                    .order_by(ExamRoundTask.id)
                )
            ),
            "exports": tuple(
                _model_row(item, ())
                for item in self._session.scalars(
                    select(ExamRoundExport)
                    .where(ExamRoundExport.exam_round_id == round_id)
                    .order_by(ExamRoundExport.id)
                )
            ),
            "ihk_statuses": tuple(
                _model_row(item, ())
                for item in self._session.scalars(
                    select(ExamRoundIhkStatus)
                    .where(ExamRoundIhkStatus.exam_round_id == round_id)
                    .order_by(ExamRoundIhkStatus.id)
                )
            ),
            "days": tuple({"id": d.id, "closure_status": d.closure_status} for d in days),
            "current_closure_day_ids": (
                tuple(
                    self._session.scalars(
                        select(ExamDayClosure.exam_day_id).where(
                            ExamDayClosure.exam_day_id.in_(day_ids),
                            ExamDayClosure.status == "current",
                        )
                    )
                )
                if day_ids
                else ()
            ),
            "follow_up_task_ids": (
                tuple(
                    self._session.scalars(
                        select(ExamDayTask.id).where(
                            ExamDayTask.exam_day_id.in_(day_ids),
                            ExamDayTask.task_type == "protocol_follow_up",
                            ExamDayTask.status == "open",
                        )
                    )
                )
                if day_ids
                else ()
            ),
            "absences": (
                tuple(
                    _model_row(item, ())
                    for item in self._session.scalars(
                        select(AbsenceReport)
                        .where(AbsenceReport.exam_day_id.in_(day_ids))
                        .order_by(AbsenceReport.id)
                    )
                )
                if day_ids
                else ()
            ),
            "protocol_correction_ids": (),
            "protocol_retention": tuple(
                {
                    "kind": "protocol",
                    "id": row.id,
                    "retain_until": row.retain_until,
                    "legal_hold": bool(row.legal_hold),
                    "hold_reason": row.hold_reason,
                }
                for row in slots
                if row.retention_protocol_id is not None
            ),
        }
        if protocol_ids:
            records["protocol_correction_ids"] = tuple(
                self._session.scalars(
                    select(ExamProtocolCorrectionRequest.id)
                    .where(
                        ExamProtocolCorrectionRequest.exam_protocol_id.in_(protocol_ids),
                        ExamProtocolCorrectionRequest.status.in_({"requested", "opened"}),
                    )
                    .order_by(ExamProtocolCorrectionRequest.id)
                )
            )
        return _RoundLifecycleReadSnapshot(records)


def _model_row(item, json_fields: tuple[str, ...]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in item.__table__.columns.keys():
        value = getattr(item, name)
        result[name] = json.loads(value) if name in json_fields else value
    return result
