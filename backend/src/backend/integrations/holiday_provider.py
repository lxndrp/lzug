"""Public-holiday abstraction used by candidate-day generation."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from holidays import country_holidays
from holidays.constants import PUBLIC

if TYPE_CHECKING:
    from backend.planning.candidate_days import PublicHoliday

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


class PythonHolidaysProvider:
    """Resolve German statutory holidays through the ``holidays`` package.

    Municipality-specific rules are intentionally not inferred: callers must
    supply one of the supported federal-state codes.
    """

    def public_holidays(
        self,
        start_date: date,
        end_date: date,
        subdivision_code: str,
    ) -> list[PublicHoliday]:
        """Return public holidays inside an inclusive date range.

        Raises:
            ValueError: If ``subdivision_code`` is not a supported German
                federal-state code.
        """
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
        holidays: list[PublicHoliday] = []
        for holiday_date, name in sorted(calendar.items()):
            if start_date <= holiday_date <= end_date:
                holidays.append({"date": holiday_date, "name": name})
        return holidays
