"""Convert planning transport payloads without database or authorization access."""

from __future__ import annotations

from typing import Any

from backend.planning import (
    ConfirmedPlanChange,
    PlanAssignment,
    PlanDay,
    PlanningProposal,
    PlanSlot,
)


def _integer(container: dict[str, Any], field_name: str, *, nullable: bool = False) -> int | None:
    value = container.get(field_name)
    if nullable and value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _room_identifier(container: dict[str, Any]) -> int:
    """Accept the temporary location alias without weakening room identity."""
    has_room = "room_id" in container
    has_location = "location_id" in container
    if not has_room and not has_location:
        raise ValueError("room_id must be an integer")
    room_id = _integer(container, "room_id") if has_room else None
    location_id = _integer(container, "location_id") if has_location else None
    if room_id is not None and location_id is not None and room_id != location_id:
        raise ValueError("room_id and location_id must match")
    if room_id is not None:
        return room_id
    if location_id is None:
        raise ValueError("location_id must be an integer")
    return location_id


def _plan_slot(raw_slot: Any) -> PlanSlot:
    if not isinstance(raw_slot, dict) or not isinstance(raw_slot.get("slot_type"), str):
        raise ValueError("Each slot must be an object with a slot_type")
    return PlanSlot(
        id=_integer(raw_slot, "id", nullable=True),
        round_candidate_id=_integer(raw_slot, "round_candidate_id"),
        slot_type=raw_slot["slot_type"],
    )


def _plan_assignment(raw_assignment: Any) -> PlanAssignment:
    if not isinstance(raw_assignment, dict):
        raise ValueError("Each assignment must be an object")
    if not isinstance(raw_assignment.get("assignment_role"), str) or not isinstance(
        raw_assignment.get("day_part"), str
    ):
        raise ValueError("Assignment role and day part must be strings")
    return PlanAssignment(
        id=_integer(raw_assignment, "id", nullable=True),
        committee_member_id=_integer(raw_assignment, "committee_member_id"),
        assignment_role=raw_assignment["assignment_role"],
        day_part=raw_assignment["day_part"],
    )


def _plan_day(raw_day: Any) -> PlanDay:
    if not isinstance(raw_day, dict):
        raise ValueError("Each exam day must be an object")
    raw_slots = raw_day.get("slots")
    raw_assignments = raw_day.get("assignments")
    if not isinstance(raw_slots, list) or not isinstance(raw_assignments, list):
        raise ValueError("Each exam day needs slots and assignments arrays")
    slots = tuple(_plan_slot(slot) for slot in raw_slots)
    assignments = tuple(_plan_assignment(assignment) for assignment in raw_assignments)
    return PlanDay(
        id=_integer(raw_day, "id", nullable=True),
        candidate_exam_day_id=_integer(raw_day, "candidate_exam_day_id"),
        room_id=_room_identifier(raw_day),
        slots=slots,
        assignments=assignments,
    )


def planning_proposal_from_payload(round_id: int, payload: dict[str, Any]) -> PlanningProposal:
    """Parse a complete proposal while keeping the path as authoritative scope."""
    if _integer(payload, "round_id") != round_id:
        raise ValueError("round_id must match the request path")
    raw_days = payload.get("exam_days")
    if not isinstance(raw_days, list):
        raise ValueError("exam_days must be an array")
    days = tuple(_plan_day(day) for day in raw_days)
    return PlanningProposal(round_id=round_id, revision=_integer(payload, "revision"), days=days)


def confirmed_plan_change_from_payload(
    round_id: int, payload: dict[str, Any]
) -> ConfirmedPlanChange:
    """Parse a confirmed-plan revision command at its aggregate boundary."""
    reason = payload.get("reason")
    if not isinstance(reason, str):
        raise ValueError("reason must be a string")
    return ConfirmedPlanChange(
        plan=planning_proposal_from_payload(round_id, payload), reason=reason
    )
