"""SQLite Unit of Work adapter for planning candidate-day generation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from backend.persistence.database import session_scope
from backend.persistence.models import CANDIDATE_EXAM_DAY, PLANNING_SETTINGS
from backend.persistence.store import Store

if TYPE_CHECKING:
    from backend.planning.candidate_days import (
        CandidateDayRecord,
        CandidateDaySettings,
        CandidateDayUnitOfWork,
    )


class _SQLiteCandidateDaySettings(NamedTuple):
    calendar_week_from: str
    calendar_week_to: str
    exclude_public_holidays: int
    holiday_subdivision_code: str | None


class _SQLiteCandidateDayRecord(NamedTuple):
    id: int
    round_id: int
    date: str
    is_active: int
    created_at: str
    updated_at: str


class SQLiteCandidateDayUnitOfWorkFactory:
    """Create one SQLite transaction for each candidate-day command."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def __call__(self) -> AbstractContextManager[CandidateDayUnitOfWork]:
        return self._unit_of_work()

    @contextmanager
    def _unit_of_work(self) -> Iterator[CandidateDayUnitOfWork]:
        with session_scope(self.db_path) as session:
            yield SQLiteCandidateDayUnitOfWork(Store(session))


class SQLiteCandidateDayUnitOfWork:
    """Map planning values onto the existing SQLite tables within one session."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def planning_settings(self, round_id: int) -> CandidateDaySettings | None:
        settings = self._store.first(PLANNING_SETTINGS, exam_round_id=round_id)
        if settings is None:
            return None
        return _SQLiteCandidateDaySettings(
            calendar_week_from=settings["calendar_week_from"],
            calendar_week_to=settings["calendar_week_to"],
            exclude_public_holidays=int(settings["exclude_public_holidays"]),
            holiday_subdivision_code=settings.get("holiday_subdivision_code"),
        )

    def candidate_days(self, round_id: int) -> tuple[CandidateDayRecord, ...]:
        rows = self._store.where(CANDIDATE_EXAM_DAY, exam_round_id=round_id)
        return tuple(self._record(row) for row in rows)

    def create_candidate_day(self, round_id: int, day: date) -> CandidateDayRecord:
        row = self._store.create(
            CANDIDATE_EXAM_DAY,
            {
                "exam_round_id": round_id,
                "date": day.isoformat(),
                "is_active": 1,
            },
        )
        return self._record(row)

    def _record(self, row: dict[str, object]) -> CandidateDayRecord:
        return _SQLiteCandidateDayRecord(
            id=int(row["id"]),
            round_id=int(row["exam_round_id"]),
            date=str(row["date"]),
            is_active=int(row["is_active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
