"""Concrete application wiring for the canonical backend runtime."""

from __future__ import annotations

from pathlib import Path

from backend.integrations.holiday_provider import PythonHolidaysProvider
from backend.persistence.candidate_days import SQLiteCandidateDayUnitOfWorkFactory
from backend.planning.candidate_days import CandidateDayService


def candidate_day_service(db_path: Path) -> CandidateDayService:
    """Wire the planning port to SQLite and the configured holiday adapter."""
    return CandidateDayService(
        SQLiteCandidateDayUnitOfWorkFactory(db_path),
        PythonHolidaysProvider(),
    )
