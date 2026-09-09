"""Resolve resource owners within the caller's persistence transaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.persistence.models import (
    CANDIDATE,
    CANDIDATE_COMMITTEE_ASSIGNMENT,
    CANDIDATE_EXAM_ATTENDANCE,
    CANDIDATE_EXAM_DAY,
    COMMITTEE,
    COMMITTEE_MEMBER,
    EXAM_DAY,
    EXAM_DAY_ASSIGNMENT,
    EXAM_HALF_YEAR,
    EXAM_ROUND,
    EXAM_SLOT,
    MEMBER_AVAILABILITY,
    MEMBER_EXAM_ATTENDANCE,
    PERSON,
    PLANNING_SETTINGS,
    ROUND_CANDIDATE,
    Resource,
)
from backend.persistence.store import Store

ROUND_OWNED_RESOURCES = frozenset(
    {
        ROUND_CANDIDATE,
        CANDIDATE_COMMITTEE_ASSIGNMENT,
        PLANNING_SETTINGS,
        CANDIDATE_EXAM_DAY,
        MEMBER_AVAILABILITY,
        EXAM_DAY,
    }
)
DAY_OWNED_RESOURCES = frozenset({EXAM_SLOT, EXAM_DAY_ASSIGNMENT, MEMBER_EXAM_ATTENDANCE})


@dataclass(frozen=True)
class ResourceOwner:
    """Authorization-only ownership; never serialized as response data."""

    committee_id: int | None
    round_id: int | None


class ResourceOwnership:
    """Read owners through one Store without opening or completing a session."""

    def __init__(self, store: Store):
        self.store = store

    def values(
        self, resource: Resource, resource_id: int | None, payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Overlay proposed fields on the stored resource for authorization."""
        row = self.store.get(resource, resource_id) if resource_id is not None else None
        return {**(row or {}), **(payload or {})}

    def resolve(
        self, resource: Resource, resource_id: int | None, payload: dict[str, Any] | None = None
    ) -> ResourceOwner:
        """Resolve both ownership dimensions from the same resource snapshot."""
        values = self.values(resource, resource_id, payload)
        round_id = self.round_id(resource, values)
        return ResourceOwner(self.committee_id(resource, values, round_id), round_id)

    def round_id(self, resource: Resource, values: dict[str, Any]) -> int | None:
        """Follow the resource's round reference using only this Store."""
        if resource == EXAM_ROUND:
            return values.get("id")
        if resource in ROUND_OWNED_RESOURCES:
            return values.get("exam_round_id")
        if resource == CANDIDATE:
            return self._candidate_round_id(values)
        if resource in DAY_OWNED_RESOURCES:
            return self._day_round_id(values.get("exam_day_id"))
        if resource == CANDIDATE_EXAM_ATTENDANCE:
            slot = self.store.get(EXAM_SLOT, values.get("exam_slot_id"))
            return self._day_round_id(slot["exam_day_id"]) if slot else None
        return None

    def _candidate_round_id(self, values: dict[str, Any]) -> int | None:
        if values.get("exam_round_id") is not None:
            return values["exam_round_id"]
        assignment = self.store.first(
            CANDIDATE_COMMITTEE_ASSIGNMENT, candidate_id=values.get("id"), ended_at=None
        )
        return assignment.get("exam_round_id") if assignment else None

    def _day_round_id(self, day_id: int | None) -> int | None:
        day = self.store.get(EXAM_DAY, day_id)
        return day.get("exam_round_id") if day else None

    def committee_id(
        self, resource: Resource, values: dict[str, Any], round_id: int | None
    ) -> int | None:
        """Resolve the committee while retaining direct-resource ownership rules."""
        if resource == COMMITTEE:
            return values.get("id")
        if resource in {EXAM_ROUND, COMMITTEE_MEMBER}:
            return values.get("committee_id")
        if resource == PERSON:
            member = self.store.first(COMMITTEE_MEMBER, person_id=values.get("id"))
            return member["committee_id"] if member else None
        if resource == EXAM_HALF_YEAR:
            exam_round = self.store.first(EXAM_ROUND, exam_half_year_id=values.get("id"))
        else:
            exam_round = self.store.get(EXAM_ROUND, round_id)
        return exam_round.get("committee_id") if exam_round else None
