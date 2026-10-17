"""Application queries that compose published planning calendar projections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, NotRequired, Protocol, TypedDict

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


class AttendanceRead(TypedDict):
    status: str
    arrived_at: str | None


class CandidateRead(TypedDict):
    id: int
    first_name: str
    last_name: str
    ihk_exam_number: str


class ConfirmedSlotRead(TypedDict):
    id: int
    starts_at: str
    ends_at: str
    sequence_number: int
    slot_type: str
    actual_started_at: str | None
    execution_status: str
    status_changed_at: str | None
    actual_completed_at: str | None
    status_reason: str | None
    candidate_attendance: AttendanceRead
    candidate: CandidateRead


class CommitteeMemberRead(TypedDict):
    id: int
    first_name: str
    last_name: str
    representing_side: str


class ConfirmedAssignmentRead(TypedDict):
    id: int
    assignment_role: str
    day_part: str
    fallback_status: str
    attendance: AttendanceRead
    member: CommitteeMemberRead


class ConfirmedLocationRead(TypedDict):
    id: int
    name: str
    room: str
    city: str


class CommitteeRead(TypedDict):
    id: int
    name: str


class ExamHalfYearRead(TypedDict):
    id: int
    season: str
    year: int
    status: str
    legacy_status: str | None
    created_at: str
    updated_at: str


class ConfirmedPlanMetadata(TypedDict):
    id: int
    name: str
    committee: CommitteeRead
    exam_half_year: ExamHalfYearRead | None


class ConfirmedCalendarDayRead(TypedDict):
    id: int
    date: str
    revision: int
    closure_status: str
    location: ConfirmedLocationRead | None
    room_id: int | None
    slots: list[ConfirmedSlotRead]
    assignments: list[ConfirmedAssignmentRead]
    closure: NotRequired[Mapping[str, Any]]


class ConfirmedPlanItem(TypedDict):
    id: int
    name: str
    committee: CommitteeRead
    exam_half_year: ExamHalfYearRead | None
    days: list[ConfirmedCalendarDayRead]


class ConfirmedPlanDayItem(TypedDict):
    plan: ConfirmedPlanMetadata
    day: ConfirmedCalendarDayRead


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
            plan_metadata: ConfirmedPlanMetadata = {
                "id": view["id"],
                "name": view["name"],
                "committee": view["committee"],
                "exam_half_year": view["exam_half_year"],
            }
            return {
                "plan": plan_metadata,
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
            "exam_half_year": (
                PlanningCalendarReadService._half_year_view(plan.half_year)
                if plan.half_year
                else None
            ),
            "days": [cls._day_view(day, members, execution) for day in plan.days],
        }

    @staticmethod
    def _half_year_view(record: PlanningCalendarRecord) -> ExamHalfYearRead:
        values = record.values
        return {
            "id": values["id"],
            "season": values["season"],
            "year": values["year"],
            "status": values["status"],
            "legacy_status": values["legacy_status"],
            "created_at": values["created_at"],
            "updated_at": values["updated_at"],
        }

    @staticmethod
    def _day_view(
        day: PlanningCalendarDay,
        members: Mapping[int, IdentityCalendarMember],
        execution_by_day: Mapping[int, Mapping[str, Any]],
    ) -> ConfirmedCalendarDayRead:
        day_values = day.day.values
        execution = execution_by_day.get(int(day_values["id"]), {})
        room = day.room.values if day.room else None
        venue = day.venue.values if day.venue else None
        slots: list[ConfirmedSlotRead] = []
        for slot_item in day.slots:
            slot = slot_item.slot.values
            candidate = slot_item.candidate.values if slot_item.candidate else None
            if candidate is None:
                continue
            slot_execution = execution.get("slots", {}).get(int(slot["id"]), {})
            candidate_view: CandidateRead = {
                "id": candidate["id"],
                "first_name": candidate["first_name"],
                "last_name": candidate["last_name"],
                "ihk_exam_number": candidate["ihk_exam_number"],
            }
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
                    "candidate": candidate_view,
                }
            )
        assignments: list[ConfirmedAssignmentRead] = []
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
            member_view: CommitteeMemberRead = {
                "id": member_values["id"],
                "first_name": member_values["first_name"],
                "last_name": member_values["last_name"],
                "representing_side": member_values["representing_side"],
            }
            assignments.append(
                {
                    "id": assignment["id"],
                    "assignment_role": assignment["assignment_role"],
                    "day_part": assignment["day_part"],
                    "fallback_status": assignment["fallback_status"],
                    "attendance": execution.get("member_attendance", {}).get(
                        assignment_item.member_id, {"status": "open", "arrived_at": None}
                    ),
                    "member": member_view,
                }
            )
        location: ConfirmedLocationRead | None = (
            {
                "id": venue["id"],
                "name": venue["name"],
                "room": room["name"],
                "city": venue["city"],
            }
            if venue is not None and room is not None
            else None
        )
        result: ConfirmedCalendarDayRead = {
            "id": day_values["id"],
            "date": day_values["date"],
            "revision": day_values["revision"],
            "closure_status": day_values["closure_status"],
            "location": location,
            "room_id": room["id"] if room else None,
            "slots": slots,
            "assignments": assignments,
        }
        return result
