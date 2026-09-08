"""Pydantic models used at the public FastAPI contract boundary."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ErrorResponse(BaseModel):
    error: object


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
    model_config = ConfigDict(extra="forbid")

    kind: Literal["bootstrap", "http", "runtime"]
    status: int | None = Field(default=None, ge=0, le=599)


class CalendarFeedActivationRequest(BaseModel):
    """Document the compatible boolean forms accepted when rotating a feed."""

    rotate: bool = False

    @field_validator("rotate", mode="before")
    @classmethod
    def normalize_compatible_boolean(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        raise ValueError("Expected boolean value")


class CalendarStatusResponse(BaseModel):
    active: bool
    activated_at: str | None
    revoked_at: str | None
    time_zone: str
    links: dict[str, object] = Field(alias="_links")


class CalendarFeedActivationResponse(CalendarStatusResponse):
    feed_url: str
    notice: str


class CalendarFeedRevocationResponse(CalendarStatusResponse):
    notice: str


class CalendarEventCollectionResponse(BaseModel):
    items: list[dict[str, object]]
    links: dict[str, object] = Field(alias="_links")


class NotificationCollectionResponse(BaseModel):
    items: list[dict[str, object]]
    links: dict[str, object] = Field(alias="_links")


class NotificationChannelsResponse(BaseModel):
    web_push: dict[str, object]
    email_fallback_configured: bool
    sink_enabled: bool


class PushSubscriptionRequest(BaseModel):
    endpoint: str


class PushSubscriptionResponse(BaseModel):
    id: int
    active: bool


class PushConfirmationResponse(BaseModel):
    status: Literal["technically_confirmed"]


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


class ExamSlotStartRequest(BaseModel):
    """Optional factual timestamp supplied when an exam actually starts."""

    model_config = ConfigDict(extra="allow")

    actual_started_at: str | None = None


class ExamAttendanceUpdateRequest(BaseModel):
    """Attendance fact recorded for a candidate or committee assignment."""

    model_config = ConfigDict(extra="allow")

    status: Literal["open", "present", "late", "absent"]
    arrived_at: str | None = None


class ExamSlotStatusUpdateRequest(BaseModel):
    """Execution status transition, including facts accepted during correction."""

    model_config = ConfigDict(extra="allow")

    status: Literal["open", "running", "completed", "cancelled", "needs_follow_up"]
    reason: str | None = None
    actual_started_at: str | None = None
    actual_completed_at: str | None = None


class ExamProtocolEntryRequest(BaseModel):
    """One factual occurrence in a versioned exam protocol."""

    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "late_start",
        "interruption",
        "termination",
        "different_staffing",
        "procedural_deviation",
        "objection_or_reservation",
        "other",
    ]
    statement: str
    occurred_from: str
    occurred_to: str | None = None


class ExamProtocolContentRequest(BaseModel):
    """Version-guarded replacement of the protocol's factual content."""

    model_config = ConfigDict(extra="allow")

    version: int
    declaration: Literal["without_special_occurrences", "with_special_occurrences"]
    entries: list[ExamProtocolEntryRequest] = Field(default_factory=list)
    change_reason: str | None = None


class ExamProtocolResponseRequest(BaseModel):
    """Participant confirmation or reservation for one protocol version."""

    model_config = ConfigDict(extra="allow")

    version: int
    response: Literal["confirmed", "reservation"]
    entry_id: int | None = None
    statement: str | None = None


class AssessmentModelBindingRequest(BaseModel):
    """Version-aware binding of one assessment model to an exam round."""

    model_config = ConfigDict(extra="allow")

    assessment_model_version_id: int
    reason: str
    version: int | None = None


class IndividualAssessmentRequest(BaseModel):
    """One examiner's version-guarded criterion assessment."""

    model_config = ConfigDict(extra="allow")

    version: int
    component_key: str
    criterion_key: str
    raw_points: Decimal
    submitted: bool = False
    rationale: str | None = None
    change_reason: str | None = None


class PlanningRoundRequest(BaseModel):
    """Select the exam round for a body-scoped planning operation."""

    model_config = ConfigDict(extra="allow")

    round_id: int = 1


class PlanningProposalSlotPayload(BaseModel):
    """One ordered candidate slot within a complete planning aggregate."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    round_candidate_id: int
    slot_type: str
    starts_at: str = ""
    ends_at: str = ""
    sequence_number: int = 0
    status: str = "proposed"


class PlanningProposalAssignmentPayload(BaseModel):
    """One examiner or fallback assignment within a planning day part."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    committee_member_id: int
    assignment_role: str
    day_part: str
    fallback_status: str | None = None


class PlanningProposalDayPayload(BaseModel):
    """One candidate exam day and its complete editable planning content."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    candidate_exam_day_id: int
    room_id: int | None = None
    location_id: int | None = None
    date: str = ""
    status: str = "proposed"
    slots: list[PlanningProposalSlotPayload]
    assignments: list[PlanningProposalAssignmentPayload]


class PlanningProposalWriteRequest(BaseModel):
    """Complete optimistic-lock command for replacing one planning proposal."""

    model_config = ConfigDict(extra="allow")

    round_id: int
    revision: int
    exam_days: list[PlanningProposalDayPayload]


class ConfirmedPlanChangeRequest(PlanningProposalWriteRequest):
    """Complete confirmed-plan replacement with its mandatory audit reason."""

    reason: str


class PlanningProposalResponse(PlanningProposalWriteRequest):
    """Editable proposal or confirmed plan returned by the aggregate routes."""

    links: dict[str, object] = Field(default_factory=dict, alias="_links")


class PlanningProposalResultResponse(PlanningProposalResponse):
    """Generated planning proposal including validation and count summaries."""

    status: str
    validation: dict[str, object]
    counts: dict[str, int]


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
    map_provider: dict[str, str]
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
    meaningful_change: bool = True


class ExamVenueGeocodeRequest(BaseModel):
    """Require an explicit, revision-safe request before contacting Nominatim."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int


class ExamVenueGeocodeResponse(BaseModel):
    latitude: float
    longitude: float
    source: str


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
    meaningful_change: bool = True


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
