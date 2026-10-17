"""HTTP resource metadata shared by the FastAPI adapters and contract tests."""

from backend.persistence.models import (
    CANDIDATE,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_HALF_YEAR,
    EXAM_ROUND,
    EXAM_SLOT,
    MEMBER_AVAILABILITY,
    PERSON,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
)

PLAN_AGGREGATE_RESOURCES = {EXAM_DAY, EXAM_SLOT, EXAM_DAY_ASSIGNMENT}

REST_RESOURCES = {
    "committees": COMMITTEE,
    "persons": PERSON,
    "members": COMMITTEE_MEMBER,
    "memberships": COMMITTEE_MEMBER,
    "exam-half-years": EXAM_HALF_YEAR,
    "exam-rounds": EXAM_ROUND,
    "round-candidates": ROUND_CANDIDATE,
    "candidates": CANDIDATE,
    "planning-settings": PLANNING_SETTINGS,
    "candidate-exam-days": CANDIDATE_EXAM_DAY,
    "member-availabilities": MEMBER_AVAILABILITY,
    "exam-days": EXAM_DAY,
    "exam-slots": EXAM_SLOT,
    "exam-day-assignments": EXAM_DAY_ASSIGNMENT,
}
