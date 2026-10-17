"""Application queries that compose published planning calendar projections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, Protocol, TypedDict

from backend.identity.authorization import AuthorizationScope
from backend.identity.calendar_reads import IdentityCalendarMember
from backend.planning.calendar_reads import (
    PlanningCalendarDay,
    PlanningCalendarRecord,
    PlanningConfirmedPlan,
)


class SchedulingOverviewItem(TypedDict):
    id: int
    name: str
    status: str
    status_group: str
    committee_name: str
    exam_half_year: dict[str, Any] | None
    calendar_week_from: int | None
    calendar_week_to: int | None
    can_continue: bool


class ConfirmedPlanItem(TypedDict):
    id: int
    name: str
    committee: dict[str, Any]
    exam_half_year: dict[str, Any] | None
    days: list[dict[str, Any]]


class ConfirmedPlanDayItem(TypedDict):
    plan: dict[str, Any]
    day: dict[str, Any]


class PlanningCalendarQueries(Protocol):
    """Planning-owned rows needed by the HTTP calendar projections."""

    def scheduling_rounds(
        self, committee_ids: frozenset[int]
    ) -> Sequence[
        tuple[PlanningCalendarRecord, PlanningCalendarRecord | None, PlanningCalendarRecord | None]
    ]: ...

    def confirmed_plans(self, committee_ids: frozenset[int]) -> Sequence[PlanningConfirmedPlan]: ...

    def confirmed_plan(
        self, day_id: int, committee_ids: frozenset[int]
    ) -> PlanningConfirmedPlan | None: ...


class IdentityCalendarQueries(Protocol):
    """Identity-owned names and membership projections used by calendar views."""

    def committees(self, committee_ids: frozenset[int]) -> Mapping[int, Mapping[str, Any]]: ...

    def members(self, member_ids: frozenset[int]) -> Mapping[int, IdentityCalendarMember]: ...


class ExecutionCalendarQueries(Protocol):
    """Execution-owned status and attendance values for confirmed plans."""

    def day_execution(self, day_ids: frozenset[int]) -> Mapping[int, Mapping[str, Any]]: ...


class PlanningCalendarReadUnitOfWork(Protocol):
    """Domain-owned read ports bound to one shared read snapshot."""

    planning: PlanningCalendarQueries
    identity: IdentityCalendarQueries
    execution: ExecutionCalendarQueries

    def closure_view(self, day_id: int, scope: AuthorizationScope) -> dict[str, Any] | None: ...


class PlanningCalendarReadUnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractContextManager[PlanningCalendarReadUnitOfWork]: ...


class PlanningCalendarReadService:
    """Compose Planning, Identity, and Execution reads for public calendar views."""

    def __init__(self, unit_of_work_factory: PlanningCalendarReadUnitOfWorkFactory):
        self._unit_of_work_factory = unit_of_work_factory

    def scheduling_overview(self, scope: AuthorizationScope) -> list[SchedulingOverviewItem]:
        groups = {
            "draft": "draft",
            "availability_requested": "coordination",
            "availability_closed": "coordination",
            "plan_proposed": "planning",
            "in_progress": "planning",
            "plan_confirmed": "confirmed",
        }
        with self._unit_of_work_factory() as unit_of_work:
            rounds = unit_of_work.planning.scheduling_rounds(scope.committee_ids)
            committee_ids = frozenset(int(row[0].values["committee_id"]) for row in rounds)
            committees = unit_of_work.identity.committees(committee_ids)
            overview: list[SchedulingOverviewItem] = []
            for exam_round, half_year, settings in rounds:
                round_values = exam_round.values
                status_group = groups.get(round_values["status"])
                committee = committees.get(int(round_values["committee_id"]))
                if status_group is None or committee is None:
                    continue
                setting_values = settings.values if settings is not None else {}
                overview.append(
                    {
                        "id": round_values["id"],
                        "name": round_values["name"],
                        "status": round_values["status"],
                        "status_group": status_group,
                        "committee_name": committee["name"],
                        "exam_half_year": half_year.as_dict() if half_year else None,
                        "calendar_week_from": setting_values.get("calendar_week_from"),
                        "calendar_week_to": setting_values.get("calendar_week_to"),
                        "can_continue": status_group != "confirmed",
                    }
                )
            return sorted(overview, key=lambda row: (row["status_group"], row["name"], row["id"]))

    def confirmed_plans(self, scope: AuthorizationScope) -> list[ConfirmedPlanItem]:
        with self._unit_of_work_factory() as unit_of_work:
            plans = unit_of_work.planning.confirmed_plans(scope.committee_ids)
            committee_ids = frozenset(int(plan.exam_round.values["committee_id"]) for plan in plans)
            member_ids = frozenset(
                assignment.member_id
                for plan in plans
                for day in plan.days
                for assignment in day.assignments
            )
            committees = unit_of_work.identity.committees(committee_ids)
            members = unit_of_work.identity.members(member_ids)
            execution = unit_of_work.execution.day_execution(
                frozenset(day.day.values["id"] for plan in plans for day in plan.days)
            )
            result: list[ConfirmedPlanItem] = [
                self._plan_view(plan, committees, members, execution)
                for plan in plans
                if int(plan.exam_round.values["committee_id"]) in committees
            ]
            return sorted(
                result,
                key=lambda plan: (plan["committee"]["name"], plan["name"], plan["id"]),
            )

    def confirmed_plan_day(
        self, day_id: int, scope: AuthorizationScope
    ) -> ConfirmedPlanDayItem | None:
        with self._unit_of_work_factory() as unit_of_work:
            plan = unit_of_work.planning.confirmed_plan(day_id, scope.committee_ids)
            if plan is None:
                return None
            round_values = plan.exam_round.values
            committee_id = int(round_values["committee_id"])
            committees = unit_of_work.identity.committees(frozenset({committee_id}))
            if committee_id not in committees:
                return None
            member_ids = frozenset(
                assignment.member_id for day in plan.days for assignment in day.assignments
            )
            members = unit_of_work.identity.members(member_ids)
            execution = unit_of_work.execution.day_execution(
                frozenset(day.day.values["id"] for day in plan.days)
            )
            view = self._plan_view(plan, committees, members, execution)
            day = next(item for item in view["days"] if item["id"] == day_id)
            closure = unit_of_work.closure_view(day_id, scope)
            if closure is None:
                return None
            day["closure"] = closure
            return {
                "plan": {key: view[key] for key in ("id", "name", "committee", "exam_half_year")},
                "day": day,
            }

    @classmethod
    def _plan_view(
        cls,
        plan: PlanningConfirmedPlan,
        committees: Mapping[int, Mapping[str, Any]],
        members: Mapping[int, IdentityCalendarMember],
        execution: Mapping[int, Mapping[str, Any]],
    ) -> ConfirmedPlanItem:
        round_values = plan.exam_round.as_dict()
        committee = committees[int(round_values["committee_id"])]
        return {
            "id": round_values["id"],
            "name": round_values["name"],
            "committee": {"id": committee["id"], "name": committee["name"]},
            "exam_half_year": plan.half_year.as_dict() if plan.half_year else None,
            "days": [cls._day_view(day, members, execution) for day in plan.days],
        }  # type: ignore[return-value]

    @staticmethod
    def _day_view(
        day: PlanningCalendarDay,
        members: Mapping[int, IdentityCalendarMember],
        execution_by_day: Mapping[int, Mapping[str, Any]],
    ) -> dict[str, Any]:
        day_values = day.day.values
        execution = execution_by_day.get(int(day_values["id"]), {})
        room = day.room.values if day.room else None
        venue = day.venue.values if day.venue else None
        slots = []
        for slot_item in day.slots:
            slot = slot_item.slot.values
            candidate = slot_item.candidate.values if slot_item.candidate else None
            if candidate is None:
                continue
            slot_execution = execution.get("slots", {}).get(int(slot["id"]), {})
            slots.append(
                {
                    "id": slot["id"],
                    "starts_at": slot["starts_at"],
                    "ends_at": slot["ends_at"],
                    "sequence_number": slot["sequence_number"],
                    "slot_type": slot["slot_type"],
                    "actual_started_at": slot_execution.get("actual_started_at"),
                    "execution_status": slot_execution.get("execution_status", "open"),
                    "status_changed_at": slot_execution.get("status_changed_at"),
                    "actual_completed_at": slot_execution.get("actual_completed_at"),
                    "status_reason": slot_execution.get("status_reason"),
                    "candidate_attendance": execution.get("candidate_attendance", {}).get(
                        int(slot["id"]), {"status": "open", "arrived_at": None}
                    ),
                    "candidate": {
                        key: candidate[key]
                        for key in ("id", "first_name", "last_name", "ihk_exam_number")
                    },
                }
            )
        assignments = []
        for assignment_item in day.assignments:
            assignment = assignment_item.assignment.values
            member = members.get(assignment_item.member_id)
            if member is None:
                continue
            member_values = dict(member.member)
            member_values.update(
                {
                    key: member.person[key]
                    for key in ("first_name", "last_name")
                    if key in member.person
                }
            )
            assignments.append(
                {
                    "id": assignment["id"],
                    "assignment_role": assignment["assignment_role"],
                    "day_part": assignment["day_part"],
                    "fallback_status": assignment["fallback_status"],
                    "attendance": execution.get("member_attendance", {}).get(
                        assignment_item.member_id, {"status": "open", "arrived_at": None}
                    ),
                    "member": {
                        key: member_values[key]
                        for key in ("id", "first_name", "last_name", "representing_side")
                    },
                }
            )
        summary = {
            key: 0 for key in ("open", "running", "completed", "cancelled", "needs_follow_up")
        }
        for slot in slots:
            summary[slot["execution_status"]] += 1
        return {
            "id": day_values["id"],
            "date": day_values["date"],
            "revision": day_values["revision"],
            "closure_status": day_values["closure_status"],
            "location": (
                {
                    "id": venue["id"],
                    "name": venue["name"],
                    "room": room["name"],
                    "city": venue["city"],
                }
                if venue is not None and room is not None
                else None
            ),
            "room_id": room["id"] if room else None,
            "slots": slots,
            "assignments": assignments,
            "status_summary": summary,
        }
