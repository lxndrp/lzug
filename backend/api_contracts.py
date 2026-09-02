"""Pydantic models used at the public FastAPI contract boundary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    error: str


class HealthResponse(BaseModel):
    status: str
    version: str
    revision: str
    links: dict[str, object] = Field(alias="_links")


class ApiRootResponse(BaseModel):
    version: str
    links: dict[str, object] = Field(alias="_links")


class LoginRequest(BaseModel):
    email: str = ""
    password: str = ""
    second_factor: str = ""


class TokenRequest(BaseModel):
    token: str = ""


class FactorActivationRequest(BaseModel):
    token: str = ""
    password: str = ""
    totp_secret: str = ""
    totp_code: str = ""


class FrontendErrorRequest(BaseModel):
    kind: str
    status: int | None = None


class SessionResponse(BaseModel):
    authenticated: bool
    account_id: int
    person_id: int | None
    committee_member_id: int | None
    is_operator: bool
    demo_role: Literal["chair", "examiner", "replacement"] | None = None
    display_name: str | None = None
    capabilities: list[str] | None = None
    demo_matrix_version: str | None = None
    demo_workspace_expires_at: str | None = None


class SessionRotationResponse(BaseModel):
    status: str
    expires_at: str


class DemoScenarioRoleResponse(BaseModel):
    name: Literal["chair", "examiner", "replacement"]
    display_name: str
    task: str


class DemoScenarioResponse(BaseModel):
    id: str
    title: str
    status: Literal["ready", "in_progress", "complete"]
    completed_steps: int
    total_steps: int
    next_role: Literal["chair", "examiner", "replacement"]
    next_action: str
    path: str


class DemoPreparedPlanChangeResponse(BaseModel):
    round_id: int
    day_id: int
    source_location_id: int
    target_location_id: int
    assignment_id: int
    replacement_member_id: int
    reason: str


class DemoScenarioOverviewResponse(BaseModel):
    mode: Literal["demo"]
    demo_matrix_version: str
    current_role: Literal["chair", "examiner", "replacement"]
    created_at: str
    expires_at: str
    remaining_seconds: int
    roles: list[DemoScenarioRoleResponse]
    scenarios: list[DemoScenarioResponse]
    prepared_plan_change: DemoPreparedPlanChangeResponse
    notices: list[str]
    location_contract: str


class DemoScenarioResetResponse(BaseModel):
    status: Literal["reset"]
    role: Literal["chair", "examiner", "replacement"]
    expires_at: str


class DomainResourceWrite(BaseModel):
    model_config = ConfigDict(extra="allow")


class DomainResourceResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class DomainCollectionResponse(BaseModel):
    items: list[DomainResourceResponse]
    links: dict[str, object] = Field(alias="_links")


class ExamRoomResponse(BaseModel):
    """One concrete room nested below its reusable exam venue."""

    model_config = ConfigDict(extra="allow")

    id: int
    venue_id: int
    name: str
    building: str | None
    wing: str | None
    floor: str | None
    room_number: str | None
    access_notes: str | None
    capacity: int | None
    is_active: int
    revision: int
    created_at: str
    updated_at: str
    links: dict[str, object] = Field(alias="_links")


class ExamVenueContactResponse(BaseModel):
    """Non-authentication contact information for a venue or selected rooms."""

    model_config = ConfigDict(extra="allow")

    id: int
    venue_id: int
    label: str
    role: str | None
    phone: str | None
    email: str | None
    availability_notes: str | None
    is_active: int
    revision: int
    created_at: str
    updated_at: str
    room_ids: list[int]
    links: dict[str, object] = Field(alias="_links")


class ExamVenueResponse(BaseModel):
    """The public aggregate representation for venue master data."""

    model_config = ConfigDict(extra="allow")

    id: int
    scope: str
    committee_id: int | None
    name: str
    street: str
    postal_code: str
    city: str
    country: str
    site_name: str | None
    entrance: str | None
    travel_directions: str | None
    is_accessible: int | None
    accessibility_status: str
    accessibility_notes: str | None
    latitude: float | None
    longitude: float | None
    coordinate_status: str
    coordinate_source: str | None
    is_active: int
    revision: int
    created_at: str
    updated_at: str
    rooms: list[ExamRoomResponse]
    contacts: list[ExamVenueContactResponse]
    links: dict[str, object] = Field(alias="_links")


class ExamVenueCollectionResponse(BaseModel):
    """Venue collection envelope used by the public master-data API."""

    items: list[ExamVenueResponse]
    links: dict[str, object] = Field(alias="_links")


class LegacyLocationResponse(BaseModel):
    """Temporary read projection retained while the frontend moves to rooms."""

    model_config = ConfigDict(extra="allow")

    id: int
    venue_id: int
    committee_id: int | None
    name: str
    street: str
    postal_code: str
    city: str
    room: str
    is_active: int
    created_at: str
    updated_at: str
    links: dict[str, object] = Field(alias="_links")


class LegacyLocationCollectionResponse(BaseModel):
    """Envelope for the deprecated, read-only location projection."""

    items: list[LegacyLocationResponse]
    links: dict[str, object] = Field(alias="_links")


class ExamVenueCreateRequest(BaseModel):
    """Document the accepted command fields without duplicating domain validation."""

    model_config = ConfigDict(extra="forbid")

    scope: str
    committee_id: int | None
    name: str
    street: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = "Deutschland"
    site_name: str | None = None
    entrance: str | None = None
    travel_directions: str | None = None
    is_accessible: bool | int | None = None
    accessibility_status: str = "needs_clarification"
    accessibility_notes: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    coordinate_status: str = "missing"
    coordinate_source: str | None = None
    is_active: bool | int = False
    reason: str | None = None
    duplicates_reviewed: bool = False
    duplicate_reason: str | None = None


class ExamVenueUpdateRequest(BaseModel):
    """Revision-guarded partial update for an existing exam venue."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    name: str | None = None
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None
    site_name: str | None = None
    entrance: str | None = None
    travel_directions: str | None = None
    is_accessible: bool | int | None = None
    accessibility_status: str | None = None
    accessibility_notes: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    coordinate_status: str | None = None
    coordinate_source: str | None = None
    is_active: bool | int | None = None
    reason: str | None = None
    duplicates_reviewed: bool = False
    duplicate_reason: str | None = None
    confirm_future_assignments: bool = False


