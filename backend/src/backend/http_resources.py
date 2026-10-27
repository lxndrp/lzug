"""HTTP resource metadata shared by the FastAPI adapters and contract tests."""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.resource_access import ResourceKind


@dataclass(frozen=True)
class HttpResource:
    """Transport-facing identity and fields used for filters and hypermedia links."""

    kind: ResourceKind
    readable_fields: tuple[str, ...]


PLAN_AGGREGATE_RESOURCES = frozenset(
    {ResourceKind.EXAM_DAY, ResourceKind.EXAM_SLOT, ResourceKind.EXAM_DAY_ASSIGNMENT}
)

CANDIDATE_COMMITTEE_ASSIGNMENT_RESOURCE = HttpResource(
    ResourceKind.CANDIDATE_COMMITTEE_ASSIGNMENT,
    (
        "id",
        "candidate_id",
        "exam_half_year_id",
        "exam_round_id",
        "round_candidate_id",
        "assigned_at",
        "ended_at",
        "change_reason",
        "created_at",
        "updated_at",
    ),
)

_COMMITTEE = HttpResource(
    ResourceKind.COMMITTEE,
    ("id", "name", "occupation", "ihk", "is_active", "bootstrap_state", "created_at", "updated_at"),
)
_PERSON = HttpResource(
    ResourceKind.PERSON,
    ("id", "first_name", "last_name", "email", "mobile", "created_at", "updated_at"),
)
_MEMBER = HttpResource(
    ResourceKind.COMMITTEE_MEMBER,
    (
        "id",
        "person_id",
        "committee_id",
        "member_status",
        "committee_role",
        "representing_side",
        "is_active",
        "created_at",
        "updated_at",
    ),
)
_EXAM_HALF_YEAR = HttpResource(
    ResourceKind.EXAM_HALF_YEAR,
    ("id", "season", "year", "status", "legacy_status", "created_at", "updated_at"),
)
_EXAM_ROUND = HttpResource(
    ResourceKind.EXAM_ROUND,
    (
        "id",
        "exam_half_year_id",
        "committee_id",
        "name",
        "status",
        "revision",
        "lifecycle_status",
        "legacy_status",
        "availability_deadline",
        "availability_reminder_at",
        "created_by_member_id",
        "created_at",
        "updated_at",
    ),
)
_ROUND_CANDIDATE = HttpResource(
    ResourceKind.ROUND_CANDIDATE,
    (
        "id",
        "exam_round_id",
        "candidate_id",
        "attempt_number",
        "requires_mep",
        "is_active",
        "terminal_status",
        "terminal_reason",
        "effective_new_round_id",
        "postponed_until",
        "ihk_decision_reference",
        "terminal_at",
        "created_at",
        "updated_at",
    ),
)
_CANDIDATE = HttpResource(
    ResourceKind.CANDIDATE,
    (
        "id",
        "first_name",
        "last_name",
        "ihk_exam_number",
        "specialization",
        "training_company",
        "created_at",
        "updated_at",
    ),
)
_PLANNING_SETTINGS = HttpResource(
    ResourceKind.PLANNING_SETTINGS,
    (
        "id",
        "exam_round_id",
        "calendar_week_from",
        "calendar_week_to",
        "exams_per_day",
        "max_exam_days_per_week",
        "lunch_break_enabled",
        "exclude_public_holidays",
        "holiday_subdivision_code",
        "default_room_id",
        "updated_by_member_id",
        "created_at",
        "updated_at",
    ),
)
_CANDIDATE_EXAM_DAY = HttpResource(
    ResourceKind.CANDIDATE_EXAM_DAY,
    ("id", "exam_round_id", "date", "is_active", "created_at", "updated_at"),
)
_MEMBER_AVAILABILITY = HttpResource(
    ResourceKind.MEMBER_AVAILABILITY,
    (
        "id",
        "exam_round_id",
        "committee_member_id",
        "candidate_exam_day_id",
        "availability",
        "responded_at",
        "created_at",
        "updated_at",
    ),
)
_EXAM_DAY = HttpResource(
    ResourceKind.EXAM_DAY,
    (
        "id",
        "exam_round_id",
        "room_id",
        "date",
        "status",
        "revision",
        "closure_status",
        "lunch_break_enabled",
        "created_from_proposal",
        "created_at",
        "updated_at",
    ),
)
_EXAM_SLOT = HttpResource(
    ResourceKind.EXAM_SLOT,
    (
        "id",
        "exam_day_id",
        "round_candidate_id",
        "slot_type",
        "starts_at",
        "ends_at",
        "sequence_number",
        "status",
        "actual_started_at",
        "execution_status",
        "status_changed_at",
        "actual_completed_at",
        "status_reason",
        "created_at",
        "updated_at",
    ),
)
_EXAM_DAY_ASSIGNMENT = HttpResource(
    ResourceKind.EXAM_DAY_ASSIGNMENT,
    (
        "id",
        "exam_day_id",
        "committee_member_id",
        "assignment_role",
        "day_part",
        "fallback_status",
        "created_at",
        "updated_at",
    ),
)

REST_RESOURCES = {
    "committees": _COMMITTEE,
    "persons": _PERSON,
    "members": _MEMBER,
    "memberships": _MEMBER,
    "exam-half-years": _EXAM_HALF_YEAR,
    "exam-rounds": _EXAM_ROUND,
    "round-candidates": _ROUND_CANDIDATE,
    "candidates": _CANDIDATE,
    "planning-settings": _PLANNING_SETTINGS,
    "candidate-exam-days": _CANDIDATE_EXAM_DAY,
    "member-availabilities": _MEMBER_AVAILABILITY,
    "exam-days": _EXAM_DAY,
    "exam-slots": _EXAM_SLOT,
    "exam-day-assignments": _EXAM_DAY_ASSIGNMENT,
}
