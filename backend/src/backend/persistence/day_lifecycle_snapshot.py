"""SQLite adapter for detached exam-day lifecycle transition facts."""

from __future__ import annotations

import json
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.models import ExamDay, ExamDayClosure, ExamDayReopening


class _ExamDayLifecycleSnapshot(NamedTuple):
    day: dict[str, object]
    closure_fingerprints: tuple[str, ...]
    reopenings: tuple[dict[str, object], ...]


class SQLiteExamDayLifecycleSnapshotReader:
    """Materialize the small transition projection without leaking ORM rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_exam_day_lifecycle_snapshot(self, day_id: int) -> _ExamDayLifecycleSnapshot | None:
        day = self._session.get(ExamDay, day_id)
        if day is None:
            return None
        closures = tuple(
            item.command_fingerprint
            for item in self._session.scalars(
                select(ExamDayClosure).where(ExamDayClosure.exam_day_id == day_id)
            )
        )
        reopenings = tuple(
            {
                "id": item.id,
                "status": item.status,
                "command_fingerprint": item.command_fingerprint,
                "requested_scope": json.loads(item.requested_scope_json),
                "completed_scope": json.loads(item.completed_scope_json),
            }
            for item in self._session.scalars(
                select(ExamDayReopening).where(ExamDayReopening.exam_day_id == day_id)
            )
        )
        return _ExamDayLifecycleSnapshot(
            {
                "id": day.id,
                "exam_round_id": day.exam_round_id,
                "revision": day.revision,
                "closure_status": day.closure_status,
            },
            closures,
            reopenings,
        )
