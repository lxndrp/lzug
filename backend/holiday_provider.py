from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from holidays import country_holidays
from holidays.constants import PUBLIC

GERMAN_SUBDIVISION_CODES = frozenset(
    {
        "DE-BB",
        "DE-BE",
        "DE-BW",
        "DE-BY",
        "DE-HB",
        "DE-HE",
        "DE-HH",
        "DE-MV",
        "DE-NI",
        "DE-NW",
        "DE-RP",
        "DE-SH",
        "DE-SL",
        "DE-SN",
        "DE-ST",
        "DE-TH",
    }
)


@dataclass(frozen=True)
class PublicHoliday:
    date: date
    name: str


class HolidayProvider(Protocol):
    def public_holidays(
        self,
        start_date: date,
        end_date: date,
        subdivision_code: str,
    ) -> list[PublicHoliday]: ...


class PythonHolidaysProvider:
    def public_holidays(
        self,
        start_date: date,
        end_date: date,
        subdivision_code: str,
    ) -> list[PublicHoliday]:
        if subdivision_code not in GERMAN_SUBDIVISION_CODES:
            raise ValueError("Unknown German federal state")

        years = range(start_date.year, end_date.year + 1)
        calendar = country_holidays(
            "DE",
            subdiv=subdivision_code.removeprefix("DE-"),
            years=years,
            language="de",
            categories=PUBLIC,
        )
        return [
            PublicHoliday(date=holiday_date, name=name)
            for holiday_date, name in sorted(calendar.items())
            if start_date <= holiday_date <= end_date
        ]
