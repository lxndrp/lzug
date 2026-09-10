// Generated from the canonical FastAPI OpenAPI document.
// Do not edit manually. Run `task frontend:transport:generate`.

export type ClientOptions = {
    baseUrl: `${string}://${string}` | (string & {});
};

/**
 * ApiRootResponse
 */
export type ApiRootResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Version
     */
    version: string;
};

/**
 * AssessmentModelBindingRequest
 *
 * Version-aware binding of one assessment model to an exam round.
 */
export type AssessmentModelBindingRequest = {
    /**
     * Assessment Model Version Id
     */
    assessment_model_version_id: number;
    /**
     * Reason
     */
    reason: string;
    /**
     * Version
     */
    version?: number | null;
    [key: string]: unknown;
};

/**
 * CalendarEventCollectionResponse
 */
export type CalendarEventCollectionResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Items
     */
    items: Array<{
        [key: string]: unknown;
    }>;
};

/**
 * CalendarFeedActivationRequest
 *
 * Document the compatible boolean forms accepted when rotating a feed.
 */
export type CalendarFeedActivationRequest = {
    /**
     * Rotate
     */
    rotate?: boolean;
};

/**
 * CalendarFeedActivationResponse
 */
export type CalendarFeedActivationResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Activated At
     */
    activated_at: string | null;
    /**
     * Active
     */
    active: boolean;
    /**
     * Feed Url
     */
    feed_url: string;
    /**
     * Notice
     */
    notice: string;
    /**
     * Revoked At
     */
    revoked_at: string | null;
    /**
     * Time Zone
     */
    time_zone: string;
};

/**
 * CalendarFeedRevocationResponse
 */
export type CalendarFeedRevocationResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Activated At
     */
    activated_at: string | null;
    /**
     * Active
     */
    active: boolean;
    /**
     * Notice
     */
    notice: string;
    /**
     * Revoked At
     */
    revoked_at: string | null;
    /**
     * Time Zone
     */
    time_zone: string;
};

/**
 * CalendarStatusResponse
 */
export type CalendarStatusResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Activated At
     */
    activated_at: string | null;
    /**
     * Active
     */
    active: boolean;
    /**
     * Revoked At
     */
    revoked_at: string | null;
    /**
     * Time Zone
     */
    time_zone: string;
};

/**
 * ConfirmedPlanChangeRequest
 *
 * Complete confirmed-plan replacement with its mandatory audit reason.
 */
export type ConfirmedPlanChangeRequest = {
    /**
     * Exam Days
     */
    exam_days: Array<PlanningProposalDayPayload>;
    /**
     * Reason
     */
    reason: string;
    /**
     * Revision
     */
    revision: number;
    /**
     * Round Id
     */
    round_id: number;
    [key: string]: unknown;
};

/**
 * DemoPreparedPlanChangeResponse
 */
export type DemoPreparedPlanChangeResponse = {
    /**
     * Assignment Id
     */
    assignment_id: number;
    /**
     * Day Id
     */
    day_id: number;
    /**
     * Reason
     */
    reason: string;
    /**
     * Replacement Member Id
     */
    replacement_member_id: number;
    /**
     * Round Id
     */
    round_id: number;
    /**
     * Source Location Id
     */
    source_location_id: number;
    /**
     * Target Location Id
     */
    target_location_id: number;
};

/**
 * DemoScenarioOverviewResponse
 */
export type DemoScenarioOverviewResponse = {
    /**
     * Created At
     */
    created_at: string;
    /**
     * Current Role
     */
    current_role: 'chair' | 'examiner' | 'replacement';
    /**
     * Demo Matrix Version
     */
    demo_matrix_version: string;
    /**
     * Expires At
     */
    expires_at: string;
    /**
     * Location Contract
     */
    location_contract: string;
    /**
     * Mode
     */
    mode: 'demo';
    /**
     * Notices
     */
    notices: Array<string>;
    prepared_plan_change: DemoPreparedPlanChangeResponse;
    /**
     * Remaining Seconds
     */
    remaining_seconds: number;
    /**
     * Roles
     */
    roles: Array<DemoScenarioRoleResponse>;
    /**
     * Scenarios
     */
    scenarios: Array<DemoScenarioResponse>;
};

/**
 * DemoScenarioResetResponse
 */
export type DemoScenarioResetResponse = {
    /**
     * Expires At
     */
    expires_at: string;
    /**
     * Role
     */
    role: 'chair' | 'examiner' | 'replacement';
    /**
     * Status
     */
    status: 'reset';
};

/**
 * DemoScenarioResponse
 */
export type DemoScenarioResponse = {
    /**
     * Completed Steps
     */
    completed_steps: number;
    /**
     * Id
     */
    id: string;
    /**
     * Next Action
     */
    next_action: string;
    /**
     * Next Role
     */
    next_role: 'chair' | 'examiner' | 'replacement';
    /**
     * Path
     */
    path: string;
    /**
     * Status
     */
    status: 'ready' | 'in_progress' | 'complete';
    /**
     * Title
     */
    title: string;
    /**
     * Total Steps
     */
    total_steps: number;
};

/**
 * DemoScenarioRoleResponse
 */
export type DemoScenarioRoleResponse = {
    /**
     * Display Name
     */
    display_name: string;
    /**
     * Name
     */
    name: 'chair' | 'examiner' | 'replacement';
    /**
     * Task
     */
    task: string;
};

/**
 * DomainCollectionResponse
 */
export type DomainCollectionResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Items
     */
    items: Array<DomainResourceResponse>;
};

/**
 * DomainResourceResponse
 */
export type DomainResourceResponse = {
    [key: string]: unknown;
};

/**
 * DomainResourceWrite
 */
export type DomainResourceWrite = {
    [key: string]: unknown;
};

/**
 * EmptyRequest
 *
 * Explicitly empty JSON object used by commands without payload fields.
 */
export type EmptyRequest = {
    [key: string]: never;
};

/**
 * ErrorResponse
 */
export type ErrorResponse = {
    /**
     * Error
     */
    error: unknown;
};

/**
 * ExamAttendanceUpdateRequest
 *
 * Attendance fact recorded for a candidate or committee assignment.
 */
export type ExamAttendanceUpdateRequest = {
    /**
     * Arrived At
     */
    arrived_at?: string | null;
    /**
     * Status
     */
    status: 'open' | 'present' | 'late' | 'absent';
    [key: string]: unknown;
};

/**
 * ExamProtocolContentRequest
 *
 * Version-guarded replacement of the protocol's factual content.
 */
export type ExamProtocolContentRequest = {
    /**
     * Change Reason
     */
    change_reason?: string | null;
    /**
     * Declaration
     */
    declaration: 'without_special_occurrences' | 'with_special_occurrences';
    /**
     * Entries
     */
    entries?: Array<ExamProtocolEntryRequest>;
    /**
     * Version
     */
    version: number;
    [key: string]: unknown;
};

/**
 * ExamProtocolEntryRequest
 *
 * One factual occurrence in a versioned exam protocol.
 */
export type ExamProtocolEntryRequest = {
    /**
     * Category
     */
    category: 'late_start' | 'interruption' | 'termination' | 'different_staffing' | 'procedural_deviation' | 'objection_or_reservation' | 'other';
    /**
     * Occurred From
     */
    occurred_from: string;
    /**
     * Occurred To
     */
    occurred_to?: string | null;
    /**
     * Statement
     */
    statement: string;
};

/**
 * ExamProtocolResponseRequest
 *
 * Participant confirmation or reservation for one protocol version.
 */
export type ExamProtocolResponseRequest = {
    /**
     * Entry Id
     */
    entry_id?: number | null;
    /**
     * Response
     */
    response: 'confirmed' | 'reservation';
    /**
     * Statement
     */
    statement?: string | null;
    /**
     * Version
     */
    version: number;
    [key: string]: unknown;
};

/**
 * ExamRoomCreateRequest
 *
 * Create one room under an existing exam venue.
 */
export type ExamRoomCreateRequest = {
    /**
     * Access Notes
     */
    access_notes?: string | null;
    /**
     * Building
     */
    building?: string | null;
    /**
     * Capacity
     */
    capacity?: number | null;
    /**
     * Floor
     */
    floor?: string | null;
    /**
     * Is Active
     */
    is_active?: boolean | number;
    /**
     * Name
     */
    name: string;
    /**
     * Reason
     */
    reason?: string | null;
    /**
     * Room Number
     */
    room_number?: string | null;
    /**
     * Wing
     */
    wing?: string | null;
};

/**
 * ExamRoomResponse
 *
 * One concrete room nested below its reusable exam venue.
 */
export type ExamRoomResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Access Notes
     */
    access_notes: string | null;
    /**
     * Building
     */
    building: string | null;
    /**
     * Capacity
     */
    capacity: number | null;
    /**
     * Created At
     */
    created_at: string;
    /**
     * Floor
     */
    floor: string | null;
    /**
     * Id
     */
    id: number;
    /**
     * Is Active
     */
    is_active: number;
    /**
     * Name
     */
    name: string;
    /**
     * Revision
     */
    revision: number;
    /**
     * Room Number
     */
    room_number: string | null;
    /**
     * Updated At
     */
    updated_at: string;
    /**
     * Venue Id
     */
    venue_id: number;
    /**
     * Wing
     */
    wing: string | null;
    [key: string]: unknown;
};

/**
 * ExamRoomUpdateRequest
 *
 * Revision-guarded partial update for one exam room.
 */
export type ExamRoomUpdateRequest = {
    /**
     * Access Notes
     */
    access_notes?: string | null;
    /**
     * Building
     */
    building?: string | null;
    /**
     * Capacity
     */
    capacity?: number | null;
    /**
     * Confirm Future Assignments
     */
    confirm_future_assignments?: boolean;
    /**
     * Expected Revision
     */
    expected_revision: number;
    /**
     * Floor
     */
    floor?: string | null;
    /**
     * Is Active
     */
    is_active?: boolean | number | null;
    /**
     * Meaningful Change
     */
    meaningful_change?: boolean;
    /**
     * Name
     */
    name?: string | null;
    /**
     * Reason
     */
    reason?: string | null;
    /**
     * Room Number
     */
    room_number?: string | null;
    /**
     * Wing
     */
    wing?: string | null;
};

/**
 * ExamSlotStartRequest
 *
 * Optional factual timestamp supplied when an exam actually starts.
 */
export type ExamSlotStartRequest = {
    /**
     * Actual Started At
     */
    actual_started_at?: string | null;
    [key: string]: unknown;
};

/**
 * ExamSlotStatusUpdateRequest
 *
 * Execution status transition, including facts accepted during correction.
 */
export type ExamSlotStatusUpdateRequest = {
    /**
     * Actual Completed At
     */
    actual_completed_at?: string | null;
    /**
     * Actual Started At
     */
    actual_started_at?: string | null;
    /**
     * Reason
     */
    reason?: string | null;
    /**
     * Status
     */
    status: 'open' | 'running' | 'completed' | 'cancelled' | 'needs_follow_up';
    [key: string]: unknown;
};

/**
 * ExamVenueCollectionResponse
 *
 * Venue collection envelope used by the public master-data API.
 */
export type ExamVenueCollectionResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Items
     */
    items: Array<ExamVenueResponse>;
};

/**
 * ExamVenueContactCreateRequest
 *
 * Create a venue-wide or room-specific non-authentication contact.
 */
export type ExamVenueContactCreateRequest = {
    /**
     * Availability Notes
     */
    availability_notes?: string | null;
    /**
     * Email
     */
    email?: string | null;
    /**
     * Is Active
     */
    is_active?: boolean | number;
    /**
     * Label
     */
    label: string;
    /**
     * Phone
     */
    phone?: string | null;
    /**
     * Reason
     */
    reason?: string | null;
    /**
     * Role
     */
    role?: string | null;
    /**
     * Room Ids
     */
    room_ids?: Array<number> | null;
};

/**
 * ExamVenueContactResponse
 *
 * Non-authentication contact information for a venue or selected rooms.
 */
export type ExamVenueContactResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Availability Notes
     */
    availability_notes: string | null;
    /**
     * Created At
     */
    created_at: string;
    /**
     * Email
     */
    email: string | null;
    /**
     * Id
     */
    id: number;
    /**
     * Is Active
     */
    is_active: number;
    /**
     * Label
     */
    label: string;
    /**
     * Phone
     */
    phone: string | null;
    /**
     * Revision
     */
    revision: number;
    /**
     * Role
     */
    role: string | null;
    /**
     * Room Ids
     */
    room_ids: Array<number>;
    /**
     * Updated At
     */
    updated_at: string;
    /**
     * Venue Id
     */
    venue_id: number;
    [key: string]: unknown;
};

/**
 * ExamVenueContactUpdateRequest
 *
 * Revision-guarded partial update for a venue contact.
 */
export type ExamVenueContactUpdateRequest = {
    /**
     * Availability Notes
     */
    availability_notes?: string | null;
    /**
     * Email
     */
    email?: string | null;
    /**
     * Expected Revision
     */
    expected_revision: number;
    /**
     * Is Active
     */
    is_active?: boolean | number | null;
    /**
     * Label
     */
    label?: string | null;
    /**
     * Phone
     */
    phone?: string | null;
    /**
     * Reason
     */
    reason?: string | null;
    /**
     * Role
     */
    role?: string | null;
    /**
     * Room Ids
     */
    room_ids?: Array<number> | null;
};

/**
 * ExamVenueCreateRequest
 *
 * Document the accepted command fields without duplicating domain validation.
 */
export type ExamVenueCreateRequest = {
    /**
     * Accessibility Notes
     */
    accessibility_notes?: string | null;
    /**
     * Accessibility Status
     */
    accessibility_status?: string;
    /**
     * City
     */
    city?: string;
    /**
     * Committee Id
     */
    committee_id: number | null;
    /**
     * Coordinate Source
     */
    coordinate_source?: string | null;
    /**
     * Coordinate Status
     */
    coordinate_status?: string;
    /**
     * Country
     */
    country?: string;
    /**
     * Duplicate Reason
     */
    duplicate_reason?: string | null;
    /**
     * Duplicates Reviewed
     */
    duplicates_reviewed?: boolean;
    /**
     * Entrance
     */
    entrance?: string | null;
    /**
     * Is Accessible
     */
    is_accessible?: boolean | number | null;
    /**
     * Is Active
     */
    is_active?: boolean | number;
    /**
     * Latitude
     */
    latitude?: number | null;
    /**
     * Longitude
     */
    longitude?: number | null;
    /**
     * Name
     */
    name: string;
    /**
     * Postal Code
     */
    postal_code?: string;
    /**
     * Reason
     */
    reason?: string | null;
    /**
     * Scope
     */
    scope: string;
    /**
     * Site Name
     */
    site_name?: string | null;
    /**
     * Street
     */
    street?: string;
    /**
     * Travel Directions
     */
    travel_directions?: string | null;
};

/**
 * ExamVenueDuplicateCheckRequest
 *
 * Candidate fields used for a non-mutating duplicate preview.
 */
export type ExamVenueDuplicateCheckRequest = {
    /**
     * City
     */
    city?: string;
    /**
     * Country
     */
    country?: string;
    /**
     * Excluded Id
     */
    excluded_id?: number | null;
    /**
     * Name
     */
    name?: string;
    /**
     * Postal Code
     */
    postal_code?: string;
    /**
     * Street
     */
    street?: string;
};

/**
 * ExamVenueGeocodeRequest
 *
 * Require an explicit, revision-safe request before contacting Nominatim.
 */
export type ExamVenueGeocodeRequest = {
    /**
     * Expected Revision
     */
    expected_revision: number;
};

/**
 * ExamVenueGeocodeResponse
 */
export type ExamVenueGeocodeResponse = {
    /**
     * Latitude
     */
    latitude: number;
    /**
     * Longitude
     */
    longitude: number;
    /**
     * Source
     */
    source: string;
};

/**
 * ExamVenuePromotionDecisionRequest
 */
export type ExamVenuePromotionDecisionRequest = {
    /**
     * Decision
     */
    decision: string;
    /**
     * Expected Revision
     */
    expected_revision: number;
    /**
     * Reason
     */
    reason: string;
};

/**
 * ExamVenuePromotionRequest
 */
export type ExamVenuePromotionRequest = {
    /**
     * Expected Revision
     */
    expected_revision: number;
    /**
     * Reason
     */
    reason: string;
};

/**
 * ExamVenueResponse
 *
 * The public aggregate representation for venue master data.
 */
export type ExamVenueResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Accessibility Notes
     */
    accessibility_notes: string | null;
    /**
     * Accessibility Status
     */
    accessibility_status: string;
    /**
     * City
     */
    city: string;
    /**
     * Committee Id
     */
    committee_id: number | null;
    /**
     * Contacts
     */
    contacts: Array<ExamVenueContactResponse>;
    /**
     * Coordinate Source
     */
    coordinate_source: string | null;
    /**
     * Coordinate Status
     */
    coordinate_status: string;
    /**
     * Country
     */
    country: string;
    /**
     * Created At
     */
    created_at: string;
    /**
     * Entrance
     */
    entrance: string | null;
    /**
     * Id
     */
    id: number;
    /**
     * Is Accessible
     */
    is_accessible: number | null;
    /**
     * Is Active
     */
    is_active: number;
    /**
     * Latitude
     */
    latitude: number | null;
    /**
     * Longitude
     */
    longitude: number | null;
    /**
     * Map Provider
     */
    map_provider: {
        [key: string]: string;
    };
    /**
     * Name
     */
    name: string;
    /**
     * Postal Code
     */
    postal_code: string;
    /**
     * Revision
     */
    revision: number;
    /**
     * Rooms
     */
    rooms: Array<ExamRoomResponse>;
    /**
     * Scope
     */
    scope: string;
    /**
     * Site Name
     */
    site_name: string | null;
    /**
     * Street
     */
    street: string;
    /**
     * Travel Directions
     */
    travel_directions: string | null;
    /**
     * Updated At
     */
    updated_at: string;
    [key: string]: unknown;
};

