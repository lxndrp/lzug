"""Generate eligible weekday records for an exam round from ISO calendar weeks."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .database import DEFAULT_DB_PATH, session_scope
from .holiday_provider import HolidayProvider, PythonHolidaysProvider
from .models import CANDIDATE_EXAM_DAY, PLANNING_SETTINGS
from .store import Store

ISO_WEEK_PATTERN = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})$")


class CandidateDayService:
    """Generate candidate exam days without coupling planning to a holiday source.

    The injected provider makes public-holiday rules replaceable in tests and
    in future deployments. Generation is idempotent for existing dates and the
    surrounding session commits all newly created days together.
    """

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        holiday_provider: HolidayProvider | None = None,
    ):
        self.db_path = db_path
        self.holiday_provider = holiday_provider or PythonHolidaysProvider()

    def generate(self, round_id: int) -> dict[str, Any]:
        """Persist missing workdays in the configured ISO-week range.

        Weekends, existing rows, and optionally state-specific public holidays
        are excluded. The returned result keeps those categories separate so
        the HTTP layer can give the user an actionable explanation.

        Args:
            round_id: Identifier of the round whose settings are used.

        Returns:
            Created days, skipped dates, excluded holidays, and their counts.

        Raises:
            ValueError: If settings are absent, ISO weeks are invalid, or a
                required federal-state code is missing.
        """
        with session_scope(self.db_path) as session:
            store = Store(session)
            settings = store.first(PLANNING_SETTINGS, exam_round_id=round_id)
            if settings is None:
                raise ValueError("Planning settings not found")

            start_date = self._week_date(settings["calendar_week_from"], weekday=1)
            end_date = self._week_date(settings["calendar_week_to"], weekday=5)
            if start_date > end_date:
                raise ValueError("Calendar week range is invalid")

            weekdays = self._weekdays(start_date, end_date)
            holidays_by_date = self._holidays(settings, start_date, end_date)
            existing_rows = store.where(CANDIDATE_EXAM_DAY, exam_round_id=round_id)
            existing_dates = {date.fromisoformat(row["date"]) for row in existing_rows}

            created_days = []
            skipped_existing = []
            excluded_holidays = []
            for candidate_date in weekdays:
                if candidate_date in existing_dates:
                    skipped_existing.append(candidate_date.isoformat())
                    continue
                if candidate_date in holidays_by_date:
                    excluded_holidays.append(
                        {
                            "date": candidate_date.isoformat(),
                            "name": holidays_by_date[candidate_date],
                        }
                    )
                    continue
                created_days.append(
                    store.create(
                        CANDIDATE_EXAM_DAY,
                        {
                            "exam_round_id": round_id,
                            "date": candidate_date.isoformat(),
                            "is_active": 1,
                        },
                    )
                )

            return {
                "round_id": round_id,
                "calendar_week_from": settings["calendar_week_from"],
                "calendar_week_to": settings["calendar_week_to"],
                "exclude_public_holidays": settings["exclude_public_holidays"],
                "holiday_subdivision_code": settings["holiday_subdivision_code"],
                "created_days": created_days,
                "skipped_existing": skipped_existing,
                "excluded_holidays": excluded_holidays,
                "counts": {
                    "calculated_weekdays": len(weekdays),
                    "created": len(created_days),
                    "existing": len(skipped_existing),
                    "excluded_holidays": len(excluded_holidays),
                },
            }

    def _holidays(
        self,
        settings: dict[str, Any],
        start_date: date,
        end_date: date,
    ) -> dict[date, str]:
        if not settings["exclude_public_holidays"]:
            return {}
        subdivision_code = settings.get("holiday_subdivision_code")
        if not subdivision_code:
            raise ValueError("Federal state is required when public holidays are excluded")
        return {
            holiday.date: holiday.name
            for holiday in self.holiday_provider.public_holidays(
                start_date,
                end_date,
                subdivision_code,
            )
        }

    def _week_date(self, value: str, weekday: int) -> date:
        match = ISO_WEEK_PATTERN.fullmatch(value)
        if match is None:
            raise ValueError("Calendar week must use the format YYYY-Www")
        try:
            return date.fromisocalendar(
                int(match.group("year")),
                int(match.group("week")),
                weekday,
            )
        except ValueError as error:
            raise ValueError("Calendar week is invalid") from error

    def _weekdays(self, start_date: date, end_date: date) -> list[date]:
        result = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                result.append(current)
            current += timedelta(days=1)
        return result
