"""Consumer-owned contracts for authorization and visible resource reads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from backend.identity.authorization import AuthorizationScope


class ResourceKind(StrEnum):
    """Stable application identities for resources covered by HTTP scope rules."""

    COMMITTEE = "committee"
    PERSON = "person"
    COMMITTEE_MEMBER = "committee_member"
    EXAM_HALF_YEAR = "exam_half_year"
    EXAM_ROUND = "exam_round"
    ROUND_CANDIDATE = "round_candidate"
    CANDIDATE = "candidate"
    CANDIDATE_COMMITTEE_ASSIGNMENT = "candidate_committee_assignment"
    PLANNING_SETTINGS = "planning_settings"
    CANDIDATE_EXAM_DAY = "candidate_exam_day"
    MEMBER_AVAILABILITY = "member_availability"
    EXAM_DAY = "exam_day"
    EXAM_SLOT = "exam_slot"
    EXAM_DAY_ASSIGNMENT = "exam_day_assignment"
    CANDIDATE_EXAM_ATTENDANCE = "candidate_exam_attendance"
    MEMBER_EXAM_ATTENDANCE = "member_exam_attendance"
    EXAM_VENUE = "exam_venue"


class ResourceReferenceField(StrEnum):
    """Ownership-related references that a resource command may propose."""

    COMMITTEE_ID = "committee_id"
    PERSON_ID = "person_id"
    EXAM_HALF_YEAR_ID = "exam_half_year_id"
    EXAM_ROUND_ID = "exam_round_id"
    CANDIDATE_ID = "candidate_id"
    ROUND_CANDIDATE_ID = "round_candidate_id"
    EXAM_DAY_ID = "exam_day_id"
    EXAM_SLOT_ID = "exam_slot_id"
    COMMITTEE_MEMBER_ID = "committee_member_id"
    CANDIDATE_EXAM_DAY_ID = "candidate_exam_day_id"


@dataclass(frozen=True)
class ResourceReferenceChange:
    """One typed reference override from an application command."""

    field: ResourceReferenceField
    value: int | None


@runtime_checkable
class ResourceReferences(Protocol):
    """Materialized ownership references; no ORM model or query expression."""

    committee_id: int | None
    person_id: int | None
    exam_half_year_id: int | None
    exam_round_id: int | None
    candidate_id: int | None
    round_candidate_id: int | None
    exam_day_id: int | None
    exam_slot_id: int | None
    committee_member_id: int | None
    candidate_exam_day_id: int | None

    def value(self, field: ResourceReferenceField) -> int | None: ...


@runtime_checkable
class ResourceOwnership(Protocol):
    """Authorization-only owner and reference snapshot for one resource."""

    committee_id: int | None
    round_id: int | None
    references: ResourceReferences
    exists: bool


@runtime_checkable
class CommitteeMemberIdentity(Protocol):
    """Small persisted membership facts needed by self-service authorization."""

    member_id: int
    person_id: int
    committee_id: int
    is_active: bool


ResourceProjection = dict[str, object]
ResourceFilters = Mapping[str, object]


class ResourceAccessQueries(Protocol):
    """Queries that materialize authorization facts and scoped projections."""

    def ownership(
        self,
        resource: ResourceKind,
        resource_id: int | None,
        changes: Sequence[ResourceReferenceChange] = (),
    ) -> ResourceOwnership: ...

    def committee_member(self, member_id: int) -> CommitteeMemberIdentity | None: ...

    def list_visible(
        self,
        resource: ResourceKind,
        scope: AuthorizationScope,
        filters: ResourceFilters | None = None,
    ) -> Sequence[ResourceProjection]: ...

    def get_visible(
        self, resource: ResourceKind, resource_id: int, scope: AuthorizationScope
    ) -> ResourceProjection | None: ...

    def list_members(
        self,
        filters: ResourceFilters | None = None,
        scope: AuthorizationScope | None = None,
    ) -> Sequence[ResourceProjection]: ...

    def get_member(
        self, member_id: int, scope: AuthorizationScope | None = None
    ) -> ResourceProjection | None: ...


class ResourceAccessQueryFactory(Protocol):
    """Bind resource queries to a read snapshot or caller-owned write UoW."""

    def snapshot(self) -> AbstractContextManager[ResourceAccessQueries]: ...

    def for_transaction(self, transaction: object) -> ResourceAccessQueries:
        """Bind queries to an opaque, caller-owned write transaction."""


def reference_changes(payload: Mapping[str, object]) -> tuple[ResourceReferenceChange, ...]:
    """Validate and extract typed ownership references from a transport payload."""
    changes = []
    for field in ResourceReferenceField:
        if field.value in payload:
            value = payload[field.value]
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"{field.value} must be an integer or None")
            changes.append(ResourceReferenceChange(field, value))
    return tuple(changes)