/**
 * ExamVenueUpdateRequest
 *
 * Revision-guarded partial update for an existing exam venue.
 */
export type ExamVenueUpdateRequest = {
    /**
     * Accessibility Notes
     */
    accessibility_notes?: string | null;
    /**
     * Accessibility Status
     */
    accessibility_status?: string | null;
    /**
     * City
     */
    city?: string | null;
    /**
     * Confirm Future Assignments
     */
    confirm_future_assignments?: boolean;
    /**
     * Coordinate Source
     */
    coordinate_source?: string | null;
    /**
     * Coordinate Status
     */
    coordinate_status?: string | null;
    /**
     * Country
     */
    country?: string | null;
    /**
     * Duplicate Reason
     */
    duplicate_reason?: string | null;
    /**
     * Duplicates Reviewed
     */
    duplicates_reviewed?: boolean;
    /**
     * Entrance
     */
    entrance?: string | null;
    /**
     * Expected Revision
     */
    expected_revision: number;
    /**
     * Is Accessible
     */
    is_accessible?: boolean | number | null;
    /**
     * Is Active
     */
    is_active?: boolean | number | null;
    /**
     * Latitude
     */
    latitude?: number | null;
    /**
     * Longitude
     */
    longitude?: number | null;
    /**
     * Meaningful Change
     */
    meaningful_change?: boolean;
    /**
     * Name
     */
    name?: string | null;
    /**
     * Postal Code
     */
    postal_code?: string | null;
    /**
     * Reason
     */
    reason?: string | null;
    /**
     * Site Name
     */
    site_name?: string | null;
    /**
     * Street
     */
    street?: string | null;
    /**
     * Travel Directions
     */
    travel_directions?: string | null;
};

/**
 * FactorActivationRequest
 */
export type FactorActivationRequest = {
    /**
     * Password
     */
    password?: string;
    /**
     * Token
     */
    token?: string;
    /**
     * Totp Code
     */
    totp_code?: string;
    /**
     * Totp Secret
     */
    totp_secret?: string;
};

/**
 * FrontendErrorRequest
 */
export type FrontendErrorRequest = {
    /**
     * Kind
     */
    kind: 'bootstrap' | 'http' | 'runtime';
    /**
     * Status
     */
    status?: number | null;
};

/**
 * HTTPValidationError
 */
export type HttpValidationError = {
    /**
     * Detail
     */
    detail?: Array<ValidationError>;
};

/**
 * HealthResponse
 */
export type HealthResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Revision
     */
    revision: string;
    /**
     * Status
     */
    status: string;
    /**
     * Version
     */
    version: string;
};

/**
 * IndividualAssessmentRequest
 *
 * One examiner's version-guarded criterion assessment.
 */
export type IndividualAssessmentRequest = {
    /**
     * Change Reason
     */
    change_reason?: string | null;
    /**
     * Component Key
     */
    component_key: string;
    /**
     * Criterion Key
     */
    criterion_key: string;
    /**
     * Rationale
     */
    rationale?: string | null;
    /**
     * Raw Points
     */
    raw_points: number | string;
    /**
     * Submitted
     */
    submitted?: boolean;
    /**
     * Version
     */
    version: number;
    [key: string]: unknown;
};

/**
 * LegacyLocationCollectionResponse
 *
 * Envelope for the deprecated, read-only location projection.
 */
export type LegacyLocationCollectionResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Items
     */
    items: Array<LegacyLocationResponse>;
};

/**
 * LegacyLocationResponse
 *
 * Temporary read projection retained while the frontend moves to rooms.
 */
export type LegacyLocationResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * City
     */
    city: string;
    /**
     * Committee Id
     */
    committee_id: number | null;
    /**
     * Created At
     */
    created_at: string;
    /**
     * Id
     */
    id: number;
    /**
     * Is Active
     */
    is_active: number;
    /**
     * Name
     */
    name: string;
    /**
     * Postal Code
     */
    postal_code: string;
    /**
     * Room
     */
    room: string;
    /**
     * Street
     */
    street: string;
    /**
     * Updated At
     */
    updated_at: string;
    /**
     * Venue Id
     */
    venue_id: number;
    [key: string]: unknown;
};

/**
 * LifecycleResponse
 *
 * Public state; diagnostics and recovery decisions belong to the admin adapter.
 */
export type LifecycleResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Ready
     */
    ready: boolean;
    /**
     * Revision
     */
    revision: string;
    state: RuntimeState;
    /**
     * Status
     */
    status: string;
    /**
     * Version
     */
    version: string;
};

/**
 * LoginRequest
 */
export type LoginRequest = {
    /**
     * Email
     */
    email?: string;
    /**
     * Password
     */
    password?: string;
    /**
     * Second Factor
     */
    second_factor?: string;
};

/**
 * NotificationChannelsResponse
 */
export type NotificationChannelsResponse = {
    /**
     * Email Fallback Configured
     */
    email_fallback_configured: boolean;
    /**
     * Sink Enabled
     */
    sink_enabled: boolean;
    /**
     * Web Push
     */
    web_push: {
        [key: string]: unknown;
    };
};

/**
 * NotificationCollectionResponse
 */
export type NotificationCollectionResponse = {
    /**
     * Links
     */
    _links: {
        [key: string]: unknown;
    };
    /**
     * Items
     */
    items: Array<{
        [key: string]: unknown;
    }>;
};

/**
 * PlanningProposalAssignmentPayload
 *
 * One examiner or fallback assignment within a planning day part.
 */
export type PlanningProposalAssignmentPayload = {
    /**
     * Assignment Role
     */
    assignment_role: string;
    /**
     * Committee Member Id
     */
    committee_member_id: number;
    /**
     * Day Part
     */
    day_part: string;
    /**
     * Fallback Status
     */
    fallback_status?: string | null;
    /**
     * Id
     */
    id?: number | null;
    [key: string]: unknown;
};

/**
 * PlanningProposalDayPayload
 *
 * One candidate exam day and its complete editable planning content.
 */
export type PlanningProposalDayPayload = {
    /**
     * Assignments
     */
    assignments: Array<PlanningProposalAssignmentPayload>;
    /**
     * Candidate Exam Day Id
     */
    candidate_exam_day_id: number;
    /**
     * Date
     */
    date?: string;
    /**
     * Id
     */
    id?: number | null;
    /**
     * Location Id
     */
    location_id?: number | null;
    /**
     * Room Id
     */
    room_id?: number | null;
    /**
     * Slots
     */
    slots: Array<PlanningProposalSlotPayload>;
    /**
     * Status
     */
    status?: string;
    [key: string]: unknown;
};

/**
 * PlanningProposalResponse
 *
 * Editable proposal or confirmed plan returned by the aggregate routes.
 */
export type PlanningProposalResponse = {
    /**
     * Links
     */
    _links?: {
        [key: string]: unknown;
    };
    /**
     * Exam Days
     */
    exam_days: Array<PlanningProposalDayPayload>;
    /**
     * Revision
     */
    revision: number;
    /**
     * Round Id
     */
    round_id: number;
    [key: string]: unknown;
};

/**
 * PlanningProposalResultResponse
 *
 * Generated planning proposal including validation and count summaries.
 */
export type PlanningProposalResultResponse = {
    /**
     * Links
     */
    _links?: {
        [key: string]: unknown;
    };
    /**
     * Counts
     */
    counts: {
        [key: string]: number;
    };
    /**
     * Exam Days
     */
    exam_days: Array<PlanningProposalDayPayload>;
    /**
     * Revision
     */
    revision: number;
    /**
     * Round Id
     */
    round_id: number;
    /**
     * Status
     */
    status: string;
    /**
     * Validation
     */
    validation: {
        [key: string]: unknown;
    };
    [key: string]: unknown;
};

/**
 * PlanningProposalSlotPayload
 *
 * One ordered candidate slot within a complete planning aggregate.
 */
export type PlanningProposalSlotPayload = {
    /**
     * Ends At
     */
    ends_at?: string;
    /**
     * Id
     */
    id?: number | null;
    /**
     * Round Candidate Id
     */
    round_candidate_id: number;
    /**
     * Sequence Number
     */
    sequence_number?: number;
    /**
     * Slot Type
     */
    slot_type: string;
    /**
     * Starts At
     */
    starts_at?: string;
    /**
     * Status
     */
    status?: string;
    [key: string]: unknown;
};

/**
 * PlanningProposalWriteRequest
 *
 * Complete optimistic-lock command for replacing one planning proposal.
 */
export type PlanningProposalWriteRequest = {
    /**
     * Exam Days
     */
    exam_days: Array<PlanningProposalDayPayload>;
    /**
     * Revision
     */
    revision: number;
    /**
     * Round Id
     */
    round_id: number;
    [key: string]: unknown;
};

/**
 * PlanningRoundRequest
 *
 * Select the exam round for a body-scoped planning operation.
 */
export type PlanningRoundRequest = {
    /**
     * Round Id
     */
    round_id?: number;
    [key: string]: unknown;
};

/**
 * PushConfirmationResponse
 */
export type PushConfirmationResponse = {
    /**
     * Status
     */
    status: 'technically_confirmed';
};

/**
 * PushSubscriptionRequest
 */
export type PushSubscriptionRequest = {
    /**
     * Endpoint
     */
    endpoint: string;
};

/**
 * PushSubscriptionResponse
 */
export type PushSubscriptionResponse = {
    /**
     * Active
     */
    active: boolean;
    /**
     * Id
     */
    id: number;
};

/**
 * RevisionDeleteRequest
 *
 * The optimistic-lock command required before deleting aggregate entities.
 */
export type RevisionDeleteRequest = {
    /**
     * Expected Revision
     */
    expected_revision: number;
    /**
     * Reason
     */
    reason?: string | null;
};

/**
 * RuntimeState
 *
 * Internal process states; public representations belong to the adapters.
 */
export type RuntimeState = 'stopped' | 'initializing' | 'ready' | 'maintenance' | 'migration_required' | 'migrating' | 'error' | 'stopping';

/**
 * RuntimeUnavailableDetail
 */
export type RuntimeUnavailableDetail = {
    /**
     * Code
     */
    code: 'runtime_not_ready';
    /**
     * Message
     */
    message: 'Application is temporarily unavailable.';
    /**
     * Ready
     */
    ready: false;
    state: RuntimeState;
};

/**
 * RuntimeUnavailableResponse
 */
export type RuntimeUnavailableResponse = {
    error: RuntimeUnavailableDetail;
};

/**
 * SessionResponse
 */
export type SessionResponse = {
    /**
     * Account Id
     */
    account_id: number;
    /**
     * Authenticated
     */
    authenticated: boolean;
    /**
     * Capabilities
     */
    capabilities?: Array<string> | null;
    /**
     * Committee Member Id
     */
    committee_member_id: number | null;
    /**
     * Demo Matrix Version
     */
    demo_matrix_version?: string | null;
    /**
     * Demo Role
     */
    demo_role?: 'chair' | 'examiner' | 'replacement' | null;
    /**
     * Demo Workspace Expires At
     */
    demo_workspace_expires_at?: string | null;
    /**
     * Display Name
     */
    display_name?: string | null;
    /**
     * Is Operator
     */
    is_operator: boolean;
    /**
     * Person Id
     */
    person_id: number | null;
};

/**
 * SessionRotationResponse
 */
export type SessionRotationResponse = {
    /**
     * Expires At
     */
    expires_at: string;
    /**
     * Status
     */
    status: string;
};

/**
 * TokenRequest
 */
export type TokenRequest = {
    /**
     * Token
     */
    token?: string;
};

/**
 * ValidationError
 */
export type ValidationError = {
    /**
     * Context
     */
    ctx?: {
        [key: string]: unknown;
    };
    /**
     * Input
     */
    input?: unknown;
    /**
     * Location
     */
    loc: Array<string | number>;
    /**
     * Message
     */
    msg: string;
    /**
     * Error Type
     */
    type: string;
};

export type ApiRootApiGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api';
};

export type ApiRootApiGetResponses = {
    /**
     * Successful Response
     */
    200: ApiRootResponse;
};

export type ApiRootApiGetResponse = ApiRootApiGetResponses[keyof ApiRootApiGetResponses];

export type AbsenceReportsApiAbsenceReportsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/absence-reports';
};

export type AbsenceReportsApiAbsenceReportsGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type CreateAbsenceApiAbsenceReportsPostData = {
    body: DomainResourceWrite;
    path?: never;
    query?: never;
    url: '/api/absence-reports';
};

export type CreateAbsenceApiAbsenceReportsPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type CreateAbsenceApiAbsenceReportsPostError = CreateAbsenceApiAbsenceReportsPostErrors[keyof CreateAbsenceApiAbsenceReportsPostErrors];

export type CreateAbsenceApiAbsenceReportsPostResponses = {
    /**
     * Successful Response
     */
    201: unknown;
};

export type AbsenceReportApiAbsenceReportsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/absence-reports/{id}';
};

export type AbsenceReportApiAbsenceReportsIdGetErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type AbsenceReportApiAbsenceReportsIdGetError = AbsenceReportApiAbsenceReportsIdGetErrors[keyof AbsenceReportApiAbsenceReportsIdGetErrors];

export type AbsenceReportApiAbsenceReportsIdGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type AbsenceCancelApiAbsenceReportsReportIdCancelPostData = {
    body?: DomainResourceWrite;
    path: {
        /**
         * Report Id
         */
        report_id: number;
    };
    query?: never;
    url: '/api/absence-reports/{report_id}/cancel';
};

export type AbsenceCancelApiAbsenceReportsReportIdCancelPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type AbsenceCancelApiAbsenceReportsReportIdCancelPostError = AbsenceCancelApiAbsenceReportsReportIdCancelPostErrors[keyof AbsenceCancelApiAbsenceReportsReportIdCancelPostErrors];

export type AbsenceCancelApiAbsenceReportsReportIdCancelPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type AbsenceReopenApiAbsenceReportsReportIdReopenPostData = {
    body?: DomainResourceWrite;
    path: {
        /**
         * Report Id
         */
        report_id: number;
    };
    query?: never;
    url: '/api/absence-reports/{report_id}/reopen';
};

export type AbsenceReopenApiAbsenceReportsReportIdReopenPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type AbsenceReopenApiAbsenceReportsReportIdReopenPostError = AbsenceReopenApiAbsenceReportsReportIdReopenPostErrors[keyof AbsenceReopenApiAbsenceReportsReportIdReopenPostErrors];

export type AbsenceReopenApiAbsenceReportsReportIdReopenPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type AbsenceSelectReplacementApiAbsenceReportsReportIdSelectReplacementPostData = {
    body?: DomainResourceWrite;
    path: {
        /**
         * Report Id
         */
        report_id: number;
    };
    query?: never;
    url: '/api/absence-reports/{report_id}/select-replacement';
};

export type AbsenceSelectReplacementApiAbsenceReportsReportIdSelectReplacementPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type AbsenceSelectReplacementApiAbsenceReportsReportIdSelectReplacementPostError = AbsenceSelectReplacementApiAbsenceReportsReportIdSelectReplacementPostErrors[keyof AbsenceSelectReplacementApiAbsenceReportsReportIdSelectReplacementPostErrors];

export type AbsenceSelectReplacementApiAbsenceReportsReportIdSelectReplacementPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type AbsenceWithdrawApiAbsenceReportsReportIdWithdrawPostData = {
    body?: DomainResourceWrite;
    path: {
        /**
         * Report Id
         */
        report_id: number;
    };
    query?: never;
    url: '/api/absence-reports/{report_id}/withdraw';
};

export type AbsenceWithdrawApiAbsenceReportsReportIdWithdrawPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type AbsenceWithdrawApiAbsenceReportsReportIdWithdrawPostError = AbsenceWithdrawApiAbsenceReportsReportIdWithdrawPostErrors[keyof AbsenceWithdrawApiAbsenceReportsReportIdWithdrawPostErrors];

export type AbsenceWithdrawApiAbsenceReportsReportIdWithdrawPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type AssessmentModelVersionsApiAssessmentModelVersionsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/assessment-model-versions';
};

export type AssessmentModelVersionsApiAssessmentModelVersionsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type AssessmentModelVersionsApiAssessmentModelVersionsGetError = AssessmentModelVersionsApiAssessmentModelVersionsGetErrors[keyof AssessmentModelVersionsApiAssessmentModelVersionsGetErrors];

export type AssessmentModelVersionsApiAssessmentModelVersionsGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type CreateAssessmentModelVersionApiAssessmentModelVersionsPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/assessment-model-versions';
};

export type CreateAssessmentModelVersionApiAssessmentModelVersionsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateAssessmentModelVersionApiAssessmentModelVersionsPostError = CreateAssessmentModelVersionApiAssessmentModelVersionsPostErrors[keyof CreateAssessmentModelVersionApiAssessmentModelVersionsPostErrors];

export type CreateAssessmentModelVersionApiAssessmentModelVersionsPostResponses = {
    /**
     * Successful Response
     */
    201: unknown;
};

export type AuthInvitationActivateApiAuthInvitationActivatePostData = {
    body: FactorActivationRequest;
    path?: never;
    query?: never;
    url: '/api/auth/invitation/activate';
};

export type AuthInvitationActivateApiAuthInvitationActivatePostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type AuthInvitationActivateApiAuthInvitationActivatePostError = AuthInvitationActivateApiAuthInvitationActivatePostErrors[keyof AuthInvitationActivateApiAuthInvitationActivatePostErrors];

export type AuthInvitationActivateApiAuthInvitationActivatePostResponses = {
    /**
     * Response Auth Invitation Activate Api Auth Invitation Activate Post
     *
     * Successful Response
     */
    200: {
        [key: string]: unknown;
    };
};

export type AuthInvitationActivateApiAuthInvitationActivatePostResponse = AuthInvitationActivateApiAuthInvitationActivatePostResponses[keyof AuthInvitationActivateApiAuthInvitationActivatePostResponses];

export type AuthInvitationPrepareApiAuthInvitationPreparePostData = {
    body: TokenRequest;
    path?: never;
    query?: never;
    url: '/api/auth/invitation/prepare';
};

