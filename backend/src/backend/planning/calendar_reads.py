"""Detached Planning snapshot contracts for published calendar read projections."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class PlanningCalendarRecord(Protocol):
    """Materialized Planning row values; no ORM values cross the port."""

    @property
    def values(self) -> Mapping[str, Any]: ...

    def as_dict(self) -> dict[str, Any]: ...


class PlanningCalendarSlot(Protocol):
    @property
    def slot(self) -> PlanningCalendarRecord: ...

    @property
    def candidate(self) -> PlanningCalendarRecord | None: ...


class PlanningCalendarAssignment(Protocol):
    @property
    def assignment(self) -> PlanningCalendarRecord: ...

    @property
    def member_id(self) -> int: ...


class PlanningCalendarDay(Protocol):
    @property
    def day(self) -> PlanningCalendarRecord: ...

    @property
    def room(self) -> PlanningCalendarRecord | None: ...

    @property
    def venue(self) -> PlanningCalendarRecord | None: ...

    @property
    def slots(self) -> tuple[PlanningCalendarSlot, ...]: ...

    @property
    def assignments(self) -> tuple[PlanningCalendarAssignment, ...]: ...


class PlanningConfirmedPlan(Protocol):
    @property
    def exam_round(self) -> PlanningCalendarRecord: ...

    @property
    def half_year(self) -> PlanningCalendarRecord | None: ...

    @property
    def days(self) -> tuple[PlanningCalendarDay, ...]: ...
