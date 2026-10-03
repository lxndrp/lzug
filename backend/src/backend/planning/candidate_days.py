"""Generate eligible weekday records for an exam round from ISO calendar weeks."""

from __future__ import annotations

import re
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol, TypedDict

ISO_WEEK_PATTERN = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})$")


@dataclass(frozen=True)
class GenerateCandidateDays:
    """Request candidate-day generation for one planning round."""

    round_id: int


class CandidateDaySettings(Protocol):
    """Planning settings needed to generate candidate days."""

    calendar_week_from: str
    calendar_week_to: str
    exclude_public_holidays: int
    holiday_subdivision_code: str | None


class CandidateDayRecord(Protocol):
    """Materialized candidate-day value owned by planning."""

    id: int
    round_id: int
    date: str
    is_active: int


class PublicHoliday(TypedDict):
    """A holiday within the planning range, preserving its display name."""

    date: date
    name: str


class HolidayProvider(Protocol):
    """Planning-owned port for state-specific public holidays."""

    def public_holidays(
        self,
        start_date: date,
        end_date: date,
        subdivision_code: str,
    ) -> list[PublicHoliday]: ...


class CandidateDayUnitOfWork(Protocol):
    """Atomic read/write boundary for one candidate-day generation command."""

    def planning_settings(self, round_id: int) -> CandidateDaySettings | None: ...

    def candidate_days(self, round_id: int) -> tuple[CandidateDayRecord, ...]: ...

    def create_candidate_day(self, round_id: int, day: date) -> CandidateDayRecord: ...


class CandidateDayUnitOfWorkFactory(Protocol):
    """Create an isolated Unit of Work for one command."""

    def __call__(self) -> AbstractContextManager[CandidateDayUnitOfWork]: ...


@dataclass(frozen=True)
class ExcludedHoliday:
    """One holiday omitted from the generated dates."""

    date: str
    name: str


@dataclass(frozen=True)
class CandidateDayGeneration:
    """Typed result of a candidate-day generation command."""

    round_id: int
    calendar_week_from: str
    calendar_week_to: str
    exclude_public_holidays: int
    holiday_subdivision_code: str | None
    created_days: tuple[CandidateDayRecord, ...]
    skipped_existing: tuple[str, ...]
    excluded_holidays: tuple[ExcludedHoliday, ...]
    calculated_weekdays: int

    def as_payload(self) -> dict[str, object]:
        """Preserve the established HTTP response shape at the adapter edge."""
        created_days = [
            {
                "id": day.id,
                "exam_round_id": day.round_id,
                "date": day.date,
                "is_active": day.is_active,
            }
            for day in self.created_days
        ]
        return {
            "round_id": self.round_id,
            "calendar_week_from": self.calendar_week_from,
            "calendar_week_to": self.calendar_week_to,
            "exclude_public_holidays": self.exclude_public_holidays,
            "holiday_subdivision_code": self.holiday_subdivision_code,
            "created_days": created_days,
            "skipped_existing": list(self.skipped_existing),
            "excluded_holidays": [
                {"date": holiday.date, "name": holiday.name} for holiday in self.excluded_holidays
            ],
            "counts": {
                "calculated_weekdays": self.calculated_weekdays,
                "created": len(self.created_days),
                "existing": len(self.skipped_existing),
                "excluded_holidays": len(self.excluded_holidays),
            },
        }


class CandidateDayService:
    """Generate candidate days through planning-owned ports only."""

    def __init__(
        self,
        unit_of_work_factory: CandidateDayUnitOfWorkFactory,
        holiday_provider: HolidayProvider,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._holiday_provider = holiday_provider

    def generate(self, command: GenerateCandidateDays) -> CandidateDayGeneration:
        """Persist missing workdays in the configured ISO-week range atomically."""
        with self._unit_of_work_factory() as unit_of_work:
            settings = unit_of_work.planning_settings(command.round_id)
            if settings is None:
                raise ValueError("Planning settings not found")

            start_date = self._week_date(settings.calendar_week_from, weekday=1)
            end_date = self._week_date(settings.calendar_week_to, weekday=5)
            if start_date > end_date:
                raise ValueError("Calendar week range is invalid")

            weekdays = self._weekdays(start_date, end_date)
            holidays_by_date = self._holidays(settings, start_date, end_date)
            existing_dates = {
                date.fromisoformat(row.date)
                for row in unit_of_work.candidate_days(command.round_id)
            }

            created_days = []
            skipped_existing = []
            excluded_holidays = []
            for candidate_date in weekdays:
                if candidate_date in existing_dates:
                    skipped_existing.append(candidate_date.isoformat())
                    continue
                if candidate_date in holidays_by_date:
                    excluded_holidays.append(
                        ExcludedHoliday(
                            date=candidate_date.isoformat(),
                            name=holidays_by_date[candidate_date],
                        )
                    )
                    continue
                created_days.append(
                    unit_of_work.create_candidate_day(command.round_id, candidate_date)
                )

            return CandidateDayGeneration(
                round_id=command.round_id,
                calendar_week_from=settings.calendar_week_from,
                calendar_week_to=settings.calendar_week_to,
                exclude_public_holidays=settings.exclude_public_holidays,
                holiday_subdivision_code=settings.holiday_subdivision_code,
                created_days=tuple(created_days),
                skipped_existing=tuple(skipped_existing),
                excluded_holidays=tuple(excluded_holidays),
                calculated_weekdays=len(weekdays),
            )

    def _holidays(
        self,
        settings: CandidateDaySettings,
        start_date: date,
        end_date: date,
    ) -> dict[date, str]:
        if not settings.exclude_public_holidays:
            return {}
        subdivision_code = settings.holiday_subdivision_code
        if not subdivision_code:
            raise ValueError("Federal state is required when public holidays are excluded")
        return {
            holiday["date"]: holiday["name"]
            for holiday in self._holiday_provider.public_holidays(
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