export type AuthInvitationPrepareApiAuthInvitationPreparePostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type AuthInvitationPrepareApiAuthInvitationPreparePostError = AuthInvitationPrepareApiAuthInvitationPreparePostErrors[keyof AuthInvitationPrepareApiAuthInvitationPreparePostErrors];

export type AuthInvitationPrepareApiAuthInvitationPreparePostResponses = {
    /**
     * Response Auth Invitation Prepare Api Auth Invitation Prepare Post
     *
     * Successful Response
     */
    200: {
        [key: string]: unknown;
    };
};

export type AuthInvitationPrepareApiAuthInvitationPreparePostResponse = AuthInvitationPrepareApiAuthInvitationPreparePostResponses[keyof AuthInvitationPrepareApiAuthInvitationPreparePostResponses];

export type LoginApiAuthLoginPostData = {
    body: LoginRequest;
    path?: never;
    query?: never;
    url: '/api/auth/login';
};

export type LoginApiAuthLoginPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type LoginApiAuthLoginPostError = LoginApiAuthLoginPostErrors[keyof LoginApiAuthLoginPostErrors];

export type LoginApiAuthLoginPostResponses = {
    /**
     * Response Login Api Auth Login Post
     *
     * Successful Response
     */
    200: {
        [key: string]: unknown;
    };
};

export type LoginApiAuthLoginPostResponse = LoginApiAuthLoginPostResponses[keyof LoginApiAuthLoginPostResponses];

export type AuthRecoveryCompleteApiAuthRecoveryCompletePostData = {
    body: FactorActivationRequest;
    path?: never;
    query?: never;
    url: '/api/auth/recovery/complete';
};

export type AuthRecoveryCompleteApiAuthRecoveryCompletePostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type AuthRecoveryCompleteApiAuthRecoveryCompletePostError = AuthRecoveryCompleteApiAuthRecoveryCompletePostErrors[keyof AuthRecoveryCompleteApiAuthRecoveryCompletePostErrors];

export type AuthRecoveryCompleteApiAuthRecoveryCompletePostResponses = {
    /**
     * Response Auth Recovery Complete Api Auth Recovery Complete Post
     *
     * Successful Response
     */
    200: {
        [key: string]: unknown;
    };
};

export type AuthRecoveryCompleteApiAuthRecoveryCompletePostResponse = AuthRecoveryCompleteApiAuthRecoveryCompletePostResponses[keyof AuthRecoveryCompleteApiAuthRecoveryCompletePostResponses];

export type AuthRecoveryPrepareApiAuthRecoveryPreparePostData = {
    body: TokenRequest;
    path?: never;
    query?: never;
    url: '/api/auth/recovery/prepare';
};

export type AuthRecoveryPrepareApiAuthRecoveryPreparePostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type AuthRecoveryPrepareApiAuthRecoveryPreparePostError = AuthRecoveryPrepareApiAuthRecoveryPreparePostErrors[keyof AuthRecoveryPrepareApiAuthRecoveryPreparePostErrors];

export type AuthRecoveryPrepareApiAuthRecoveryPreparePostResponses = {
    /**
     * Response Auth Recovery Prepare Api Auth Recovery Prepare Post
     *
     * Successful Response
     */
    200: {
        [key: string]: unknown;
    };
};

export type AuthRecoveryPrepareApiAuthRecoveryPreparePostResponse = AuthRecoveryPrepareApiAuthRecoveryPreparePostResponses[keyof AuthRecoveryPrepareApiAuthRecoveryPreparePostResponses];

export type CalendarStatusApiCalendarGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/calendar';
};

export type CalendarStatusApiCalendarGetResponses = {
    /**
     * Successful Response
     */
    200: CalendarStatusResponse;
};

export type CalendarStatusApiCalendarGetResponse = CalendarStatusApiCalendarGetResponses[keyof CalendarStatusApiCalendarGetResponses];

export type CalendarEventsApiCalendarEventsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/calendar/events';
};

export type CalendarEventsApiCalendarEventsGetResponses = {
    /**
     * Successful Response
     */
    200: CalendarEventCollectionResponse;
};

export type CalendarEventsApiCalendarEventsGetResponse = CalendarEventsApiCalendarEventsGetResponses[keyof CalendarEventsApiCalendarEventsGetResponses];

export type RevokeFeedApiCalendarFeedDeleteData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/calendar/feed';
};

export type RevokeFeedApiCalendarFeedDeleteResponses = {
    /**
     * Successful Response
     */
    200: CalendarFeedRevocationResponse;
};

export type RevokeFeedApiCalendarFeedDeleteResponse = RevokeFeedApiCalendarFeedDeleteResponses[keyof RevokeFeedApiCalendarFeedDeleteResponses];

export type CalendarStatusApiCalendarFeedGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/calendar/feed';
};

export type CalendarStatusApiCalendarFeedGetResponses = {
    /**
     * Successful Response
     */
    200: CalendarStatusResponse;
};

export type CalendarStatusApiCalendarFeedGetResponse = CalendarStatusApiCalendarFeedGetResponses[keyof CalendarStatusApiCalendarFeedGetResponses];

export type ActivateFeedApiCalendarFeedPostData = {
    body: CalendarFeedActivationRequest;
    path?: never;
    query?: never;
    url: '/api/calendar/feed';
};

export type ActivateFeedApiCalendarFeedPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type ActivateFeedApiCalendarFeedPostError = ActivateFeedApiCalendarFeedPostErrors[keyof ActivateFeedApiCalendarFeedPostErrors];

export type ActivateFeedApiCalendarFeedPostResponses = {
    /**
     * Successful Response
     */
    201: CalendarFeedActivationResponse;
};

export type ActivateFeedApiCalendarFeedPostResponse = ActivateFeedApiCalendarFeedPostResponses[keyof ActivateFeedApiCalendarFeedPostResponses];

export type AssignmentCollectionApiCandidateCommitteeAssignmentsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/candidate-committee-assignments';
};

export type AssignmentCollectionApiCandidateCommitteeAssignmentsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type AssignmentCollectionApiCandidateCommitteeAssignmentsGetError = AssignmentCollectionApiCandidateCommitteeAssignmentsGetErrors[keyof AssignmentCollectionApiCandidateCommitteeAssignmentsGetErrors];

export type AssignmentCollectionApiCandidateCommitteeAssignmentsGetResponses = {
    /**
     * Successful Response
     */
    200: DomainCollectionResponse;
};

export type AssignmentCollectionApiCandidateCommitteeAssignmentsGetResponse = AssignmentCollectionApiCandidateCommitteeAssignmentsGetResponses[keyof AssignmentCollectionApiCandidateCommitteeAssignmentsGetResponses];

export type AssignmentItemApiCandidateCommitteeAssignmentsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/candidate-committee-assignments/{id}';
};

export type AssignmentItemApiCandidateCommitteeAssignmentsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type AssignmentItemApiCandidateCommitteeAssignmentsIdGetError = AssignmentItemApiCandidateCommitteeAssignmentsIdGetErrors[keyof AssignmentItemApiCandidateCommitteeAssignmentsIdGetErrors];

export type AssignmentItemApiCandidateCommitteeAssignmentsIdGetResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type AssignmentItemApiCandidateCommitteeAssignmentsIdGetResponse = AssignmentItemApiCandidateCommitteeAssignmentsIdGetResponses[keyof AssignmentItemApiCandidateCommitteeAssignmentsIdGetResponses];

export type GetPlanningCandidateExamDaysApiCandidateExamDaysGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/candidate-exam-days';
};

export type GetPlanningCandidateExamDaysApiCandidateExamDaysGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPlanningCandidateExamDaysApiCandidateExamDaysGetError = GetPlanningCandidateExamDaysApiCandidateExamDaysGetErrors[keyof GetPlanningCandidateExamDaysApiCandidateExamDaysGetErrors];

export type GetPlanningCandidateExamDaysApiCandidateExamDaysGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type CreateCandidateExamDaysApiCandidateExamDaysPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/candidate-exam-days';
};

export type CreateCandidateExamDaysApiCandidateExamDaysPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateCandidateExamDaysApiCandidateExamDaysPostError = CreateCandidateExamDaysApiCandidateExamDaysPostErrors[keyof CreateCandidateExamDaysApiCandidateExamDaysPostErrors];

export type CreateCandidateExamDaysApiCandidateExamDaysPostResponses = {
    /**
     * Successful Response
     */
    201: unknown;
};

export type GenerateDaysApiCandidateExamDaysGeneratePostData = {
    body: PlanningRoundRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/candidate-exam-days/generate';
};

export type GenerateDaysApiCandidateExamDaysGeneratePostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GenerateDaysApiCandidateExamDaysGeneratePostError = GenerateDaysApiCandidateExamDaysGeneratePostErrors[keyof GenerateDaysApiCandidateExamDaysGeneratePostErrors];

export type GenerateDaysApiCandidateExamDaysGeneratePostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DeleteCandidateExamDaysApiCandidateExamDaysIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/candidate-exam-days/{id}';
};

export type DeleteCandidateExamDaysApiCandidateExamDaysIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteCandidateExamDaysApiCandidateExamDaysIdDeleteError = DeleteCandidateExamDaysApiCandidateExamDaysIdDeleteErrors[keyof DeleteCandidateExamDaysApiCandidateExamDaysIdDeleteErrors];

export type DeleteCandidateExamDaysApiCandidateExamDaysIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteCandidateExamDaysApiCandidateExamDaysIdDeleteResponse = DeleteCandidateExamDaysApiCandidateExamDaysIdDeleteResponses[keyof DeleteCandidateExamDaysApiCandidateExamDaysIdDeleteResponses];

export type GetPlanningCandidateExamDaysItemApiCandidateExamDaysIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/candidate-exam-days/{id}';
};

export type GetPlanningCandidateExamDaysItemApiCandidateExamDaysIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPlanningCandidateExamDaysItemApiCandidateExamDaysIdGetError = GetPlanningCandidateExamDaysItemApiCandidateExamDaysIdGetErrors[keyof GetPlanningCandidateExamDaysItemApiCandidateExamDaysIdGetErrors];

export type GetPlanningCandidateExamDaysItemApiCandidateExamDaysIdGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type UpdateCandidateExamDaysApiCandidateExamDaysIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/candidate-exam-days/{id}';
};

export type UpdateCandidateExamDaysApiCandidateExamDaysIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateCandidateExamDaysApiCandidateExamDaysIdPatchError = UpdateCandidateExamDaysApiCandidateExamDaysIdPatchErrors[keyof UpdateCandidateExamDaysApiCandidateExamDaysIdPatchErrors];

export type UpdateCandidateExamDaysApiCandidateExamDaysIdPatchResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetCandidatesApiCandidatesGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/candidates';
};

export type GetCandidatesApiCandidatesGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetCandidatesApiCandidatesGetError = GetCandidatesApiCandidatesGetErrors[keyof GetCandidatesApiCandidatesGetErrors];

export type GetCandidatesApiCandidatesGetResponses = {
    /**
     * Successful Response
     */
    200: DomainCollectionResponse;
};

export type GetCandidatesApiCandidatesGetResponse = GetCandidatesApiCandidatesGetResponses[keyof GetCandidatesApiCandidatesGetResponses];

export type CreateCandidatesApiCandidatesPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/candidates';
};

export type CreateCandidatesApiCandidatesPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateCandidatesApiCandidatesPostError = CreateCandidatesApiCandidatesPostErrors[keyof CreateCandidatesApiCandidatesPostErrors];

export type CreateCandidatesApiCandidatesPostResponses = {
    /**
     * Successful Response
     */
    201: DomainResourceResponse;
};

export type CreateCandidatesApiCandidatesPostResponse = CreateCandidatesApiCandidatesPostResponses[keyof CreateCandidatesApiCandidatesPostResponses];

export type DeleteCandidatesApiCandidatesIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/candidates/{id}';
};

export type DeleteCandidatesApiCandidatesIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteCandidatesApiCandidatesIdDeleteError = DeleteCandidatesApiCandidatesIdDeleteErrors[keyof DeleteCandidatesApiCandidatesIdDeleteErrors];

export type DeleteCandidatesApiCandidatesIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteCandidatesApiCandidatesIdDeleteResponse = DeleteCandidatesApiCandidatesIdDeleteResponses[keyof DeleteCandidatesApiCandidatesIdDeleteResponses];

export type GetCandidatesItemApiCandidatesIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/candidates/{id}';
};

export type GetCandidatesItemApiCandidatesIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetCandidatesItemApiCandidatesIdGetError = GetCandidatesItemApiCandidatesIdGetErrors[keyof GetCandidatesItemApiCandidatesIdGetErrors];

export type GetCandidatesItemApiCandidatesIdGetResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type GetCandidatesItemApiCandidatesIdGetResponse = GetCandidatesItemApiCandidatesIdGetResponses[keyof GetCandidatesItemApiCandidatesIdGetResponses];

export type UpdateCandidatesApiCandidatesIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/candidates/{id}';
};

export type UpdateCandidatesApiCandidatesIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateCandidatesApiCandidatesIdPatchError = UpdateCandidatesApiCandidatesIdPatchErrors[keyof UpdateCandidatesApiCandidatesIdPatchErrors];

export type UpdateCandidatesApiCandidatesIdPatchResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type UpdateCandidatesApiCandidatesIdPatchResponse = UpdateCandidatesApiCandidatesIdPatchResponses[keyof UpdateCandidatesApiCandidatesIdPatchResponses];

export type GetCommitteesApiCommitteesGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/committees';
};

export type GetCommitteesApiCommitteesGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetCommitteesApiCommitteesGetError = GetCommitteesApiCommitteesGetErrors[keyof GetCommitteesApiCommitteesGetErrors];

export type GetCommitteesApiCommitteesGetResponses = {
    /**
     * Successful Response
     */
    200: DomainCollectionResponse;
};

export type GetCommitteesApiCommitteesGetResponse = GetCommitteesApiCommitteesGetResponses[keyof GetCommitteesApiCommitteesGetResponses];

export type DeleteCommitteesApiCommitteesIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/committees/{id}';
};

export type DeleteCommitteesApiCommitteesIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteCommitteesApiCommitteesIdDeleteError = DeleteCommitteesApiCommitteesIdDeleteErrors[keyof DeleteCommitteesApiCommitteesIdDeleteErrors];

export type DeleteCommitteesApiCommitteesIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteCommitteesApiCommitteesIdDeleteResponse = DeleteCommitteesApiCommitteesIdDeleteResponses[keyof DeleteCommitteesApiCommitteesIdDeleteResponses];

export type GetCommitteesItemApiCommitteesIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/committees/{id}';
};

export type GetCommitteesItemApiCommitteesIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetCommitteesItemApiCommitteesIdGetError = GetCommitteesItemApiCommitteesIdGetErrors[keyof GetCommitteesItemApiCommitteesIdGetErrors];

export type GetCommitteesItemApiCommitteesIdGetResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type GetCommitteesItemApiCommitteesIdGetResponse = GetCommitteesItemApiCommitteesIdGetResponses[keyof GetCommitteesItemApiCommitteesIdGetResponses];

export type UpdateCommitteesApiCommitteesIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/committees/{id}';
};

export type UpdateCommitteesApiCommitteesIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateCommitteesApiCommitteesIdPatchError = UpdateCommitteesApiCommitteesIdPatchErrors[keyof UpdateCommitteesApiCommitteesIdPatchErrors];

export type UpdateCommitteesApiCommitteesIdPatchResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type UpdateCommitteesApiCommitteesIdPatchResponse = UpdateCommitteesApiCommitteesIdPatchResponses[keyof UpdateCommitteesApiCommitteesIdPatchResponses];

export type AssignmentAttendanceApiConfirmedPlanDaysDayIdAssignmentsAssignmentIdAttendancePatchData = {
    body: ExamAttendanceUpdateRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Day Id
         */
        day_id: number;
        /**
         * Assignment Id
         */
        assignment_id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance';
};

export type AssignmentAttendanceApiConfirmedPlanDaysDayIdAssignmentsAssignmentIdAttendancePatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type AssignmentAttendanceApiConfirmedPlanDaysDayIdAssignmentsAssignmentIdAttendancePatchError = AssignmentAttendanceApiConfirmedPlanDaysDayIdAssignmentsAssignmentIdAttendancePatchErrors[keyof AssignmentAttendanceApiConfirmedPlanDaysDayIdAssignmentsAssignmentIdAttendancePatchErrors];

