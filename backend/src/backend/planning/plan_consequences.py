"""Typed descriptions of the effects of a confirmed plan revision."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanCalendarChange:
    recipient_member_id: int
    assignment_id: int
    action: str


@dataclass(frozen=True)
class PlanNotificationChange:
    recipient_member_id: int
    categories: tuple[str, ...]


@dataclass(frozen=True)
class PlanConsequenceDescriptions:
    calendar: tuple[PlanCalendarChange, ...]
    notifications: tuple[PlanNotificationChange, ...]
    notification_scope: frozenset[int]


@dataclass(frozen=True)
class PlanConsequenceSource:
    """Planning-owned revision context and its deterministic effect description."""

    revision_id: int
    exam_round_id: int
    committee_id: int
    resulting_revision: int
    descriptions: PlanConsequenceDescriptions | None
    error_code: str | None = None


def describe_plan_change(
    before: dict,
    after: dict,
    *,
    actor_member_id: int,
    manager_member_ids: tuple[int, ...] = (),
) -> PlanConsequenceDescriptions:
    """Describe follow-up work from detached, immutable plan snapshots."""
    old_assignments = _assignments(before)
    new_assignments = _assignments(after)
    calendar: list[PlanCalendarChange] = []
    notices: dict[int, set[str]] = defaultdict(set)
    personnel_days: set[int] = set()

    for assignment_id in sorted(set(old_assignments) | set(new_assignments)):
        old = old_assignments.get(assignment_id)
        new = new_assignments.get(assignment_id)
        if old is None or new is None:
            raise ValueError("Confirmed plan assignment identity changed")
        old_member = int(old["committee_member_id"])
        new_member = int(new["committee_member_id"])
        if old_member != new_member:
            personnel_days.update({int(old["day_id"]), int(new["day_id"])})
            notices[old_member].add("removed")
            notices[new_member].add("added")
            calendar.extend(
                (
                    PlanCalendarChange(old_member, assignment_id, "cancel"),
                    PlanCalendarChange(new_member, assignment_id, "create"),
                )
            )
        elif _calendar_signature(old) != _calendar_signature(new):
            notices[new_member].add("changed")
            calendar.append(PlanCalendarChange(new_member, assignment_id, "update"))

    if personnel_days:
        old_by_day = _members_by_day(old_assignments)
        new_by_day = _members_by_day(new_assignments)
        for day_id in personnel_days:
            for member_id in old_by_day[day_id] & new_by_day[day_id]:
                notices[member_id].add("crew_changed")

    if notices:
        for member_id in manager_member_ids:
            notices[member_id].add("overview")

    notifications = tuple(
        PlanNotificationChange(member_id, tuple(sorted(categories)))
        for member_id, categories in sorted(notices.items())
        if member_id != actor_member_id
    )
    return PlanConsequenceDescriptions(
        calendar=tuple(calendar),
        notifications=notifications,
        notification_scope=frozenset(notices),
    )


def _assignments(payload: dict) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for day in payload["exam_days"]:
        slots = list(day["slots"])
        for assignment in day["assignments"]:
            assignment_id = int(assignment["id"])
            day_part = str(assignment["day_part"])
            section = slots
            if day_part != "full_day":
                section = [
                    slot
                    for slot in slots
                    if (str(slot["starts_at"])[11:16] < "12:00") == (day_part == "morning")
                ]
            if not section:
                raise ValueError("Assignment has no calendar section")
            result[assignment_id] = {
                **assignment,
                "day_id": int(day["id"]),
                "date": day["date"],
                "room_id": int(day["room_id"]),
                "starts_at": min(str(slot["starts_at"]) for slot in section),
                "ends_at": max(str(slot["ends_at"]) for slot in section),
            }
    return result


def _calendar_signature(assignment: dict) -> tuple:
    return (
        assignment["committee_member_id"],
        assignment["day_id"],
        assignment["date"],
        assignment["room_id"],
        assignment["assignment_role"],
        assignment["day_part"],
        assignment["starts_at"],
        assignment["ends_at"],
    )


def _members_by_day(assignments: dict[int, dict]) -> dict[int, set[int]]:
    by_day: dict[int, set[int]] = defaultdict(set)
    for assignment in assignments.values():
        by_day[int(assignment["day_id"])].add(int(assignment["committee_member_id"]))
    return by_day