class ExamRoomCreateRequest(BaseModel):
    """Create one room under an existing exam venue."""

    model_config = ConfigDict(extra="forbid")

    name: str
    building: str | None = None
    wing: str | None = None
    floor: str | None = None
    room_number: str | None = None
    access_notes: str | None = None
    capacity: int | None = None
    is_active: bool | int = True
    reason: str | None = None


class ExamRoomUpdateRequest(BaseModel):
    """Revision-guarded partial update for one exam room."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    name: str | None = None
    building: str | None = None
    wing: str | None = None
    floor: str | None = None
    room_number: str | None = None
    access_notes: str | None = None
    capacity: int | None = None
    is_active: bool | int | None = None
    reason: str | None = None
    confirm_future_assignments: bool = False


class ExamVenueContactCreateRequest(BaseModel):
    """Create a venue-wide or room-specific non-authentication contact."""

    model_config = ConfigDict(extra="forbid")

    label: str
    role: str | None = None
    phone: str | None = None
    email: str | None = None
    availability_notes: str | None = None
    is_active: bool | int = True
    room_ids: list[int] | None = None
    reason: str | None = None


class ExamVenueContactUpdateRequest(BaseModel):
    """Revision-guarded partial update for a venue contact."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    label: str | None = None
    role: str | None = None
    phone: str | None = None
    email: str | None = None
    availability_notes: str | None = None
    is_active: bool | int | None = None
    room_ids: list[int] | None = None
    reason: str | None = None


class RevisionDeleteRequest(BaseModel):
    """The optimistic-lock command required before deleting aggregate entities."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    reason: str | None = None


class ExamVenueDuplicateCheckRequest(BaseModel):
    """Candidate fields used for a non-mutating duplicate preview."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    street: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = "Deutschland"
    excluded_id: int | None = None


class ExamVenuePromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    reason: str


class ExamVenuePromotionDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    decision: str
    reason: str