export type AssignmentAttendanceApiConfirmedPlanDaysDayIdAssignmentsAssignmentIdAttendancePatchResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ProtocolCompletionApiConfirmedPlanDaysDayIdProtocolCompletionGetData = {
    body?: never;
    path: {
        /**
         * Day Id
         */
        day_id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{day_id}/protocol-completion';
};

export type ProtocolCompletionApiConfirmedPlanDaysDayIdProtocolCompletionGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ProtocolCompletionApiConfirmedPlanDaysDayIdProtocolCompletionGetError = ProtocolCompletionApiConfirmedPlanDaysDayIdProtocolCompletionGetErrors[keyof ProtocolCompletionApiConfirmedPlanDaysDayIdProtocolCompletionGetErrors];

export type ProtocolCompletionApiConfirmedPlanDaysDayIdProtocolCompletionGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ResultCompletionApiConfirmedPlanDaysDayIdResultCompletionGetData = {
    body?: never;
    path: {
        /**
         * Day Id
         */
        day_id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{day_id}/result-completion';
};

export type ResultCompletionApiConfirmedPlanDaysDayIdResultCompletionGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ResultCompletionApiConfirmedPlanDaysDayIdResultCompletionGetError = ResultCompletionApiConfirmedPlanDaysDayIdResultCompletionGetErrors[keyof ResultCompletionApiConfirmedPlanDaysDayIdResultCompletionGetErrors];

export type ResultCompletionApiConfirmedPlanDaysDayIdResultCompletionGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type SlotAttendanceApiConfirmedPlanDaysDayIdSlotsSlotIdAttendancePatchData = {
    body: ExamAttendanceUpdateRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Day Id
         */
        day_id: number;
        /**
         * Slot Id
         */
        slot_id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance';
};

export type SlotAttendanceApiConfirmedPlanDaysDayIdSlotsSlotIdAttendancePatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SlotAttendanceApiConfirmedPlanDaysDayIdSlotsSlotIdAttendancePatchError = SlotAttendanceApiConfirmedPlanDaysDayIdSlotsSlotIdAttendancePatchErrors[keyof SlotAttendanceApiConfirmedPlanDaysDayIdSlotsSlotIdAttendancePatchErrors];

export type SlotAttendanceApiConfirmedPlanDaysDayIdSlotsSlotIdAttendancePatchResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type SlotProtocolApiConfirmedPlanDaysDayIdSlotsSlotIdProtocolGetData = {
    body?: never;
    path: {
        /**
         * Day Id
         */
        day_id: number;
        /**
         * Slot Id
         */
        slot_id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{day_id}/slots/{slot_id}/protocol';
};

export type SlotProtocolApiConfirmedPlanDaysDayIdSlotsSlotIdProtocolGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SlotProtocolApiConfirmedPlanDaysDayIdSlotsSlotIdProtocolGetError = SlotProtocolApiConfirmedPlanDaysDayIdSlotsSlotIdProtocolGetErrors[keyof SlotProtocolApiConfirmedPlanDaysDayIdSlotsSlotIdProtocolGetErrors];

export type SlotProtocolApiConfirmedPlanDaysDayIdSlotsSlotIdProtocolGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type SlotResultApiConfirmedPlanDaysDayIdSlotsSlotIdResultGetData = {
    body?: never;
    path: {
        /**
         * Day Id
         */
        day_id: number;
        /**
         * Slot Id
         */
        slot_id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{day_id}/slots/{slot_id}/result';
};

export type SlotResultApiConfirmedPlanDaysDayIdSlotsSlotIdResultGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SlotResultApiConfirmedPlanDaysDayIdSlotsSlotIdResultGetError = SlotResultApiConfirmedPlanDaysDayIdSlotsSlotIdResultGetErrors[keyof SlotResultApiConfirmedPlanDaysDayIdSlotsSlotIdResultGetErrors];

export type SlotResultApiConfirmedPlanDaysDayIdSlotsSlotIdResultGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type StartSlotApiConfirmedPlanDaysDayIdSlotsSlotIdStartPostData = {
    body: ExamSlotStartRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Day Id
         */
        day_id: number;
        /**
         * Slot Id
         */
        slot_id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{day_id}/slots/{slot_id}/start';
};

export type StartSlotApiConfirmedPlanDaysDayIdSlotsSlotIdStartPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type StartSlotApiConfirmedPlanDaysDayIdSlotsSlotIdStartPostError = StartSlotApiConfirmedPlanDaysDayIdSlotsSlotIdStartPostErrors[keyof StartSlotApiConfirmedPlanDaysDayIdSlotsSlotIdStartPostErrors];

export type StartSlotApiConfirmedPlanDaysDayIdSlotsSlotIdStartPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type SlotStatusApiConfirmedPlanDaysDayIdSlotsSlotIdStatusPatchData = {
    body: ExamSlotStatusUpdateRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Day Id
         */
        day_id: number;
        /**
         * Slot Id
         */
        slot_id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{day_id}/slots/{slot_id}/status';
};

export type SlotStatusApiConfirmedPlanDaysDayIdSlotsSlotIdStatusPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SlotStatusApiConfirmedPlanDaysDayIdSlotsSlotIdStatusPatchError = SlotStatusApiConfirmedPlanDaysDayIdSlotsSlotIdStatusPatchErrors[keyof SlotStatusApiConfirmedPlanDaysDayIdSlotsSlotIdStatusPatchErrors];

export type SlotStatusApiConfirmedPlanDaysDayIdSlotsSlotIdStatusPatchResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ConfirmedDayApiConfirmedPlanDaysIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{id}';
};

export type ConfirmedDayApiConfirmedPlanDaysIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ConfirmedDayApiConfirmedPlanDaysIdGetError = ConfirmedDayApiConfirmedPlanDaysIdGetErrors[keyof ConfirmedDayApiConfirmedPlanDaysIdGetErrors];

export type ConfirmedDayApiConfirmedPlanDaysIdGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExamDayClosureApiConfirmedPlanDaysIdClosureGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{id}/closure';
};

export type ExamDayClosureApiConfirmedPlanDaysIdClosureGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamDayClosureApiConfirmedPlanDaysIdClosureGetError = ExamDayClosureApiConfirmedPlanDaysIdClosureGetErrors[keyof ExamDayClosureApiConfirmedPlanDaysIdClosureGetErrors];

export type ExamDayClosureApiConfirmedPlanDaysIdClosureGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type CloseExamDayApiConfirmedPlanDaysIdClosurePostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{id}/closure';
};

export type CloseExamDayApiConfirmedPlanDaysIdClosurePostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CloseExamDayApiConfirmedPlanDaysIdClosurePostError = CloseExamDayApiConfirmedPlanDaysIdClosurePostErrors[keyof CloseExamDayApiConfirmedPlanDaysIdClosurePostErrors];

export type CloseExamDayApiConfirmedPlanDaysIdClosurePostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExportExamDayJsonApiConfirmedPlanDaysIdClosureExportJsonGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{id}/closure/export.json';
};

export type ExportExamDayJsonApiConfirmedPlanDaysIdClosureExportJsonGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExportExamDayJsonApiConfirmedPlanDaysIdClosureExportJsonGetError = ExportExamDayJsonApiConfirmedPlanDaysIdClosureExportJsonGetErrors[keyof ExportExamDayJsonApiConfirmedPlanDaysIdClosureExportJsonGetErrors];

export type ExportExamDayJsonApiConfirmedPlanDaysIdClosureExportJsonGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExportExamDayTextApiConfirmedPlanDaysIdClosureExportTxtGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{id}/closure/export.txt';
};

export type ExportExamDayTextApiConfirmedPlanDaysIdClosureExportTxtGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExportExamDayTextApiConfirmedPlanDaysIdClosureExportTxtGetError = ExportExamDayTextApiConfirmedPlanDaysIdClosureExportTxtGetErrors[keyof ExportExamDayTextApiConfirmedPlanDaysIdClosureExportTxtGetErrors];

export type ExportExamDayTextApiConfirmedPlanDaysIdClosureExportTxtGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExamDayReopeningImpactApiConfirmedPlanDaysIdReopeningImpactPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{id}/reopening-impact';
};

export type ExamDayReopeningImpactApiConfirmedPlanDaysIdReopeningImpactPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamDayReopeningImpactApiConfirmedPlanDaysIdReopeningImpactPostError = ExamDayReopeningImpactApiConfirmedPlanDaysIdReopeningImpactPostErrors[keyof ExamDayReopeningImpactApiConfirmedPlanDaysIdReopeningImpactPostErrors];

export type ExamDayReopeningImpactApiConfirmedPlanDaysIdReopeningImpactPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ReopenExamDayApiConfirmedPlanDaysIdReopeningsPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/confirmed-plan-days/{id}/reopenings';
};

export type ReopenExamDayApiConfirmedPlanDaysIdReopeningsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ReopenExamDayApiConfirmedPlanDaysIdReopeningsPostError = ReopenExamDayApiConfirmedPlanDaysIdReopeningsPostErrors[keyof ReopenExamDayApiConfirmedPlanDaysIdReopeningsPostErrors];

export type ReopenExamDayApiConfirmedPlanDaysIdReopeningsPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ConfirmedPlansApiConfirmedPlansGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/confirmed-plans';
};

export type ConfirmedPlansApiConfirmedPlansGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ConfirmedPlansApiConfirmedPlansGetError = ConfirmedPlansApiConfirmedPlansGetErrors[keyof ConfirmedPlansApiConfirmedPlansGetErrors];

export type ConfirmedPlansApiConfirmedPlansGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DemoResetApiDemoResetPostData = {
    body: EmptyRequest;
    path?: never;
    query?: never;
    url: '/api/demo/reset';
};

export type DemoResetApiDemoResetPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type DemoResetApiDemoResetPostError = DemoResetApiDemoResetPostErrors[keyof DemoResetApiDemoResetPostErrors];

export type DemoResetApiDemoResetPostResponses = {
    /**
     * Successful Response
     */
    200: DemoScenarioResetResponse;
};

export type DemoResetApiDemoResetPostResponse = DemoResetApiDemoResetPostResponses[keyof DemoResetApiDemoResetPostResponses];

export type DemoScenariosApiDemoScenariosGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/demo/scenarios';
};

export type DemoScenariosApiDemoScenariosGetResponses = {
    /**
     * Successful Response
     */
    200: DemoScenarioOverviewResponse;
};

export type DemoScenariosApiDemoScenariosGetResponse = DemoScenariosApiDemoScenariosGetResponses[keyof DemoScenariosApiDemoScenariosGetResponses];

export type GetPlanningExamDayAssignmentsApiExamDayAssignmentsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/exam-day-assignments';
};

export type GetPlanningExamDayAssignmentsApiExamDayAssignmentsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPlanningExamDayAssignmentsApiExamDayAssignmentsGetError = GetPlanningExamDayAssignmentsApiExamDayAssignmentsGetErrors[keyof GetPlanningExamDayAssignmentsApiExamDayAssignmentsGetErrors];

export type GetPlanningExamDayAssignmentsApiExamDayAssignmentsGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetPlanningExamDayAssignmentsItemApiExamDayAssignmentsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-day-assignments/{id}';
};

export type GetPlanningExamDayAssignmentsItemApiExamDayAssignmentsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPlanningExamDayAssignmentsItemApiExamDayAssignmentsIdGetError = GetPlanningExamDayAssignmentsItemApiExamDayAssignmentsIdGetErrors[keyof GetPlanningExamDayAssignmentsItemApiExamDayAssignmentsIdGetErrors];

export type GetPlanningExamDayAssignmentsItemApiExamDayAssignmentsIdGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetPlanningExamDaysApiExamDaysGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/exam-days';
};

export type GetPlanningExamDaysApiExamDaysGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPlanningExamDaysApiExamDaysGetError = GetPlanningExamDaysApiExamDaysGetErrors[keyof GetPlanningExamDaysApiExamDaysGetErrors];

export type GetPlanningExamDaysApiExamDaysGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetPlanningExamDaysItemApiExamDaysIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-days/{id}';
};

export type GetPlanningExamDaysItemApiExamDaysIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPlanningExamDaysItemApiExamDaysIdGetError = GetPlanningExamDaysItemApiExamDaysIdGetErrors[keyof GetPlanningExamDaysItemApiExamDaysIdGetErrors];

export type GetPlanningExamDaysItemApiExamDaysIdGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetExamHalfYearsApiExamHalfYearsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/exam-half-years';
};

export type GetExamHalfYearsApiExamHalfYearsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetExamHalfYearsApiExamHalfYearsGetError = GetExamHalfYearsApiExamHalfYearsGetErrors[keyof GetExamHalfYearsApiExamHalfYearsGetErrors];

export type GetExamHalfYearsApiExamHalfYearsGetResponses = {
    /**
     * Successful Response
     */
    200: DomainCollectionResponse;
};

export type GetExamHalfYearsApiExamHalfYearsGetResponse = GetExamHalfYearsApiExamHalfYearsGetResponses[keyof GetExamHalfYearsApiExamHalfYearsGetResponses];

export type CreateExamHalfYearsApiExamHalfYearsPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/exam-half-years';
};

export type CreateExamHalfYearsApiExamHalfYearsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateExamHalfYearsApiExamHalfYearsPostError = CreateExamHalfYearsApiExamHalfYearsPostErrors[keyof CreateExamHalfYearsApiExamHalfYearsPostErrors];

export type CreateExamHalfYearsApiExamHalfYearsPostResponses = {
    /**
     * Successful Response
     */
    201: DomainResourceResponse;
};

export type CreateExamHalfYearsApiExamHalfYearsPostResponse = CreateExamHalfYearsApiExamHalfYearsPostResponses[keyof CreateExamHalfYearsApiExamHalfYearsPostResponses];

export type DeleteExamHalfYearsApiExamHalfYearsIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-half-years/{id}';
};

export type DeleteExamHalfYearsApiExamHalfYearsIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteExamHalfYearsApiExamHalfYearsIdDeleteError = DeleteExamHalfYearsApiExamHalfYearsIdDeleteErrors[keyof DeleteExamHalfYearsApiExamHalfYearsIdDeleteErrors];

export type DeleteExamHalfYearsApiExamHalfYearsIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteExamHalfYearsApiExamHalfYearsIdDeleteResponse = DeleteExamHalfYearsApiExamHalfYearsIdDeleteResponses[keyof DeleteExamHalfYearsApiExamHalfYearsIdDeleteResponses];

export type GetExamHalfYearsItemApiExamHalfYearsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-half-years/{id}';
};

export type GetExamHalfYearsItemApiExamHalfYearsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetExamHalfYearsItemApiExamHalfYearsIdGetError = GetExamHalfYearsItemApiExamHalfYearsIdGetErrors[keyof GetExamHalfYearsItemApiExamHalfYearsIdGetErrors];

export type GetExamHalfYearsItemApiExamHalfYearsIdGetResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type GetExamHalfYearsItemApiExamHalfYearsIdGetResponse = GetExamHalfYearsItemApiExamHalfYearsIdGetResponses[keyof GetExamHalfYearsItemApiExamHalfYearsIdGetResponses];

export type UpdateExamHalfYearsApiExamHalfYearsIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-half-years/{id}';
};

export type UpdateExamHalfYearsApiExamHalfYearsIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateExamHalfYearsApiExamHalfYearsIdPatchError = UpdateExamHalfYearsApiExamHalfYearsIdPatchErrors[keyof UpdateExamHalfYearsApiExamHalfYearsIdPatchErrors];

export type UpdateExamHalfYearsApiExamHalfYearsIdPatchResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type UpdateExamHalfYearsApiExamHalfYearsIdPatchResponse = UpdateExamHalfYearsApiExamHalfYearsIdPatchResponses[keyof UpdateExamHalfYearsApiExamHalfYearsIdPatchResponses];

export type ExamProtocolApiExamProtocolsProtocolIdGetData = {
    body?: never;
    path: {
        /**
         * Protocol Id
         */
        protocol_id: number;
    };
    query?: never;
    url: '/api/exam-protocols/{protocol_id}';
};

export type ExamProtocolApiExamProtocolsProtocolIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamProtocolApiExamProtocolsProtocolIdGetError = ExamProtocolApiExamProtocolsProtocolIdGetErrors[keyof ExamProtocolApiExamProtocolsProtocolIdGetErrors];

export type ExamProtocolApiExamProtocolsProtocolIdGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type UpdateExamProtocolApiExamProtocolsProtocolIdPatchData = {
    body: ExamProtocolContentRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Protocol Id
         */
        protocol_id: number;
    };
    query?: never;
    url: '/api/exam-protocols/{protocol_id}';
};

export type UpdateExamProtocolApiExamProtocolsProtocolIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateExamProtocolApiExamProtocolsProtocolIdPatchError = UpdateExamProtocolApiExamProtocolsProtocolIdPatchErrors[keyof UpdateExamProtocolApiExamProtocolsProtocolIdPatchErrors];

export type UpdateExamProtocolApiExamProtocolsProtocolIdPatchResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type RequestExamProtocolCorrectionApiExamProtocolsProtocolIdCorrectionRequestsPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Protocol Id
         */
        protocol_id: number;
    };
    query?: never;
    url: '/api/exam-protocols/{protocol_id}/correction-requests';
};

export type RequestExamProtocolCorrectionApiExamProtocolsProtocolIdCorrectionRequestsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type RequestExamProtocolCorrectionApiExamProtocolsProtocolIdCorrectionRequestsPostError = RequestExamProtocolCorrectionApiExamProtocolsProtocolIdCorrectionRequestsPostErrors[keyof RequestExamProtocolCorrectionApiExamProtocolsProtocolIdCorrectionRequestsPostErrors];

export type RequestExamProtocolCorrectionApiExamProtocolsProtocolIdCorrectionRequestsPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExportExamProtocolJsonApiExamProtocolsProtocolIdExportJsonGetData = {
    body?: never;
    path: {
        /**
         * Protocol Id
         */
        protocol_id: number;
    };
    query?: never;
    url: '/api/exam-protocols/{protocol_id}/export.json';
};

export type ExportExamProtocolJsonApiExamProtocolsProtocolIdExportJsonGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExportExamProtocolJsonApiExamProtocolsProtocolIdExportJsonGetError = ExportExamProtocolJsonApiExamProtocolsProtocolIdExportJsonGetErrors[keyof ExportExamProtocolJsonApiExamProtocolsProtocolIdExportJsonGetErrors];

export type ExportExamProtocolJsonApiExamProtocolsProtocolIdExportJsonGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExportExamProtocolTextApiExamProtocolsProtocolIdExportTxtGetData = {
    body?: never;
    path: {
        /**
         * Protocol Id
         */
        protocol_id: number;
    };
    query?: never;
    url: '/api/exam-protocols/{protocol_id}/export.txt';
};

export type ExportExamProtocolTextApiExamProtocolsProtocolIdExportTxtGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExportExamProtocolTextApiExamProtocolsProtocolIdExportTxtGetError = ExportExamProtocolTextApiExamProtocolsProtocolIdExportTxtGetErrors[keyof ExportExamProtocolTextApiExamProtocolsProtocolIdExportTxtGetErrors];

export type ExportExamProtocolTextApiExamProtocolsProtocolIdExportTxtGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type OpenExamProtocolCorrectionApiExamProtocolsProtocolIdOpenCorrectionPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Protocol Id
         */
        protocol_id: number;
    };
    query?: never;
    url: '/api/exam-protocols/{protocol_id}/open-correction';
};

export type OpenExamProtocolCorrectionApiExamProtocolsProtocolIdOpenCorrectionPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type OpenExamProtocolCorrectionApiExamProtocolsProtocolIdOpenCorrectionPostError = OpenExamProtocolCorrectionApiExamProtocolsProtocolIdOpenCorrectionPostErrors[keyof OpenExamProtocolCorrectionApiExamProtocolsProtocolIdOpenCorrectionPostErrors];

