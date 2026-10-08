"""Consumer-owned calendar snapshots and persistence capabilities."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CalendarScope:
    """Active identity scope passed into calendar-facing application use cases."""

    person_id: int | None
    member_ids: frozenset[int]


@dataclass(frozen=True)
class CalendarMembership:
    """Minimal active-membership projection needed by calendar authorization."""

    member_id: int
    committee_id: int


@dataclass(frozen=True)
class CalendarSlotSnapshot:
    id: int
    starts_at: str
    ends_at: str
    status: str
    sequence_number: int


@dataclass(frozen=True)
class CalendarAssignmentSnapshot:
    """Materialized Planning values consumed while projecting one assignment."""

    id: int
    round_id: int
    half_year_id: int
    round_name: str
    round_status: str
    day_id: int
    day_date: str
    day_status: str
    member_id: int
    assignment_role: str
    day_part: str
    room_name: str | None
    room_building: str | None
    room_wing: str | None
    room_floor: str | None
    room_number: str | None
    room_access_notes: str | None
    venue_name: str | None
    venue_site_name: str | None
    venue_street: str | None
    venue_postal_code: str | None
    venue_city: str | None
    venue_country: str | None
    venue_entrance: str | None
    venue_travel_directions: str | None
    slots: tuple[CalendarSlotSnapshot, ...]


@dataclass(frozen=True)
class CalendarRoundSnapshot:
    id: int
    half_year_id: int
    name: str
    status: str
    assignments: tuple[CalendarAssignmentSnapshot, ...]


@dataclass(frozen=True)
class CalendarFeedSnapshot:
    person_id: int
    token_hash: str
    created_at: str
    revoked_at: str | None


@dataclass(frozen=True)
class CalendarFeedStatus:
    active: bool
    activated_at: str | None
    revoked_at: str | None
    time_zone: str


@dataclass(frozen=True)
class CalendarFeedActivation:
    status: CalendarFeedStatus
    token: str


@dataclass(frozen=True)
class CalendarEventProjection:
    id: int
    external_event_id: str
    date: str
    starts_at: str
    ends_at: str
    time_zone: str
    location: str
    role: str
    round_name: str
    status: str
    version: int


@dataclass(frozen=True)
class CalendarEventSnapshot:
    id: int | None
    external_event_id: str
    exam_half_year_id: int
    exam_round_id: int
    exam_day_id: int | None
    exam_day_assignment_id: int | None
    recipient_member_id: int
    date: str
    starts_at: str
    ends_at: str
    time_zone: str
    location: str
    role: str
    round_name: str
    source_key: str
    version: int
    status: str
    content_hash: str
    sent_at: str | None
    created_at: str
    updated_at: str


class CalendarIdentitySnapshotPort(Protocol):
    """Read the active memberships that authorize a personal calendar."""

    def active_memberships(self, person_id: int) -> Sequence[CalendarMembership]: ...


class CalendarPlanningSnapshotPort(Protocol):
    """Read detached confirmed-plan values for calendar projection."""

    def current_half_year_id(self) -> int | None: ...

    def confirmed_round_ids(self, half_year_id: int) -> Sequence[int]: ...

    def round_snapshot(
        self, round_id: int, *, member_ids: frozenset[int] | None = None
    ) -> CalendarRoundSnapshot | None: ...

    def assignment_snapshot(self, assignment_id: int) -> CalendarAssignmentSnapshot | None: ...


class CalendarUnitOfWork(Protocol):
    """Calendar-owned persistence operations for one atomic projection or lifecycle."""

    def feed_for_person(self, person_id: int) -> CalendarFeedSnapshot | None: ...

    def active_feed_for_token(self, token_hash: str) -> CalendarFeedSnapshot | None: ...

    def save_feed(self, feed: CalendarFeedSnapshot) -> None: ...

    def revoke_feed(self, person_id: int, revoked_at: str) -> bool: ...

    def events_for_source(self, source_prefix: str) -> Sequence[CalendarEventSnapshot]: ...

    def events_for_round(
        self,
        round_id: int,
        *,
        person_id: int | None = None,
    ) -> Sequence[CalendarEventSnapshot]: ...

    def events_for_members_in_period(
        self, member_ids: frozenset[int], half_year_id: int
    ) -> Sequence[CalendarEventSnapshot]: ...

    def event_for_members(
        self, event_id: int, member_ids: frozenset[int]
    ) -> CalendarEventSnapshot | None: ...

    def save_event(self, event: CalendarEventSnapshot) -> CalendarEventSnapshot: ...


class CalendarUnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractContextManager[CalendarUnitOfWork]: ...
