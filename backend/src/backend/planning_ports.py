"""Provider and repository contracts owned by Planning's venue use cases."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol


class ExamVenueError(ValueError):
    """Base error for a rejected venue-master-data command."""


class ExamVenueConflictError(ExamVenueError):
    """Signal a stale revision or a conflicting uniqueness invariant."""


class ExamVenueNotFoundError(ExamVenueError):
    """Signal an absent venue aggregate entity."""


class ExamVenueInUseError(ExamVenueError):
    """Signal an entity that still has durable planning or migration references."""


class ExamVenueConfirmationRequiredError(ExamVenueError):
    """Signal that a visible impact or duplicate warning needs confirmation."""


VENUE_SCOPES = frozenset({"global", "committee"})
ACCESSIBILITY_STATUSES = frozenset({"confirmed", "needs_clarification"})
COORDINATE_STATUSES = frozenset({"missing", "confirmed", "needs_review"})
VENUE_FIELDS = frozenset(
    {
        "scope",
        "committee_id",
        "name",
        "street",
        "postal_code",
        "city",
        "country",
        "site_name",
        "entrance",
        "travel_directions",
        "is_accessible",
        "accessibility_status",
        "accessibility_notes",
        "latitude",
        "longitude",
        "coordinate_status",
        "coordinate_source",
        "is_active",
    }
)
ROOM_FIELDS = frozenset(
    {"name", "building", "wing", "floor", "room_number", "access_notes", "capacity", "is_active"}
)
CONTACT_FIELDS = frozenset(
    {"label", "role", "phone", "email", "availability_notes", "is_active", "room_ids"}
)
COMMAND_META_FIELDS = frozenset(
    {
        "reason",
        "duplicates_reviewed",
        "duplicate_reason",
        "confirm_future_assignments",
        "meaningful_change",
    }
)
VENUE_DUPLICATE_FIELDS = frozenset({"name", "street", "postal_code", "city", "country"})


def normalize_venue_text(value: object) -> str:
    """Return the exact-match key used for names and migration grouping."""
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    return " ".join(normalized.split()).casefold()


@dataclass(frozen=True)
class GeocodeCandidate:
    """Validated coordinates returned by an explicitly requested address lookup."""

    latitude: float
    longitude: float
    source: str


@dataclass(frozen=True)
class VenueRoomAvailability:
    """Detached values needed to decide whether a room can be planned."""

    room_active: bool
    venue_active: bool
    venue_scope: str
    committee_id: int | None
    coordinate_status: str


def room_is_usable_for_committee(
    availability: VenueRoomAvailability | None,
    committee_id: int,
    *,
    require_confirmed_coordinates: bool = False,
) -> bool:
    """Decide room eligibility from detached values and explicit provider policy."""
    return bool(
        availability
        and availability.room_active
        and availability.venue_active
        and (availability.venue_scope == "global" or availability.committee_id == committee_id)
        and (not require_confirmed_coordinates or availability.coordinate_status == "confirmed")
    )


class Geocoder(Protocol):
    """Port for one address lookup; provider configuration stays in Root."""

    def geocode(self, address: str) -> GeocodeCandidate: ...


@dataclass(frozen=True)
class VenueChange:
    """Committed venue mutation available to follow-up orchestration."""

    audit_id: int
    venue_id: int
    entity_type: str
    entity_id: int
    revision: int
    changed_fields: frozenset[str]


class VenueCommandKind(StrEnum):
    """Supported venue aggregate mutations owned by Planning."""

    CREATE_VENUE = "create_venue"
    UPDATE_VENUE = "update_venue"
    DELETE_VENUE = "delete_venue"
    CREATE_ROOM = "create_room"
    UPDATE_ROOM = "update_room"
    DELETE_ROOM = "delete_room"
    CREATE_CONTACT = "create_contact"
    UPDATE_CONTACT = "update_contact"
    DELETE_CONTACT = "delete_contact"
    REQUEST_PROMOTION = "request_promotion"
    DECIDE_PROMOTION = "decide_promotion"


class VenueQueryKind(StrEnum):
    """Read-only venue aggregate queries exposed by Planning."""

    LIST_VENUES = "list_venues"
    GET_VENUE = "get_venue"
    ADDRESS_LABEL = "address_label"
    REFERENCED_COMMITTEES = "referenced_committee_ids"
    FUTURE_IMPACT = "future_impact"
    FIND_DUPLICATES = "find_duplicates"
    LIST_PENDING_PROMOTIONS = "list_pending_promotions"


@dataclass(frozen=True)
class VenueCommand:
    """Typed request to mutate a venue aggregate inside one repository UoW."""

    kind: VenueCommandKind
    entity_id: int | None = None
    values: Mapping[str, object] | None = None
    actor_member_id: int | None = None
    technical_actor: str | None = None
    reason: str | None = None
    decision: str | None = None
    expected_revision: int | None = None

    def __post_init__(self) -> None:
        if self.values is not None:
            object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True)
class VenueQuery:
    """Typed request to read a venue aggregate or its planning impact."""

    kind: VenueQueryKind
    entity_id: int | None = None
    values: Mapping[str, object] | None = None
    room_id: int | None = None
    visible_venue_ids: frozenset[int] | None = None
    excluded_id: int | None = None

    def __post_init__(self) -> None:
        if self.values is not None:
            object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True)
class VenueCommandResult:
    """Detached typed result from one committed venue command."""

    value: object
    change: VenueChange | None = None


@dataclass(frozen=True)
class VenueQueryResult:
    """Detached typed result from one venue repository query."""

    value: object


class VenueRepository(Protocol):
    """Planning-owned read/query and write-command port for exam venues."""

    def execute(self, command: VenueCommand) -> VenueCommandResult: ...

    def query(self, query: VenueQuery) -> VenueQueryResult: ...


class VenueImpactQuery(Protocol):
    """Read-only Planning query for the effects of a proposed venue change."""

    def preview(
        self,
        *,
        venue_id: int,
        entity_type: str,
        entity_id: int,
        before: Mapping[str, object],
        after: Mapping[str, object],
        meaningful_change: bool = True,
    ) -> Mapping[str, object]: ...


class VenueChangeFollowUp(Protocol):
    """Explicit post-commit transition for a committed venue change."""

    def process(self, change: VenueChange) -> Mapping[str, object]: ...
