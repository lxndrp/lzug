"""Shared command contract for round lifecycle mutation guards."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class MutationLockKind(StrEnum):
    """Resource categories whose writes honor the round lifecycle lock."""

    EXAM_ROUND = "exam_round"
    PLANNING_PROPOSAL = "planning_proposal"
    PLANNING_SETTINGS = "planning_settings"
    CANDIDATE_EXAM_DAY = "candidate_exam_day"
    MEMBER_AVAILABILITY = "member_availability"
    ROUND_CANDIDATE = "round_candidate"
    CONFIRMED_PLAN_DAY = "confirmed_plan_day"
    EXAM_PROTOCOL = "exam_protocol"
    EXAM_RESULT = "exam_result"
    ABSENCE_REPORT = "absence_report"


@dataclass(frozen=True)
class MutationLockCommand:
    """Transport-neutral reference for a mutation subject to an Execution lock."""

    kind: MutationLockKind
    resource_id: int | None
    payload: Mapping[str, Any]