export type OpenExamProtocolCorrectionApiExamProtocolsProtocolIdOpenCorrectionPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type RespondToExamProtocolApiExamProtocolsProtocolIdResponsesPostData = {
    body: ExamProtocolResponseRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Protocol Id
         */
        protocol_id: number;
    };
    query?: never;
    url: '/api/exam-protocols/{protocol_id}/responses';
};

export type RespondToExamProtocolApiExamProtocolsProtocolIdResponsesPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type RespondToExamProtocolApiExamProtocolsProtocolIdResponsesPostError = RespondToExamProtocolApiExamProtocolsProtocolIdResponsesPostErrors[keyof RespondToExamProtocolApiExamProtocolsProtocolIdResponsesPostErrors];

export type RespondToExamProtocolApiExamProtocolsProtocolIdResponsesPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type SetExamProtocolRetentionApiExamProtocolsProtocolIdRetentionPutData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Protocol Id
         */
        protocol_id: number;
    };
    query?: never;
    url: '/api/exam-protocols/{protocol_id}/retention';
};

export type SetExamProtocolRetentionApiExamProtocolsProtocolIdRetentionPutErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SetExamProtocolRetentionApiExamProtocolsProtocolIdRetentionPutError = SetExamProtocolRetentionApiExamProtocolsProtocolIdRetentionPutErrors[keyof SetExamProtocolRetentionApiExamProtocolsProtocolIdRetentionPutErrors];

export type SetExamProtocolRetentionApiExamProtocolsProtocolIdRetentionPutResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type SubmitExamProtocolApiExamProtocolsProtocolIdSubmitPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Protocol Id
         */
        protocol_id: number;
    };
    query?: never;
    url: '/api/exam-protocols/{protocol_id}/submit';
};

export type SubmitExamProtocolApiExamProtocolsProtocolIdSubmitPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SubmitExamProtocolApiExamProtocolsProtocolIdSubmitPostError = SubmitExamProtocolApiExamProtocolsProtocolIdSubmitPostErrors[keyof SubmitExamProtocolApiExamProtocolsProtocolIdSubmitPostErrors];

export type SubmitExamProtocolApiExamProtocolsProtocolIdSubmitPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExamResultApiExamResultsResultIdGetData = {
    body?: never;
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}';
};

export type ExamResultApiExamResultsResultIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamResultApiExamResultsResultIdGetError = ExamResultApiExamResultsResultIdGetErrors[keyof ExamResultApiExamResultsResultIdGetErrors];

export type ExamResultApiExamResultsResultIdGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DetermineCommitteeAssessmentApiExamResultsResultIdCommitteeAssessmentsPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/committee-assessments';
};

export type DetermineCommitteeAssessmentApiExamResultsResultIdCommitteeAssessmentsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DetermineCommitteeAssessmentApiExamResultsResultIdCommitteeAssessmentsPostError = DetermineCommitteeAssessmentApiExamResultsResultIdCommitteeAssessmentsPostErrors[keyof DetermineCommitteeAssessmentApiExamResultsResultIdCommitteeAssessmentsPostErrors];

export type DetermineCommitteeAssessmentApiExamResultsResultIdCommitteeAssessmentsPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type CommunicateExamResultApiExamResultsResultIdCommunicationsPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/communications';
};

export type CommunicateExamResultApiExamResultsResultIdCommunicationsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CommunicateExamResultApiExamResultsResultIdCommunicationsPostError = CommunicateExamResultApiExamResultsResultIdCommunicationsPostErrors[keyof CommunicateExamResultApiExamResultsResultIdCommunicationsPostErrors];

export type CommunicateExamResultApiExamResultsResultIdCommunicationsPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type OpenResultCorrectionApiExamResultsResultIdCorrectionsPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/corrections';
};

export type OpenResultCorrectionApiExamResultsResultIdCorrectionsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type OpenResultCorrectionApiExamResultsResultIdCorrectionsPostError = OpenResultCorrectionApiExamResultsResultIdCorrectionsPostErrors[keyof OpenResultCorrectionApiExamResultsResultIdCorrectionsPostErrors];

export type OpenResultCorrectionApiExamResultsResultIdCorrectionsPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DetermineExamResultApiExamResultsResultIdDeterminePostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/determine';
};

export type DetermineExamResultApiExamResultsResultIdDeterminePostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DetermineExamResultApiExamResultsResultIdDeterminePostError = DetermineExamResultApiExamResultsResultIdDeterminePostErrors[keyof DetermineExamResultApiExamResultsResultIdDeterminePostErrors];

export type DetermineExamResultApiExamResultsResultIdDeterminePostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DiscloseIndividualAssessmentsApiExamResultsResultIdDisclosuresPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/disclosures';
};

export type DiscloseIndividualAssessmentsApiExamResultsResultIdDisclosuresPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DiscloseIndividualAssessmentsApiExamResultsResultIdDisclosuresPostError = DiscloseIndividualAssessmentsApiExamResultsResultIdDisclosuresPostErrors[keyof DiscloseIndividualAssessmentsApiExamResultsResultIdDisclosuresPostErrors];

export type DiscloseIndividualAssessmentsApiExamResultsResultIdDisclosuresPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExportExamResultJsonApiExamResultsResultIdExportJsonGetData = {
    body?: never;
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/export.json';
};

export type ExportExamResultJsonApiExamResultsResultIdExportJsonGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExportExamResultJsonApiExamResultsResultIdExportJsonGetError = ExportExamResultJsonApiExamResultsResultIdExportJsonGetErrors[keyof ExportExamResultJsonApiExamResultsResultIdExportJsonGetErrors];

export type ExportExamResultJsonApiExamResultsResultIdExportJsonGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExportExamResultTextApiExamResultsResultIdExportTxtGetData = {
    body?: never;
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/export.txt';
};

export type ExportExamResultTextApiExamResultsResultIdExportTxtGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExportExamResultTextApiExamResultsResultIdExportTxtGetError = ExportExamResultTextApiExamResultsResultIdExportTxtGetErrors[keyof ExportExamResultTextApiExamResultsResultIdExportTxtGetErrors];

export type ExportExamResultTextApiExamResultsResultIdExportTxtGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type RecordExternalResultApiExamResultsResultIdExternalResultsPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/external-results';
};

export type RecordExternalResultApiExamResultsResultIdExternalResultsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type RecordExternalResultApiExamResultsResultIdExternalResultsPostError = RecordExternalResultApiExamResultsResultIdExternalResultsPostErrors[keyof RecordExternalResultApiExamResultsResultIdExternalResultsPostErrors];

export type RecordExternalResultApiExamResultsResultIdExternalResultsPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ConfirmExternalResultApiExamResultsResultIdExternalResultsExternalResultIdConfirmPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
        /**
         * External Result Id
         */
        external_result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/external-results/{external_result_id}/confirm';
};

export type ConfirmExternalResultApiExamResultsResultIdExternalResultsExternalResultIdConfirmPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ConfirmExternalResultApiExamResultsResultIdExternalResultsExternalResultIdConfirmPostError = ConfirmExternalResultApiExamResultsResultIdExternalResultsExternalResultIdConfirmPostErrors[keyof ConfirmExternalResultApiExamResultsResultIdExternalResultsExternalResultIdConfirmPostErrors];

export type ConfirmExternalResultApiExamResultsResultIdExternalResultsExternalResultIdConfirmPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type SaveIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsPostData = {
    body: IndividualAssessmentRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/individual-assessments';
};

export type SaveIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SaveIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsPostError = SaveIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsPostErrors[keyof SaveIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsPostErrors];

export type SaveIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type WithdrawIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsAssessmentIdWithdrawPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
        /**
         * Assessment Id
         */
        assessment_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/individual-assessments/{assessment_id}/withdraw';
};

export type WithdrawIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsAssessmentIdWithdrawPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type WithdrawIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsAssessmentIdWithdrawPostError = WithdrawIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsAssessmentIdWithdrawPostErrors[keyof WithdrawIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsAssessmentIdWithdrawPostErrors];

export type WithdrawIndividualAssessmentApiExamResultsResultIdIndividualAssessmentsAssessmentIdWithdrawPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ConfirmResultRecordApiExamResultsResultIdRecordConfirmationsPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/record-confirmations';
};

export type ConfirmResultRecordApiExamResultsResultIdRecordConfirmationsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ConfirmResultRecordApiExamResultsResultIdRecordConfirmationsPostError = ConfirmResultRecordApiExamResultsResultIdRecordConfirmationsPostErrors[keyof ConfirmResultRecordApiExamResultsResultIdRecordConfirmationsPostErrors];

export type ConfirmResultRecordApiExamResultsResultIdRecordConfirmationsPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type SetResultRetentionApiExamResultsResultIdRetentionPutData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-results/{result_id}/retention';
};

export type SetResultRetentionApiExamResultsResultIdRetentionPutErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SetResultRetentionApiExamResultsResultIdRetentionPutError = SetResultRetentionApiExamResultsResultIdRetentionPutErrors[keyof SetResultRetentionApiExamResultsResultIdRetentionPutErrors];

export type SetResultRetentionApiExamResultsResultIdRetentionPutResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DeleteExamRoomApiExamRoomsIdDeleteData = {
    body: RevisionDeleteRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rooms/{id}';
};

export type DeleteExamRoomApiExamRoomsIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteExamRoomApiExamRoomsIdDeleteError = DeleteExamRoomApiExamRoomsIdDeleteErrors[keyof DeleteExamRoomApiExamRoomsIdDeleteErrors];

export type DeleteExamRoomApiExamRoomsIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteExamRoomApiExamRoomsIdDeleteResponse = DeleteExamRoomApiExamRoomsIdDeleteResponses[keyof DeleteExamRoomApiExamRoomsIdDeleteResponses];

export type ExamRoomItemApiExamRoomsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rooms/{id}';
};

export type ExamRoomItemApiExamRoomsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamRoomItemApiExamRoomsIdGetError = ExamRoomItemApiExamRoomsIdGetErrors[keyof ExamRoomItemApiExamRoomsIdGetErrors];

export type ExamRoomItemApiExamRoomsIdGetResponses = {
    /**
     * Successful Response
     */
    200: ExamRoomResponse;
};

export type ExamRoomItemApiExamRoomsIdGetResponse = ExamRoomItemApiExamRoomsIdGetResponses[keyof ExamRoomItemApiExamRoomsIdGetResponses];

export type UpdateExamRoomApiExamRoomsIdPatchData = {
    body: ExamRoomUpdateRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rooms/{id}';
};

export type UpdateExamRoomApiExamRoomsIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateExamRoomApiExamRoomsIdPatchError = UpdateExamRoomApiExamRoomsIdPatchErrors[keyof UpdateExamRoomApiExamRoomsIdPatchErrors];

export type UpdateExamRoomApiExamRoomsIdPatchResponses = {
    /**
     * Successful Response
     */
    200: ExamRoomResponse;
};

export type UpdateExamRoomApiExamRoomsIdPatchResponse = UpdateExamRoomApiExamRoomsIdPatchResponses[keyof UpdateExamRoomApiExamRoomsIdPatchResponses];

export type ExamRoomChangeImpactApiExamRoomsIdChangeImpactGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rooms/{id}/change-impact';
};

export type ExamRoomChangeImpactApiExamRoomsIdChangeImpactGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamRoomChangeImpactApiExamRoomsIdChangeImpactGetError = ExamRoomChangeImpactApiExamRoomsIdChangeImpactGetErrors[keyof ExamRoomChangeImpactApiExamRoomsIdChangeImpactGetErrors];

export type ExamRoomChangeImpactApiExamRoomsIdChangeImpactGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type PreviewExamRoomChangeApiExamRoomsIdChangeImpactPostData = {
    body: ExamRoomUpdateRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rooms/{id}/change-impact';
};

export type PreviewExamRoomChangeApiExamRoomsIdChangeImpactPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type PreviewExamRoomChangeApiExamRoomsIdChangeImpactPostError = PreviewExamRoomChangeApiExamRoomsIdChangeImpactPostErrors[keyof PreviewExamRoomChangeApiExamRoomsIdChangeImpactPostErrors];

export type PreviewExamRoomChangeApiExamRoomsIdChangeImpactPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetExamRoundsApiExamRoundsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/exam-rounds';
};

export type GetExamRoundsApiExamRoundsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetExamRoundsApiExamRoundsGetError = GetExamRoundsApiExamRoundsGetErrors[keyof GetExamRoundsApiExamRoundsGetErrors];

export type GetExamRoundsApiExamRoundsGetResponses = {
    /**
     * Successful Response
     */
    200: DomainCollectionResponse;
};

export type GetExamRoundsApiExamRoundsGetResponse = GetExamRoundsApiExamRoundsGetResponses[keyof GetExamRoundsApiExamRoundsGetResponses];

export type CreateExamRoundsApiExamRoundsPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/exam-rounds';
};

export type CreateExamRoundsApiExamRoundsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateExamRoundsApiExamRoundsPostError = CreateExamRoundsApiExamRoundsPostErrors[keyof CreateExamRoundsApiExamRoundsPostErrors];

export type CreateExamRoundsApiExamRoundsPostResponses = {
    /**
     * Successful Response
     */
    201: DomainResourceResponse;
};

export type CreateExamRoundsApiExamRoundsPostResponse = CreateExamRoundsApiExamRoundsPostResponses[keyof CreateExamRoundsApiExamRoundsPostResponses];

export type DeleteExamRoundsApiExamRoundsIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}';
};

export type DeleteExamRoundsApiExamRoundsIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteExamRoundsApiExamRoundsIdDeleteError = DeleteExamRoundsApiExamRoundsIdDeleteErrors[keyof DeleteExamRoundsApiExamRoundsIdDeleteErrors];

export type DeleteExamRoundsApiExamRoundsIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteExamRoundsApiExamRoundsIdDeleteResponse = DeleteExamRoundsApiExamRoundsIdDeleteResponses[keyof DeleteExamRoundsApiExamRoundsIdDeleteResponses];

export type GetExamRoundsItemApiExamRoundsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}';
};

export type GetExamRoundsItemApiExamRoundsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetExamRoundsItemApiExamRoundsIdGetError = GetExamRoundsItemApiExamRoundsIdGetErrors[keyof GetExamRoundsItemApiExamRoundsIdGetErrors];

export type GetExamRoundsItemApiExamRoundsIdGetResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type GetExamRoundsItemApiExamRoundsIdGetResponse = GetExamRoundsItemApiExamRoundsIdGetResponses[keyof GetExamRoundsItemApiExamRoundsIdGetResponses];

export type UpdateExamRoundsApiExamRoundsIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}';
};

export type UpdateExamRoundsApiExamRoundsIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateExamRoundsApiExamRoundsIdPatchError = UpdateExamRoundsApiExamRoundsIdPatchErrors[keyof UpdateExamRoundsApiExamRoundsIdPatchErrors];

export type UpdateExamRoundsApiExamRoundsIdPatchResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type UpdateExamRoundsApiExamRoundsIdPatchResponse = UpdateExamRoundsApiExamRoundsIdPatchResponses[keyof UpdateExamRoundsApiExamRoundsIdPatchResponses];

export type CancelExamRoundApiExamRoundsIdCancellationPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/cancellation';
};

export type CancelExamRoundApiExamRoundsIdCancellationPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CancelExamRoundApiExamRoundsIdCancellationPostError = CancelExamRoundApiExamRoundsIdCancellationPostErrors[keyof CancelExamRoundApiExamRoundsIdCancellationPostErrors];

export type CancelExamRoundApiExamRoundsIdCancellationPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type SetExamRoundCandidateTerminalStatusApiExamRoundsIdCandidatesCandidateIdTerminalStatusPutData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
        /**
         * Candidate Id
         */
        candidate_id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/candidates/{candidate_id}/terminal-status';
};

export type SetExamRoundCandidateTerminalStatusApiExamRoundsIdCandidatesCandidateIdTerminalStatusPutErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SetExamRoundCandidateTerminalStatusApiExamRoundsIdCandidatesCandidateIdTerminalStatusPutError = SetExamRoundCandidateTerminalStatusApiExamRoundsIdCandidatesCandidateIdTerminalStatusPutErrors[keyof SetExamRoundCandidateTerminalStatusApiExamRoundsIdCandidatesCandidateIdTerminalStatusPutErrors];

export type SetExamRoundCandidateTerminalStatusApiExamRoundsIdCandidatesCandidateIdTerminalStatusPutResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type CloseExamRoundApiExamRoundsIdClosurePostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/closure';
};

export type CloseExamRoundApiExamRoundsIdClosurePostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CloseExamRoundApiExamRoundsIdClosurePostError = CloseExamRoundApiExamRoundsIdClosurePostErrors[keyof CloseExamRoundApiExamRoundsIdClosurePostErrors];

export type CloseExamRoundApiExamRoundsIdClosurePostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ConfirmPlanApiExamRoundsIdConfirmPlanPostData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/confirm-plan';
};

export type ConfirmPlanApiExamRoundsIdConfirmPlanPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ConfirmPlanApiExamRoundsIdConfirmPlanPostError = ConfirmPlanApiExamRoundsIdConfirmPlanPostErrors[keyof ConfirmPlanApiExamRoundsIdConfirmPlanPostErrors];

export type ConfirmPlanApiExamRoundsIdConfirmPlanPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetConfirmedPlanApiExamRoundsIdConfirmedPlanGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/confirmed-plan';
};

export type GetConfirmedPlanApiExamRoundsIdConfirmedPlanGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetConfirmedPlanApiExamRoundsIdConfirmedPlanGetError = GetConfirmedPlanApiExamRoundsIdConfirmedPlanGetErrors[keyof GetConfirmedPlanApiExamRoundsIdConfirmedPlanGetErrors];

export type GetConfirmedPlanApiExamRoundsIdConfirmedPlanGetResponses = {
    /**
     * Successful Response
     */
    200: PlanningProposalResponse;
};

