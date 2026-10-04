"""Provider and repository contracts owned by Planning's venue use cases."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from contextlib import AbstractContextManager
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
        "expected_revision",
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
    GEOCODING_ADDRESS = "geocoding_address"
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
class VenueCommandFacts:
    """Detached facts read by a write adapter inside the command transaction."""

    current: Mapping[str, object] | None = None
    venue_id: int | None = None
    venue_active: bool = False
    has_active_room: bool = False
    room_active: bool = False
    has_another_active_room: bool = False
    promotion_status: str | None = None
    room_venue_ids: Mapping[int, int] | None = None
    duplicate_candidates: tuple[Mapping[str, object], ...] | None = None
    has_future_confirmed_assignments: bool | None = None

    def __post_init__(self) -> None:
        if self.current is not None:
            object.__setattr__(self, "current", MappingProxyType(dict(self.current)))
        if self.room_venue_ids is not None:
            object.__setattr__(self, "room_venue_ids", MappingProxyType(dict(self.room_venue_ids)))
        if self.duplicate_candidates is not None:
            object.__setattr__(
                self,
                "duplicate_candidates",
                tuple(MappingProxyType(dict(candidate)) for candidate in self.duplicate_candidates),
            )


@dataclass(frozen=True)
class VenueMutationPlan:
    """Planning-validated values and audit basis passed back to Persistence."""

    values: Mapping[str, object]
    reason: str | None = None
    audit_values: Mapping[str, object] | None = None
    room_ids: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        if self.audit_values is not None:
            object.__setattr__(self, "audit_values", MappingProxyType(dict(self.audit_values)))


@dataclass(frozen=True)
class VenueFutureImpactFacts:
    """Detached venue/room state used to plan a future-impact query."""

    venue_id: int
    entity_type: str
    entity_id: int
    current: Mapping[str, object]
    before: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "current", MappingProxyType(dict(self.current)))
        object.__setattr__(self, "before", MappingProxyType(dict(self.before)))


@dataclass(frozen=True)
class VenueGeocodingAddress:
    """Address and revision captured from one detached venue read."""

    revision: int
    address: str


@dataclass(frozen=True)
class VenueQuery:
    """Typed request to read a venue aggregate or its planning impact."""

    kind: VenueQueryKind
    entity_id: int | None = None
    values: Mapping[str, object] | None = None
    room_id: int | None = None
    visible_venue_ids: frozenset[int] | None = None
    excluded_id: int | None = None
    expected_revision: int | None = None

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

    def write_uow(
        self, command: VenueCommand
    ) -> AbstractContextManager[VenueCommandUnitOfWork]: ...

    def query(self, query: VenueQuery) -> VenueQueryResult: ...


class VenueCommandUnitOfWork(Protocol):
    """Active command transaction exposing detached facts and plan persistence."""

    def facts(self) -> VenueCommandFacts: ...

    def commit(self, plan: VenueMutationPlan) -> VenueCommandResult: ...


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