export type GetConfirmedPlanApiExamRoundsIdConfirmedPlanGetResponse = GetConfirmedPlanApiExamRoundsIdConfirmedPlanGetResponses[keyof GetConfirmedPlanApiExamRoundsIdConfirmedPlanGetResponses];

export type SaveConfirmedPlanApiExamRoundsIdConfirmedPlanPutData = {
    body: ConfirmedPlanChangeRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/confirmed-plan';
};

export type SaveConfirmedPlanApiExamRoundsIdConfirmedPlanPutErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SaveConfirmedPlanApiExamRoundsIdConfirmedPlanPutError = SaveConfirmedPlanApiExamRoundsIdConfirmedPlanPutErrors[keyof SaveConfirmedPlanApiExamRoundsIdConfirmedPlanPutErrors];

export type SaveConfirmedPlanApiExamRoundsIdConfirmedPlanPutResponses = {
    /**
     * Successful Response
     */
    200: PlanningProposalResponse;
};

export type SaveConfirmedPlanApiExamRoundsIdConfirmedPlanPutResponse = SaveConfirmedPlanApiExamRoundsIdConfirmedPlanPutResponses[keyof SaveConfirmedPlanApiExamRoundsIdConfirmedPlanPutResponses];

export type ConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanConsequencesGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/confirmed-plan/consequences';
};

export type ConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanConsequencesGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanConsequencesGetError = ConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanConsequencesGetErrors[keyof ConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanConsequencesGetErrors];

export type ConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanConsequencesGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ConfirmedPlanRevisionsApiExamRoundsIdConfirmedPlanRevisionsGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/confirmed-plan/revisions';
};

export type ConfirmedPlanRevisionsApiExamRoundsIdConfirmedPlanRevisionsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ConfirmedPlanRevisionsApiExamRoundsIdConfirmedPlanRevisionsGetError = ConfirmedPlanRevisionsApiExamRoundsIdConfirmedPlanRevisionsGetErrors[keyof ConfirmedPlanRevisionsApiExamRoundsIdConfirmedPlanRevisionsGetErrors];

export type ConfirmedPlanRevisionsApiExamRoundsIdConfirmedPlanRevisionsGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type RetryConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanRevisionsRevisionIdConsequencesRetryPostData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
        /**
         * Revision Id
         */
        revision_id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/confirmed-plan/revisions/{revision_id}/consequences/retry';
};

export type RetryConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanRevisionsRevisionIdConsequencesRetryPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type RetryConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanRevisionsRevisionIdConsequencesRetryPostError = RetryConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanRevisionsRevisionIdConsequencesRetryPostErrors[keyof RetryConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanRevisionsRevisionIdConsequencesRetryPostErrors];

export type RetryConfirmedPlanConsequencesApiExamRoundsIdConfirmedPlanRevisionsRevisionIdConsequencesRetryPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExamRoundLifecycleApiExamRoundsIdLifecycleGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/lifecycle';
};

export type ExamRoundLifecycleApiExamRoundsIdLifecycleGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamRoundLifecycleApiExamRoundsIdLifecycleGetError = ExamRoundLifecycleApiExamRoundsIdLifecycleGetErrors[keyof ExamRoundLifecycleApiExamRoundsIdLifecycleGetErrors];

export type ExamRoundLifecycleApiExamRoundsIdLifecycleGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExportExamRoundJsonApiExamRoundsIdLifecycleExportJsonGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/lifecycle/export.json';
};

export type ExportExamRoundJsonApiExamRoundsIdLifecycleExportJsonGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExportExamRoundJsonApiExamRoundsIdLifecycleExportJsonGetError = ExportExamRoundJsonApiExamRoundsIdLifecycleExportJsonGetErrors[keyof ExportExamRoundJsonApiExamRoundsIdLifecycleExportJsonGetErrors];

export type ExportExamRoundJsonApiExamRoundsIdLifecycleExportJsonGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExportExamRoundTextApiExamRoundsIdLifecycleExportTxtGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/lifecycle/export.txt';
};

export type ExportExamRoundTextApiExamRoundsIdLifecycleExportTxtGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExportExamRoundTextApiExamRoundsIdLifecycleExportTxtGetError = ExportExamRoundTextApiExamRoundsIdLifecycleExportTxtGetErrors[keyof ExportExamRoundTextApiExamRoundsIdLifecycleExportTxtGetErrors];

export type ExportExamRoundTextApiExamRoundsIdLifecycleExportTxtGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetProposalApiExamRoundsIdPlanningProposalGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/planning-proposal';
};

export type GetProposalApiExamRoundsIdPlanningProposalGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetProposalApiExamRoundsIdPlanningProposalGetError = GetProposalApiExamRoundsIdPlanningProposalGetErrors[keyof GetProposalApiExamRoundsIdPlanningProposalGetErrors];

export type GetProposalApiExamRoundsIdPlanningProposalGetResponses = {
    /**
     * Successful Response
     */
    200: PlanningProposalResponse;
};

export type GetProposalApiExamRoundsIdPlanningProposalGetResponse = GetProposalApiExamRoundsIdPlanningProposalGetResponses[keyof GetProposalApiExamRoundsIdPlanningProposalGetResponses];

export type SaveProposalApiExamRoundsIdPlanningProposalPutData = {
    body: PlanningProposalWriteRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/planning-proposal';
};

export type SaveProposalApiExamRoundsIdPlanningProposalPutErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SaveProposalApiExamRoundsIdPlanningProposalPutError = SaveProposalApiExamRoundsIdPlanningProposalPutErrors[keyof SaveProposalApiExamRoundsIdPlanningProposalPutErrors];

export type SaveProposalApiExamRoundsIdPlanningProposalPutResponses = {
    /**
     * Successful Response
     */
    200: PlanningProposalResponse;
};

export type SaveProposalApiExamRoundsIdPlanningProposalPutResponse = SaveProposalApiExamRoundsIdPlanningProposalPutResponses[keyof SaveProposalApiExamRoundsIdPlanningProposalPutResponses];

export type ExamRoundReopeningImpactApiExamRoundsIdReopeningImpactPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/reopening-impact';
};

export type ExamRoundReopeningImpactApiExamRoundsIdReopeningImpactPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamRoundReopeningImpactApiExamRoundsIdReopeningImpactPostError = ExamRoundReopeningImpactApiExamRoundsIdReopeningImpactPostErrors[keyof ExamRoundReopeningImpactApiExamRoundsIdReopeningImpactPostErrors];

export type ExamRoundReopeningImpactApiExamRoundsIdReopeningImpactPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ReopenExamRoundApiExamRoundsIdReopeningsPostData = {
    body?: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/reopenings';
};

export type ReopenExamRoundApiExamRoundsIdReopeningsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ReopenExamRoundApiExamRoundsIdReopeningsPostError = ReopenExamRoundApiExamRoundsIdReopeningsPostErrors[keyof ReopenExamRoundApiExamRoundsIdReopeningsPostErrors];

export type ReopenExamRoundApiExamRoundsIdReopeningsPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type RequestAvailabilitiesApiExamRoundsIdRequestAvailabilitiesPostData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/request-availabilities';
};

export type RequestAvailabilitiesApiExamRoundsIdRequestAvailabilitiesPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type RequestAvailabilitiesApiExamRoundsIdRequestAvailabilitiesPostError = RequestAvailabilitiesApiExamRoundsIdRequestAvailabilitiesPostErrors[keyof RequestAvailabilitiesApiExamRoundsIdRequestAvailabilitiesPostErrors];

export type RequestAvailabilitiesApiExamRoundsIdRequestAvailabilitiesPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DocumentExamRoundIhkStatusApiExamRoundsIdResultsResultIdIhkStatusPutData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
        /**
         * Result Id
         */
        result_id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{id}/results/{result_id}/ihk-status';
};

export type DocumentExamRoundIhkStatusApiExamRoundsIdResultsResultIdIhkStatusPutErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DocumentExamRoundIhkStatusApiExamRoundsIdResultsResultIdIhkStatusPutError = DocumentExamRoundIhkStatusApiExamRoundsIdResultsResultIdIhkStatusPutErrors[keyof DocumentExamRoundIhkStatusApiExamRoundsIdResultsResultIdIhkStatusPutErrors];

export type DocumentExamRoundIhkStatusApiExamRoundsIdResultsResultIdIhkStatusPutResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type AssessmentModelBindingApiExamRoundsRoundIdAssessmentModelBindingGetData = {
    body?: never;
    path: {
        /**
         * Round Id
         */
        round_id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{round_id}/assessment-model-binding';
};

export type AssessmentModelBindingApiExamRoundsRoundIdAssessmentModelBindingGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type AssessmentModelBindingApiExamRoundsRoundIdAssessmentModelBindingGetError = AssessmentModelBindingApiExamRoundsRoundIdAssessmentModelBindingGetErrors[keyof AssessmentModelBindingApiExamRoundsRoundIdAssessmentModelBindingGetErrors];

export type AssessmentModelBindingApiExamRoundsRoundIdAssessmentModelBindingGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type BindAssessmentModelApiExamRoundsRoundIdAssessmentModelBindingPostData = {
    body: AssessmentModelBindingRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Round Id
         */
        round_id: number;
    };
    query?: never;
    url: '/api/exam-rounds/{round_id}/assessment-model-binding';
};

export type BindAssessmentModelApiExamRoundsRoundIdAssessmentModelBindingPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type BindAssessmentModelApiExamRoundsRoundIdAssessmentModelBindingPostError = BindAssessmentModelApiExamRoundsRoundIdAssessmentModelBindingPostErrors[keyof BindAssessmentModelApiExamRoundsRoundIdAssessmentModelBindingPostErrors];

export type BindAssessmentModelApiExamRoundsRoundIdAssessmentModelBindingPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetPlanningExamSlotsApiExamSlotsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/exam-slots';
};

export type GetPlanningExamSlotsApiExamSlotsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPlanningExamSlotsApiExamSlotsGetError = GetPlanningExamSlotsApiExamSlotsGetErrors[keyof GetPlanningExamSlotsApiExamSlotsGetErrors];

export type GetPlanningExamSlotsApiExamSlotsGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetPlanningExamSlotsItemApiExamSlotsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-slots/{id}';
};

export type GetPlanningExamSlotsItemApiExamSlotsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPlanningExamSlotsItemApiExamSlotsIdGetError = GetPlanningExamSlotsItemApiExamSlotsIdGetErrors[keyof GetPlanningExamSlotsItemApiExamSlotsIdGetErrors];

export type GetPlanningExamSlotsItemApiExamSlotsIdGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type RetryExamVenueChangeConsequencesApiExamVenueChangesAuditIdConsequencesRetryPostData = {
    body?: never;
    path: {
        /**
         * Audit Id
         */
        audit_id: number;
    };
    query?: never;
    url: '/api/exam-venue-changes/{audit_id}/consequences/retry';
};

export type RetryExamVenueChangeConsequencesApiExamVenueChangesAuditIdConsequencesRetryPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type RetryExamVenueChangeConsequencesApiExamVenueChangesAuditIdConsequencesRetryPostError = RetryExamVenueChangeConsequencesApiExamVenueChangesAuditIdConsequencesRetryPostErrors[keyof RetryExamVenueChangeConsequencesApiExamVenueChangesAuditIdConsequencesRetryPostErrors];

export type RetryExamVenueChangeConsequencesApiExamVenueChangesAuditIdConsequencesRetryPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DeleteExamVenueContactApiExamVenueContactsIdDeleteData = {
    body: RevisionDeleteRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venue-contacts/{id}';
};

export type DeleteExamVenueContactApiExamVenueContactsIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteExamVenueContactApiExamVenueContactsIdDeleteError = DeleteExamVenueContactApiExamVenueContactsIdDeleteErrors[keyof DeleteExamVenueContactApiExamVenueContactsIdDeleteErrors];

export type DeleteExamVenueContactApiExamVenueContactsIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteExamVenueContactApiExamVenueContactsIdDeleteResponse = DeleteExamVenueContactApiExamVenueContactsIdDeleteResponses[keyof DeleteExamVenueContactApiExamVenueContactsIdDeleteResponses];

export type ExamVenueContactItemApiExamVenueContactsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venue-contacts/{id}';
};

export type ExamVenueContactItemApiExamVenueContactsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamVenueContactItemApiExamVenueContactsIdGetError = ExamVenueContactItemApiExamVenueContactsIdGetErrors[keyof ExamVenueContactItemApiExamVenueContactsIdGetErrors];

export type ExamVenueContactItemApiExamVenueContactsIdGetResponses = {
    /**
     * Successful Response
     */
    200: ExamVenueContactResponse;
};

export type ExamVenueContactItemApiExamVenueContactsIdGetResponse = ExamVenueContactItemApiExamVenueContactsIdGetResponses[keyof ExamVenueContactItemApiExamVenueContactsIdGetResponses];

export type UpdateExamVenueContactApiExamVenueContactsIdPatchData = {
    body: ExamVenueContactUpdateRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venue-contacts/{id}';
};

export type UpdateExamVenueContactApiExamVenueContactsIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateExamVenueContactApiExamVenueContactsIdPatchError = UpdateExamVenueContactApiExamVenueContactsIdPatchErrors[keyof UpdateExamVenueContactApiExamVenueContactsIdPatchErrors];

export type UpdateExamVenueContactApiExamVenueContactsIdPatchResponses = {
    /**
     * Successful Response
     */
    200: ExamVenueContactResponse;
};

export type UpdateExamVenueContactApiExamVenueContactsIdPatchResponse = UpdateExamVenueContactApiExamVenueContactsIdPatchResponses[keyof UpdateExamVenueContactApiExamVenueContactsIdPatchResponses];

export type ExamVenuePromotionRequestsApiExamVenuePromotionRequestsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/exam-venue-promotion-requests';
};

export type ExamVenuePromotionRequestsApiExamVenuePromotionRequestsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamVenuePromotionRequestsApiExamVenuePromotionRequestsGetError = ExamVenuePromotionRequestsApiExamVenuePromotionRequestsGetErrors[keyof ExamVenuePromotionRequestsApiExamVenuePromotionRequestsGetErrors];

export type ExamVenuePromotionRequestsApiExamVenuePromotionRequestsGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DecideExamVenuePromotionApiExamVenuePromotionRequestsIdDecisionPostData = {
    body: ExamVenuePromotionDecisionRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venue-promotion-requests/{id}/decision';
};

export type DecideExamVenuePromotionApiExamVenuePromotionRequestsIdDecisionPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DecideExamVenuePromotionApiExamVenuePromotionRequestsIdDecisionPostError = DecideExamVenuePromotionApiExamVenuePromotionRequestsIdDecisionPostErrors[keyof DecideExamVenuePromotionApiExamVenuePromotionRequestsIdDecisionPostErrors];

export type DecideExamVenuePromotionApiExamVenuePromotionRequestsIdDecisionPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type ExamVenueCollectionApiExamVenuesGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/exam-venues';
};

export type ExamVenueCollectionApiExamVenuesGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamVenueCollectionApiExamVenuesGetError = ExamVenueCollectionApiExamVenuesGetErrors[keyof ExamVenueCollectionApiExamVenuesGetErrors];

export type ExamVenueCollectionApiExamVenuesGetResponses = {
    /**
     * Successful Response
     */
    200: ExamVenueCollectionResponse;
};

export type ExamVenueCollectionApiExamVenuesGetResponse = ExamVenueCollectionApiExamVenuesGetResponses[keyof ExamVenueCollectionApiExamVenuesGetResponses];

export type CreateExamVenueApiExamVenuesPostData = {
    body: ExamVenueCreateRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/exam-venues';
};

export type CreateExamVenueApiExamVenuesPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateExamVenueApiExamVenuesPostError = CreateExamVenueApiExamVenuesPostErrors[keyof CreateExamVenueApiExamVenuesPostErrors];

export type CreateExamVenueApiExamVenuesPostResponses = {
    /**
     * Successful Response
     */
    201: ExamVenueResponse;
};

export type CreateExamVenueApiExamVenuesPostResponse = CreateExamVenueApiExamVenuesPostResponses[keyof CreateExamVenueApiExamVenuesPostResponses];

export type ExamVenueDuplicateCheckApiExamVenuesDuplicateCheckPostData = {
    body: ExamVenueDuplicateCheckRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/exam-venues/duplicate-check';
};

export type ExamVenueDuplicateCheckApiExamVenuesDuplicateCheckPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamVenueDuplicateCheckApiExamVenuesDuplicateCheckPostError = ExamVenueDuplicateCheckApiExamVenuesDuplicateCheckPostErrors[keyof ExamVenueDuplicateCheckApiExamVenuesDuplicateCheckPostErrors];

export type ExamVenueDuplicateCheckApiExamVenuesDuplicateCheckPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DeleteExamVenueApiExamVenuesIdDeleteData = {
    body: RevisionDeleteRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venues/{id}';
};

export type DeleteExamVenueApiExamVenuesIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteExamVenueApiExamVenuesIdDeleteError = DeleteExamVenueApiExamVenuesIdDeleteErrors[keyof DeleteExamVenueApiExamVenuesIdDeleteErrors];

export type DeleteExamVenueApiExamVenuesIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteExamVenueApiExamVenuesIdDeleteResponse = DeleteExamVenueApiExamVenuesIdDeleteResponses[keyof DeleteExamVenueApiExamVenuesIdDeleteResponses];

export type ExamVenueItemApiExamVenuesIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venues/{id}';
};

export type ExamVenueItemApiExamVenuesIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamVenueItemApiExamVenuesIdGetError = ExamVenueItemApiExamVenuesIdGetErrors[keyof ExamVenueItemApiExamVenuesIdGetErrors];

export type ExamVenueItemApiExamVenuesIdGetResponses = {
    /**
     * Successful Response
     */
    200: ExamVenueResponse;
};

export type ExamVenueItemApiExamVenuesIdGetResponse = ExamVenueItemApiExamVenuesIdGetResponses[keyof ExamVenueItemApiExamVenuesIdGetResponses];

export type UpdateExamVenueApiExamVenuesIdPatchData = {
    body: ExamVenueUpdateRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venues/{id}';
};

export type UpdateExamVenueApiExamVenuesIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateExamVenueApiExamVenuesIdPatchError = UpdateExamVenueApiExamVenuesIdPatchErrors[keyof UpdateExamVenueApiExamVenuesIdPatchErrors];

export type UpdateExamVenueApiExamVenuesIdPatchResponses = {
    /**
     * Successful Response
     */
    200: ExamVenueResponse;
};

export type UpdateExamVenueApiExamVenuesIdPatchResponse = UpdateExamVenueApiExamVenuesIdPatchResponses[keyof UpdateExamVenueApiExamVenuesIdPatchResponses];

export type ExamVenueChangeImpactApiExamVenuesIdChangeImpactGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venues/{id}/change-impact';
};

export type ExamVenueChangeImpactApiExamVenuesIdChangeImpactGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type ExamVenueChangeImpactApiExamVenuesIdChangeImpactGetError = ExamVenueChangeImpactApiExamVenuesIdChangeImpactGetErrors[keyof ExamVenueChangeImpactApiExamVenuesIdChangeImpactGetErrors];

export type ExamVenueChangeImpactApiExamVenuesIdChangeImpactGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type PreviewExamVenueChangeApiExamVenuesIdChangeImpactPostData = {
    body: ExamVenueUpdateRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venues/{id}/change-impact';
};

export type PreviewExamVenueChangeApiExamVenuesIdChangeImpactPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type PreviewExamVenueChangeApiExamVenuesIdChangeImpactPostError = PreviewExamVenueChangeApiExamVenuesIdChangeImpactPostErrors[keyof PreviewExamVenueChangeApiExamVenuesIdChangeImpactPostErrors];

export type PreviewExamVenueChangeApiExamVenuesIdChangeImpactPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type CreateExamVenueContactApiExamVenuesIdContactsPostData = {
    body: ExamVenueContactCreateRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venues/{id}/contacts';
};

export type CreateExamVenueContactApiExamVenuesIdContactsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateExamVenueContactApiExamVenuesIdContactsPostError = CreateExamVenueContactApiExamVenuesIdContactsPostErrors[keyof CreateExamVenueContactApiExamVenuesIdContactsPostErrors];

export type CreateExamVenueContactApiExamVenuesIdContactsPostResponses = {
    /**
     * Successful Response
     */
    201: ExamVenueContactResponse;
};

export type CreateExamVenueContactApiExamVenuesIdContactsPostResponse = CreateExamVenueContactApiExamVenuesIdContactsPostResponses[keyof CreateExamVenueContactApiExamVenuesIdContactsPostResponses];

export type GeocodeExamVenueApiExamVenuesIdGeocodePostData = {
    body: ExamVenueGeocodeRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venues/{id}/geocode';
};

export type GeocodeExamVenueApiExamVenuesIdGeocodePostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GeocodeExamVenueApiExamVenuesIdGeocodePostError = GeocodeExamVenueApiExamVenuesIdGeocodePostErrors[keyof GeocodeExamVenueApiExamVenuesIdGeocodePostErrors];

export type GeocodeExamVenueApiExamVenuesIdGeocodePostResponses = {
    /**
     * Successful Response
     */
    200: ExamVenueGeocodeResponse;
};

export type GeocodeExamVenueApiExamVenuesIdGeocodePostResponse = GeocodeExamVenueApiExamVenuesIdGeocodePostResponses[keyof GeocodeExamVenueApiExamVenuesIdGeocodePostResponses];

export type RequestExamVenuePromotionApiExamVenuesIdPromotionRequestsPostData = {
    body: ExamVenuePromotionRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venues/{id}/promotion-requests';
};

export type RequestExamVenuePromotionApiExamVenuesIdPromotionRequestsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type RequestExamVenuePromotionApiExamVenuesIdPromotionRequestsPostError = RequestExamVenuePromotionApiExamVenuesIdPromotionRequestsPostErrors[keyof RequestExamVenuePromotionApiExamVenuesIdPromotionRequestsPostErrors];

export type RequestExamVenuePromotionApiExamVenuesIdPromotionRequestsPostResponses = {
    /**
     * Successful Response
     */
    201: unknown;
};

export type CreateExamRoomApiExamVenuesIdRoomsPostData = {
    body: ExamRoomCreateRequest;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/exam-venues/{id}/rooms';
};

export type CreateExamRoomApiExamVenuesIdRoomsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateExamRoomApiExamVenuesIdRoomsPostError = CreateExamRoomApiExamVenuesIdRoomsPostErrors[keyof CreateExamRoomApiExamVenuesIdRoomsPostErrors];

export type CreateExamRoomApiExamVenuesIdRoomsPostResponses = {
    /**
     * Successful Response
     */
    201: ExamRoomResponse;
};

export type CreateExamRoomApiExamVenuesIdRoomsPostResponse = CreateExamRoomApiExamVenuesIdRoomsPostResponses[keyof CreateExamRoomApiExamVenuesIdRoomsPostResponses];

export type HealthApiHealthGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/health';
};

export type HealthApiHealthGetResponses = {
    /**
     * Successful Response
     */
    200: HealthResponse;
};

export type HealthApiHealthGetResponse = HealthApiHealthGetResponses[keyof HealthApiHealthGetResponses];

export type LifecycleApiLifecycleGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/lifecycle';
};

export type LifecycleApiLifecycleGetResponses = {
    /**
     * Successful Response
     */
    200: LifecycleResponse;
};

export type LifecycleApiLifecycleGetResponse = LifecycleApiLifecycleGetResponses[keyof LifecycleApiLifecycleGetResponses];

export type LegacyLocationCollectionApiLocationsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/locations';
};

export type LegacyLocationCollectionApiLocationsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type LegacyLocationCollectionApiLocationsGetError = LegacyLocationCollectionApiLocationsGetErrors[keyof LegacyLocationCollectionApiLocationsGetErrors];

export type LegacyLocationCollectionApiLocationsGetResponses = {
    /**
     * Successful Response
     */
    200: LegacyLocationCollectionResponse;
};

export type LegacyLocationCollectionApiLocationsGetResponse = LegacyLocationCollectionApiLocationsGetResponses[keyof LegacyLocationCollectionApiLocationsGetResponses];

export type CreateLegacyLocationApiLocationsPostData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/locations';
};

export type CreateLegacyLocationApiLocationsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Response Create Legacy Location Api Locations Post
     *
     * Successful Response
     */
    410: {
        [key: string]: unknown;
    };
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateLegacyLocationApiLocationsPostError = CreateLegacyLocationApiLocationsPostErrors[keyof CreateLegacyLocationApiLocationsPostErrors];

export type DeleteLegacyLocationApiLocationsIdDeleteData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/locations/{id}';
};

export type DeleteLegacyLocationApiLocationsIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Response Delete Legacy Location Api Locations  Id  Delete
     *
     * Successful Response
     */
    410: {
        [key: string]: unknown;
    };
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteLegacyLocationApiLocationsIdDeleteError = DeleteLegacyLocationApiLocationsIdDeleteErrors[keyof DeleteLegacyLocationApiLocationsIdDeleteErrors];

export type LegacyLocationItemApiLocationsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/locations/{id}';
};

export type LegacyLocationItemApiLocationsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type LegacyLocationItemApiLocationsIdGetError = LegacyLocationItemApiLocationsIdGetErrors[keyof LegacyLocationItemApiLocationsIdGetErrors];

export type LegacyLocationItemApiLocationsIdGetResponses = {
    /**
     * Successful Response
     */
    200: LegacyLocationResponse;
};

export type LegacyLocationItemApiLocationsIdGetResponse = LegacyLocationItemApiLocationsIdGetResponses[keyof LegacyLocationItemApiLocationsIdGetResponses];

export type UpdateLegacyLocationApiLocationsIdPatchData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/locations/{id}';
};

export type UpdateLegacyLocationApiLocationsIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Response Update Legacy Location Api Locations  Id  Patch
     *
     * Successful Response
     */
    410: {
        [key: string]: unknown;
    };
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateLegacyLocationApiLocationsIdPatchError = UpdateLegacyLocationApiLocationsIdPatchErrors[keyof UpdateLegacyLocationApiLocationsIdPatchErrors];

export type GetMemberAvailabilitiesApiMemberAvailabilitiesGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/member-availabilities';
};

export type GetMemberAvailabilitiesApiMemberAvailabilitiesGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetMemberAvailabilitiesApiMemberAvailabilitiesGetError = GetMemberAvailabilitiesApiMemberAvailabilitiesGetErrors[keyof GetMemberAvailabilitiesApiMemberAvailabilitiesGetErrors];

export type GetMemberAvailabilitiesApiMemberAvailabilitiesGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type CreateMemberAvailabilitiesApiMemberAvailabilitiesPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/member-availabilities';
};

export type CreateMemberAvailabilitiesApiMemberAvailabilitiesPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateMemberAvailabilitiesApiMemberAvailabilitiesPostError = CreateMemberAvailabilitiesApiMemberAvailabilitiesPostErrors[keyof CreateMemberAvailabilitiesApiMemberAvailabilitiesPostErrors];

export type CreateMemberAvailabilitiesApiMemberAvailabilitiesPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DeleteMemberAvailabilitiesApiMemberAvailabilitiesIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/member-availabilities/{id}';
};

export type DeleteMemberAvailabilitiesApiMemberAvailabilitiesIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteMemberAvailabilitiesApiMemberAvailabilitiesIdDeleteError = DeleteMemberAvailabilitiesApiMemberAvailabilitiesIdDeleteErrors[keyof DeleteMemberAvailabilitiesApiMemberAvailabilitiesIdDeleteErrors];

export type DeleteMemberAvailabilitiesApiMemberAvailabilitiesIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteMemberAvailabilitiesApiMemberAvailabilitiesIdDeleteResponse = DeleteMemberAvailabilitiesApiMemberAvailabilitiesIdDeleteResponses[keyof DeleteMemberAvailabilitiesApiMemberAvailabilitiesIdDeleteResponses];

export type GetMemberAvailabilitiesItemApiMemberAvailabilitiesIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/member-availabilities/{id}';
};

export type GetMemberAvailabilitiesItemApiMemberAvailabilitiesIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetMemberAvailabilitiesItemApiMemberAvailabilitiesIdGetError = GetMemberAvailabilitiesItemApiMemberAvailabilitiesIdGetErrors[keyof GetMemberAvailabilitiesItemApiMemberAvailabilitiesIdGetErrors];

export type GetMemberAvailabilitiesItemApiMemberAvailabilitiesIdGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type UpdateMemberAvailabilitiesApiMemberAvailabilitiesIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/member-availabilities/{id}';
};

export type UpdateMemberAvailabilitiesApiMemberAvailabilitiesIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateMemberAvailabilitiesApiMemberAvailabilitiesIdPatchError = UpdateMemberAvailabilitiesApiMemberAvailabilitiesIdPatchErrors[keyof UpdateMemberAvailabilitiesApiMemberAvailabilitiesIdPatchErrors];

export type UpdateMemberAvailabilitiesApiMemberAvailabilitiesIdPatchResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetMembersApiMembersGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/members';
};

export type GetMembersApiMembersGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetMembersApiMembersGetError = GetMembersApiMembersGetErrors[keyof GetMembersApiMembersGetErrors];

export type GetMembersApiMembersGetResponses = {
    /**
     * Successful Response
     */
    200: DomainCollectionResponse;
};

export type GetMembersApiMembersGetResponse = GetMembersApiMembersGetResponses[keyof GetMembersApiMembersGetResponses];

export type CreateMembersApiMembersPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/members';
};

export type CreateMembersApiMembersPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateMembersApiMembersPostError = CreateMembersApiMembersPostErrors[keyof CreateMembersApiMembersPostErrors];

export type CreateMembersApiMembersPostResponses = {
    /**
     * Successful Response
     */
    201: DomainResourceResponse;
};

export type CreateMembersApiMembersPostResponse = CreateMembersApiMembersPostResponses[keyof CreateMembersApiMembersPostResponses];

export type DeleteMembersApiMembersIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/members/{id}';
};

export type DeleteMembersApiMembersIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteMembersApiMembersIdDeleteError = DeleteMembersApiMembersIdDeleteErrors[keyof DeleteMembersApiMembersIdDeleteErrors];

export type DeleteMembersApiMembersIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteMembersApiMembersIdDeleteResponse = DeleteMembersApiMembersIdDeleteResponses[keyof DeleteMembersApiMembersIdDeleteResponses];

export type GetMembersItemApiMembersIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/members/{id}';
};

export type GetMembersItemApiMembersIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetMembersItemApiMembersIdGetError = GetMembersItemApiMembersIdGetErrors[keyof GetMembersItemApiMembersIdGetErrors];

export type GetMembersItemApiMembersIdGetResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type GetMembersItemApiMembersIdGetResponse = GetMembersItemApiMembersIdGetResponses[keyof GetMembersItemApiMembersIdGetResponses];

export type UpdateMembersApiMembersIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/members/{id}';
};

export type UpdateMembersApiMembersIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateMembersApiMembersIdPatchError = UpdateMembersApiMembersIdPatchErrors[keyof UpdateMembersApiMembersIdPatchErrors];

export type UpdateMembersApiMembersIdPatchResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type UpdateMembersApiMembersIdPatchResponse = UpdateMembersApiMembersIdPatchResponses[keyof UpdateMembersApiMembersIdPatchResponses];

export type GetMembershipsApiMembershipsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/memberships';
};

export type GetMembershipsApiMembershipsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetMembershipsApiMembershipsGetError = GetMembershipsApiMembershipsGetErrors[keyof GetMembershipsApiMembershipsGetErrors];

export type GetMembershipsApiMembershipsGetResponses = {
    /**
     * Successful Response
     */
    200: DomainCollectionResponse;
};

export type GetMembershipsApiMembershipsGetResponse = GetMembershipsApiMembershipsGetResponses[keyof GetMembershipsApiMembershipsGetResponses];

export type CreateMembershipsApiMembershipsPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/memberships';
};

export type CreateMembershipsApiMembershipsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateMembershipsApiMembershipsPostError = CreateMembershipsApiMembershipsPostErrors[keyof CreateMembershipsApiMembershipsPostErrors];

export type CreateMembershipsApiMembershipsPostResponses = {
    /**
     * Successful Response
     */
    201: DomainResourceResponse;
};

export type CreateMembershipsApiMembershipsPostResponse = CreateMembershipsApiMembershipsPostResponses[keyof CreateMembershipsApiMembershipsPostResponses];

export type DeleteMembershipsApiMembershipsIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/memberships/{id}';
};

export type DeleteMembershipsApiMembershipsIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteMembershipsApiMembershipsIdDeleteError = DeleteMembershipsApiMembershipsIdDeleteErrors[keyof DeleteMembershipsApiMembershipsIdDeleteErrors];

export type DeleteMembershipsApiMembershipsIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteMembershipsApiMembershipsIdDeleteResponse = DeleteMembershipsApiMembershipsIdDeleteResponses[keyof DeleteMembershipsApiMembershipsIdDeleteResponses];

export type GetMembershipsItemApiMembershipsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/memberships/{id}';
};

export type GetMembershipsItemApiMembershipsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetMembershipsItemApiMembershipsIdGetError = GetMembershipsItemApiMembershipsIdGetErrors[keyof GetMembershipsItemApiMembershipsIdGetErrors];

export type GetMembershipsItemApiMembershipsIdGetResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type GetMembershipsItemApiMembershipsIdGetResponse = GetMembershipsItemApiMembershipsIdGetResponses[keyof GetMembershipsItemApiMembershipsIdGetResponses];

export type UpdateMembershipsApiMembershipsIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/memberships/{id}';
};

export type UpdateMembershipsApiMembershipsIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateMembershipsApiMembershipsIdPatchError = UpdateMembershipsApiMembershipsIdPatchErrors[keyof UpdateMembershipsApiMembershipsIdPatchErrors];

export type UpdateMembershipsApiMembershipsIdPatchResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type UpdateMembershipsApiMembershipsIdPatchResponse = UpdateMembershipsApiMembershipsIdPatchResponses[keyof UpdateMembershipsApiMembershipsIdPatchResponses];

export type NotificationChannelsApiNotificationChannelsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/notification-channels';
};

export type NotificationChannelsApiNotificationChannelsGetResponses = {
    /**
     * Successful Response
     */
    200: NotificationChannelsResponse;
};

export type NotificationChannelsApiNotificationChannelsGetResponse = NotificationChannelsApiNotificationChannelsGetResponses[keyof NotificationChannelsApiNotificationChannelsGetResponses];

export type NotificationOverviewApiNotificationOverviewGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/notification-overview';
};

export type NotificationOverviewApiNotificationOverviewGetResponses = {
    /**
     * Successful Response
     */
    200: NotificationCollectionResponse;
};

export type NotificationOverviewApiNotificationOverviewGetResponse = NotificationOverviewApiNotificationOverviewGetResponses[keyof NotificationOverviewApiNotificationOverviewGetResponses];

export type NotificationProblemsApiNotificationProblemsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/notification-problems';
};

export type NotificationProblemsApiNotificationProblemsGetResponses = {
    /**
     * Successful Response
     */
    200: NotificationCollectionResponse;
};

export type NotificationProblemsApiNotificationProblemsGetResponse = NotificationProblemsApiNotificationProblemsGetResponses[keyof NotificationProblemsApiNotificationProblemsGetResponses];

export type NotificationsApiNotificationsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/notifications';
};

export type NotificationsApiNotificationsGetResponses = {
    /**
     * Successful Response
     */
    200: NotificationCollectionResponse;
};

export type NotificationsApiNotificationsGetResponse = NotificationsApiNotificationsGetResponses[keyof NotificationsApiNotificationsGetResponses];

export type ConfirmPushApiNotificationsIdPushConfirmationPostData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/notifications/{id}/push-confirmation';
};

export type ConfirmPushApiNotificationsIdPushConfirmationPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type ConfirmPushApiNotificationsIdPushConfirmationPostError = ConfirmPushApiNotificationsIdPushConfirmationPostErrors[keyof ConfirmPushApiNotificationsIdPushConfirmationPostErrors];

export type ConfirmPushApiNotificationsIdPushConfirmationPostResponses = {
    /**
     * Successful Response
     */
    200: PushConfirmationResponse;
};

export type ConfirmPushApiNotificationsIdPushConfirmationPostResponse = ConfirmPushApiNotificationsIdPushConfirmationPostResponses[keyof ConfirmPushApiNotificationsIdPushConfirmationPostResponses];

export type FrontendErrorApiObservabilityFrontendErrorsPostData = {
    body: FrontendErrorRequest;
    path?: never;
    query?: never;
    url: '/api/observability/frontend-errors';
};

export type FrontendErrorApiObservabilityFrontendErrorsPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type FrontendErrorApiObservabilityFrontendErrorsPostError = FrontendErrorApiObservabilityFrontendErrorsPostErrors[keyof FrontendErrorApiObservabilityFrontendErrorsPostErrors];

export type FrontendErrorApiObservabilityFrontendErrorsPostResponses = {
    /**
     * Successful Response
     */
    202: unknown;
};

export type OpenapiDocumentApiOpenapiJsonGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/openapi.json';
};

export type OpenapiDocumentApiOpenapiJsonGetResponses = {
    /**
     * Response Openapi Document Api Openapi Json Get
     *
     * Successful Response
     */
    200: {
        [key: string]: unknown;
    };
};

export type OpenapiDocumentApiOpenapiJsonGetResponse = OpenapiDocumentApiOpenapiJsonGetResponses[keyof OpenapiDocumentApiOpenapiJsonGetResponses];

export type GetPersonsApiPersonsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/persons';
};

export type GetPersonsApiPersonsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPersonsApiPersonsGetError = GetPersonsApiPersonsGetErrors[keyof GetPersonsApiPersonsGetErrors];

export type GetPersonsApiPersonsGetResponses = {
    /**
     * Successful Response
     */
    200: DomainCollectionResponse;
};

export type GetPersonsApiPersonsGetResponse = GetPersonsApiPersonsGetResponses[keyof GetPersonsApiPersonsGetResponses];

export type CreatePersonsApiPersonsPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/persons';
};

export type CreatePersonsApiPersonsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreatePersonsApiPersonsPostError = CreatePersonsApiPersonsPostErrors[keyof CreatePersonsApiPersonsPostErrors];

export type CreatePersonsApiPersonsPostResponses = {
    /**
     * Successful Response
     */
    201: DomainResourceResponse;
};

export type CreatePersonsApiPersonsPostResponse = CreatePersonsApiPersonsPostResponses[keyof CreatePersonsApiPersonsPostResponses];

export type DeletePersonsApiPersonsIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/persons/{id}';
};

export type DeletePersonsApiPersonsIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeletePersonsApiPersonsIdDeleteError = DeletePersonsApiPersonsIdDeleteErrors[keyof DeletePersonsApiPersonsIdDeleteErrors];

export type DeletePersonsApiPersonsIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeletePersonsApiPersonsIdDeleteResponse = DeletePersonsApiPersonsIdDeleteResponses[keyof DeletePersonsApiPersonsIdDeleteResponses];

export type GetPersonsItemApiPersonsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/persons/{id}';
};

export type GetPersonsItemApiPersonsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPersonsItemApiPersonsIdGetError = GetPersonsItemApiPersonsIdGetErrors[keyof GetPersonsItemApiPersonsIdGetErrors];

export type GetPersonsItemApiPersonsIdGetResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type GetPersonsItemApiPersonsIdGetResponse = GetPersonsItemApiPersonsIdGetResponses[keyof GetPersonsItemApiPersonsIdGetResponses];

export type UpdatePersonsApiPersonsIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/persons/{id}';
};

export type UpdatePersonsApiPersonsIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdatePersonsApiPersonsIdPatchError = UpdatePersonsApiPersonsIdPatchErrors[keyof UpdatePersonsApiPersonsIdPatchErrors];

export type UpdatePersonsApiPersonsIdPatchResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type UpdatePersonsApiPersonsIdPatchResponse = UpdatePersonsApiPersonsIdPatchResponses[keyof UpdatePersonsApiPersonsIdPatchResponses];

export type GenerateProposalApiPlanningProposalsPostData = {
    body: PlanningRoundRequest;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/planning-proposals';
};

export type GenerateProposalApiPlanningProposalsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GenerateProposalApiPlanningProposalsPostError = GenerateProposalApiPlanningProposalsPostErrors[keyof GenerateProposalApiPlanningProposalsPostErrors];

export type GenerateProposalApiPlanningProposalsPostResponses = {
    /**
     * Successful Response
     */
    201: PlanningProposalResultResponse;
};

export type GenerateProposalApiPlanningProposalsPostResponse = GenerateProposalApiPlanningProposalsPostResponses[keyof GenerateProposalApiPlanningProposalsPostResponses];

export type GetPlanningSettingsApiPlanningSettingsGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/planning-settings';
};

export type GetPlanningSettingsApiPlanningSettingsGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPlanningSettingsApiPlanningSettingsGetError = GetPlanningSettingsApiPlanningSettingsGetErrors[keyof GetPlanningSettingsApiPlanningSettingsGetErrors];

export type GetPlanningSettingsApiPlanningSettingsGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type CreatePlanningSettingsApiPlanningSettingsPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/planning-settings';
};

export type CreatePlanningSettingsApiPlanningSettingsPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreatePlanningSettingsApiPlanningSettingsPostError = CreatePlanningSettingsApiPlanningSettingsPostErrors[keyof CreatePlanningSettingsApiPlanningSettingsPostErrors];

export type CreatePlanningSettingsApiPlanningSettingsPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type DeletePlanningSettingsApiPlanningSettingsIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/planning-settings/{id}';
};

export type DeletePlanningSettingsApiPlanningSettingsIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeletePlanningSettingsApiPlanningSettingsIdDeleteError = DeletePlanningSettingsApiPlanningSettingsIdDeleteErrors[keyof DeletePlanningSettingsApiPlanningSettingsIdDeleteErrors];

export type DeletePlanningSettingsApiPlanningSettingsIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeletePlanningSettingsApiPlanningSettingsIdDeleteResponse = DeletePlanningSettingsApiPlanningSettingsIdDeleteResponses[keyof DeletePlanningSettingsApiPlanningSettingsIdDeleteResponses];

export type GetPlanningSettingsItemApiPlanningSettingsIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/planning-settings/{id}';
};

export type GetPlanningSettingsItemApiPlanningSettingsIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetPlanningSettingsItemApiPlanningSettingsIdGetError = GetPlanningSettingsItemApiPlanningSettingsIdGetErrors[keyof GetPlanningSettingsItemApiPlanningSettingsIdGetErrors];

export type GetPlanningSettingsItemApiPlanningSettingsIdGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type UpdatePlanningSettingsApiPlanningSettingsIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/planning-settings/{id}';
};

export type UpdatePlanningSettingsApiPlanningSettingsIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdatePlanningSettingsApiPlanningSettingsIdPatchError = UpdatePlanningSettingsApiPlanningSettingsIdPatchErrors[keyof UpdatePlanningSettingsApiPlanningSettingsIdPatchErrors];

export type UpdatePlanningSettingsApiPlanningSettingsIdPatchResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type RegisterPushApiPushSubscriptionsPostData = {
    body: PushSubscriptionRequest;
    path?: never;
    query?: never;
    url: '/api/push-subscriptions';
};

export type RegisterPushApiPushSubscriptionsPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type RegisterPushApiPushSubscriptionsPostError = RegisterPushApiPushSubscriptionsPostErrors[keyof RegisterPushApiPushSubscriptionsPostErrors];

export type RegisterPushApiPushSubscriptionsPostResponses = {
    /**
     * Successful Response
     */
    201: PushSubscriptionResponse;
};

export type RegisterPushApiPushSubscriptionsPostResponse = RegisterPushApiPushSubscriptionsPostResponses[keyof RegisterPushApiPushSubscriptionsPostResponses];

export type UnregisterPushApiPushSubscriptionsIdDeleteData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/push-subscriptions/{id}';
};

export type UnregisterPushApiPushSubscriptionsIdDeleteErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type UnregisterPushApiPushSubscriptionsIdDeleteError = UnregisterPushApiPushSubscriptionsIdDeleteErrors[keyof UnregisterPushApiPushSubscriptionsIdDeleteErrors];

export type UnregisterPushApiPushSubscriptionsIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type UnregisterPushApiPushSubscriptionsIdDeleteResponse = UnregisterPushApiPushSubscriptionsIdDeleteResponses[keyof UnregisterPushApiPushSubscriptionsIdDeleteResponses];

export type ReadyApiReadyGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/ready';
};

export type ReadyApiReadyGetErrors = {
    /**
     * Service Unavailable
     */
    503: LifecycleResponse;
};

export type ReadyApiReadyGetError = ReadyApiReadyGetErrors[keyof ReadyApiReadyGetErrors];

export type ReadyApiReadyGetResponses = {
    /**
     * Successful Response
     */
    200: LifecycleResponse;
};

export type ReadyApiReadyGetResponse = ReadyApiReadyGetResponses[keyof ReadyApiReadyGetResponses];

export type PatchResponseApiReplacementResponsesResponseIdPatchData = {
    body: DomainResourceWrite;
    path: {
        /**
         * Response Id
         */
        response_id: number;
    };
    query?: never;
    url: '/api/replacement-responses/{response_id}';
};

export type PatchResponseApiReplacementResponsesResponseIdPatchErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type PatchResponseApiReplacementResponsesResponseIdPatchError = PatchResponseApiReplacementResponsesResponseIdPatchErrors[keyof PatchResponseApiReplacementResponsesResponseIdPatchErrors];

export type PatchResponseApiReplacementResponsesResponseIdPatchResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type PostResponseApiReplacementResponsesResponseIdRespondPostData = {
    body: DomainResourceWrite;
    path: {
        /**
         * Response Id
         */
        response_id: number;
    };
    query?: never;
    url: '/api/replacement-responses/{response_id}/respond';
};

export type PostResponseApiReplacementResponsesResponseIdRespondPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type PostResponseApiReplacementResponsesResponseIdRespondPostError = PostResponseApiReplacementResponsesResponseIdRespondPostErrors[keyof PostResponseApiReplacementResponsesResponseIdRespondPostErrors];

export type PostResponseApiReplacementResponsesResponseIdRespondPostResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type GetRoundCandidatesApiRoundCandidatesGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/round-candidates';
};

export type GetRoundCandidatesApiRoundCandidatesGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetRoundCandidatesApiRoundCandidatesGetError = GetRoundCandidatesApiRoundCandidatesGetErrors[keyof GetRoundCandidatesApiRoundCandidatesGetErrors];

export type GetRoundCandidatesApiRoundCandidatesGetResponses = {
    /**
     * Successful Response
     */
    200: DomainCollectionResponse;
};

export type GetRoundCandidatesApiRoundCandidatesGetResponse = GetRoundCandidatesApiRoundCandidatesGetResponses[keyof GetRoundCandidatesApiRoundCandidatesGetResponses];

export type CreateRoundCandidatesApiRoundCandidatesPostData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/round-candidates';
};

export type CreateRoundCandidatesApiRoundCandidatesPostErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type CreateRoundCandidatesApiRoundCandidatesPostError = CreateRoundCandidatesApiRoundCandidatesPostErrors[keyof CreateRoundCandidatesApiRoundCandidatesPostErrors];

export type CreateRoundCandidatesApiRoundCandidatesPostResponses = {
    /**
     * Successful Response
     */
    201: DomainResourceResponse;
};

export type CreateRoundCandidatesApiRoundCandidatesPostResponse = CreateRoundCandidatesApiRoundCandidatesPostResponses[keyof CreateRoundCandidatesApiRoundCandidatesPostResponses];

export type DeleteRoundCandidatesApiRoundCandidatesIdDeleteData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/round-candidates/{id}';
};

export type DeleteRoundCandidatesApiRoundCandidatesIdDeleteErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type DeleteRoundCandidatesApiRoundCandidatesIdDeleteError = DeleteRoundCandidatesApiRoundCandidatesIdDeleteErrors[keyof DeleteRoundCandidatesApiRoundCandidatesIdDeleteErrors];

export type DeleteRoundCandidatesApiRoundCandidatesIdDeleteResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type DeleteRoundCandidatesApiRoundCandidatesIdDeleteResponse = DeleteRoundCandidatesApiRoundCandidatesIdDeleteResponses[keyof DeleteRoundCandidatesApiRoundCandidatesIdDeleteResponses];

export type GetRoundCandidatesItemApiRoundCandidatesIdGetData = {
    body?: never;
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/round-candidates/{id}';
};

export type GetRoundCandidatesItemApiRoundCandidatesIdGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type GetRoundCandidatesItemApiRoundCandidatesIdGetError = GetRoundCandidatesItemApiRoundCandidatesIdGetErrors[keyof GetRoundCandidatesItemApiRoundCandidatesIdGetErrors];

export type GetRoundCandidatesItemApiRoundCandidatesIdGetResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type GetRoundCandidatesItemApiRoundCandidatesIdGetResponse = GetRoundCandidatesItemApiRoundCandidatesIdGetResponses[keyof GetRoundCandidatesItemApiRoundCandidatesIdGetResponses];

export type UpdateRoundCandidatesApiRoundCandidatesIdPatchData = {
    body: DomainResourceWrite;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path: {
        /**
         * Id
         */
        id: number;
    };
    query?: never;
    url: '/api/round-candidates/{id}';
};

export type UpdateRoundCandidatesApiRoundCandidatesIdPatchErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type UpdateRoundCandidatesApiRoundCandidatesIdPatchError = UpdateRoundCandidatesApiRoundCandidatesIdPatchErrors[keyof UpdateRoundCandidatesApiRoundCandidatesIdPatchErrors];

export type UpdateRoundCandidatesApiRoundCandidatesIdPatchResponses = {
    /**
     * Successful Response
     */
    200: DomainResourceResponse;
};

export type UpdateRoundCandidatesApiRoundCandidatesIdPatchResponse = UpdateRoundCandidatesApiRoundCandidatesIdPatchResponses[keyof UpdateRoundCandidatesApiRoundCandidatesIdPatchResponses];

export type RoundSummaryApiRoundSummaryGetData = {
    body?: never;
    path?: never;
    query?: {
        /**
         * Round Id
         */
        round_id?: number | null;
    };
    url: '/api/round-summary';
};

export type RoundSummaryApiRoundSummaryGetErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type RoundSummaryApiRoundSummaryGetError = RoundSummaryApiRoundSummaryGetErrors[keyof RoundSummaryApiRoundSummaryGetErrors];

export type RoundSummaryApiRoundSummaryGetResponses = {
    /**
     * Response Round Summary Api Round Summary Get
     *
     * Successful Response
     */
    200: {
        [key: string]: unknown;
    };
};

export type RoundSummaryApiRoundSummaryGetResponse = RoundSummaryApiRoundSummaryGetResponses[keyof RoundSummaryApiRoundSummaryGetResponses];

export type SchedulingApiSchedulingOverviewGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/scheduling-overview';
};

export type SchedulingApiSchedulingOverviewGetErrors = {
    /**
     * Application error
     */
    400: ErrorResponse;
    /**
     * Application error
     */
    401: ErrorResponse;
    /**
     * Application error
     */
    403: ErrorResponse;
    /**
     * Application error
     */
    404: ErrorResponse;
    /**
     * Application error
     */
    409: ErrorResponse;
    /**
     * Application error
     */
    413: ErrorResponse;
    /**
     * Application error
     */
    415: ErrorResponse;
    /**
     * Application error
     */
    422: ErrorResponse;
    /**
     * Application error
     */
    429: ErrorResponse;
    /**
     * Application error
     */
    500: ErrorResponse;
    /**
     * Runtime is not ready. Inspect lifecycle; never automatically retry a mutation.
     */
    503: RuntimeUnavailableResponse;
};

export type SchedulingApiSchedulingOverviewGetError = SchedulingApiSchedulingOverviewGetErrors[keyof SchedulingApiSchedulingOverviewGetErrors];

export type SchedulingApiSchedulingOverviewGetResponses = {
    /**
     * Successful Response
     */
    200: unknown;
};

export type SessionApiSessionGetData = {
    body?: never;
    path?: never;
    query?: never;
    url: '/api/session';
};

export type SessionApiSessionGetResponses = {
    /**
     * Successful Response
     */
    200: SessionResponse;
};

export type SessionApiSessionGetResponse = SessionApiSessionGetResponses[keyof SessionApiSessionGetResponses];

export type LogoutSessionApiSessionLogoutPostData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/session/logout';
};

export type LogoutSessionApiSessionLogoutPostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type LogoutSessionApiSessionLogoutPostError = LogoutSessionApiSessionLogoutPostErrors[keyof LogoutSessionApiSessionLogoutPostErrors];

export type LogoutSessionApiSessionLogoutPostResponses = {
    /**
     * Successful Response
     */
    204: void;
};

export type LogoutSessionApiSessionLogoutPostResponse = LogoutSessionApiSessionLogoutPostResponses[keyof LogoutSessionApiSessionLogoutPostResponses];

export type RotateSessionApiSessionRotatePostData = {
    body?: never;
    headers?: {
        /**
         * X-Csrf-Token
         */
        'X-CSRF-Token'?: string | null;
    };
    path?: never;
    query?: never;
    url: '/api/session/rotate';
};

export type RotateSessionApiSessionRotatePostErrors = {
    /**
     * Validation Error
     */
    422: HttpValidationError;
};

export type RotateSessionApiSessionRotatePostError = RotateSessionApiSessionRotatePostErrors[keyof RotateSessionApiSessionRotatePostErrors];

export type RotateSessionApiSessionRotatePostResponses = {
    /**
     * Successful Response
     */
    200: SessionRotationResponse;
};

export type RotateSessionApiSessionRotatePostResponse = RotateSessionApiSessionRotatePostResponses[keyof RotateSessionApiSessionRotatePostResponses];
