/** A HAL-like link. The optional method describes an allowed state transition. */
export type ApiLink = {
  href: string;
  method?: string;
};

export type ApiRoot = {
  name: string;
  version: string;
  _links: Record<string, ApiLink>;
};

export type ApiCollection<T> = {
  items: T[];
  _links: Record<string, ApiLink>;
};

export type NotificationItem = {
  id: number;
  event_type: string;
  title: string;
  message: string;
  action_path: string;
  created_at: string;
};

export type AbsenceResponse = {
  id: number;
  committee_member_id: number;
  response: 'pending' | 'available' | 'unavailable' | string;
  requested_at: string;
  expires_at: string | null;
  urgent: boolean;
  responded_at: string | null;
};

export type AbsenceReport = {
  id: number;
  exam_day_id: number;
  exam_day_assignment_id: number;
  committee_member_id: number;
  reported_by_member_id: number;
  reported_at: string;
  reason: string | null;
  status: string;
  selected_replacement_member_id: number | null;
  version: number;
  created_at: string;
  updated_at: string;
  responses: AbsenceResponse[];
  audit: Array<{
    id: number;
    actor_member_id: number;
    event_type: string;
    from_status: string | null;
    to_status: string | null;
    details: string | null;
    created_at: string;
  }>;
};

export type NotificationProblem = {
  notification_id: number;
  event_type: string;
  recipient_member_id: number;
  channel: 'web_push' | 'email' | 'sink';
  status:
    | 'pending'
    | 'technically_confirmed'
    | 'temporarily_failed'
    | 'permanently_failed'
    | 'unavailable';
  attempt_count: number;
  error_code: string | null;
  updated_at: string;
};

export type NotificationChannels = {
  web_push: { available: boolean; public_key: string | null };
  email_fallback_configured: boolean;
  sink_enabled: boolean;
};

export type CalendarStatus = {
  active: boolean;
  activated_at: string | null;
  revoked_at: string | null;
  time_zone: string;
  _links: Record<string, ApiLink>;
};

export type CalendarEvent = {
  id: number;
  external_event_id: string;
  date: string;
  starts_at: string;
  ends_at: string;
  time_zone: string;
  location: string;
  role: string;
  round_name: string;
  status: 'sent' | 'updated' | 'cancelled' | string;
  version: number;
  download_url: string;
};

export type CalendarFeedActivation = CalendarStatus & {
  feed_url: string;
  notice: string;
};

export type SchedulingStatusGroup = 'draft' | 'coordination' | 'planning' | 'confirmed';

export type SchedulingOverviewItem = {
  id: number;
  name: string;
  status: RoundStatus;
  status_group: SchedulingStatusGroup;
  committee_name: string;
  exam_half_year: ExamHalfYear;
  calendar_week_from: string | null;
  calendar_week_to: string | null;
  can_continue: boolean;
  _links: Record<string, ApiLink>;
};

export type ConfirmedPlanContext = {
  id: number;
  name: string;
  committee: { id: number; name: string };
  exam_half_year: ExamHalfYear;
};

export type ConfirmedPlanDay = {
  id: number;
  date: string;
  revision: number;
  closure_status: ExamDayClosureStatus;
  closure: ExamDayClosure;
  location: { id: number; name: string; room: string; city: string } | null;
  slots: Array<{
    id: number;
    starts_at: string;
    ends_at: string;
    sequence_number: number;
    slot_type: 'regular' | 'mep' | string;
    actual_started_at: string | null;
    execution_status: ExecutionStatus;
    status_changed_at: string;
    actual_completed_at: string | null;
    status_reason: string | null;
    candidate_attendance: Attendance;
    candidate: { id: number; first_name: string; last_name: string; ihk_exam_number: string };
  }>;
  assignments: Array<{
    id: number;
    assignment_role: 'examiner' | 'fallback' | string;
    day_part: 'morning' | 'afternoon' | 'full_day' | string;
    fallback_status: 'confirmed' | 'proposed' | null | string;
    attendance: Attendance;
    member: { id: number; first_name: string; last_name: string; representing_side: string };
  }>;
  status_summary: ExecutionStatusSummary;
};

export type ExamDayClosureStatus =
  'open' | 'closed' | 'closed_exception' | 'reopening' | 'historical';

export type ExamDayClosureFinding = {
  code: string;
  label: string;
  ok: boolean;
  details: unknown;
};

export type ExamDayReopeningScopeKind =
  | 'slot_status'
  | 'candidate_attendance'
  | 'member_attendance'
  | 'staffing'
  | 'absence'
  | 'exam_protocol'
  | 'exam_result';

export type ExamDayReopeningScope = {
  kind: ExamDayReopeningScopeKind;
  entity_id: number;
};

export type ExamDayClosure = {
  exam_day_id: number;
  revision: number;
  status: ExamDayClosureStatus;
  legacy_status: string | null;
  evaluation: {
    items: ExamDayClosureFinding[];
    warnings: Array<Record<string, unknown>>;
    regular_close_ready: boolean;
    exception_close_ready: boolean;
    exception_candidate: Record<string, unknown> | null;
    protocol_references: Array<Record<string, unknown>>;
    result_references: Array<Record<string, unknown>>;
  };
  active_reopening: Record<string, unknown> | null;
  history: Array<Record<string, unknown>>;
  tasks: Array<Record<string, unknown>>;
  permissions: { close: boolean; reopen: boolean; export: boolean };
  _links: Record<string, ApiLink>;
};

export type ExamDayReopeningImpact = {
  exam_day_id: number;
  revision: number;
  requested_scope: string[];
  expanded_scope: string[];
  impacts: Record<string, number[]>;
};

export type ExecutionStatus =
  'open' | 'running' | 'completed' | 'cancelled' | 'needs_follow_up' | string;

export type ExecutionStatusSummary = Record<
  'open' | 'running' | 'completed' | 'cancelled' | 'needs_follow_up',
  number
>;

export type AttendanceStatus = 'open' | 'present' | 'late' | 'absent';

export type Attendance = {
  status: AttendanceStatus | string;
  arrived_at: string | null;
};

export type ConfirmedPlan = ConfirmedPlanContext & {
  days: Array<{
    id: ConfirmedPlanDay['id'];
    date: ConfirmedPlanDay['date'];
    location: ConfirmedPlanDay['location'];
    slots: ConfirmedPlanDay['slots'];
    assignments: ConfirmedPlanDay['assignments'];
  }>;
};

export type ConfirmedPlanDayView = {
  plan: ConfirmedPlanContext;
  day: ConfirmedPlanDay;
  _links: Record<string, ApiLink>;
};

export type ExamProtocolDeclaration = 'without_special_occurrences' | 'with_special_occurrences';

export type ExamProtocolEntryCategory =
  | 'late_start'
  | 'interruption'
  | 'termination'
  | 'different_staffing'
  | 'procedural_deviation'
  | 'objection_or_reservation'
  | 'other';

export type ExamProtocolEntry = {
  id: number;
  category: ExamProtocolEntryCategory;
  statement: string;
  occurred_from: string;
  occurred_to: string | null;
  recorded_by_member_id: number;
  created_at: string;
};

export type ExamProtocolRevision = {
  id: number;
  version: number;
  declaration: ExamProtocolDeclaration | null;
  workflow_state: 'draft' | 'submitted' | 'correction_open' | string;
  change_reason: string | null;
  submitted_at: string | null;
  obsolete: boolean;
  missing_response_member_ids: number[];
  entries: ExamProtocolEntry[];
  responses: Array<{
    id: number;
    committee_member_id: number;
    response: 'confirmed' | 'reservation';
    entry_id: number | null;
    statement: string | null;
    responded_at: string;
  }>;
};

export type ExamProtocol = {
  id: number;
  exam_slot_id: number;
  day_revision?: number;
  current_version: number;
  state:
    | 'in_progress'
    | 'awaiting_confirmation'
    | 'fully_confirmed'
    | 'fully_with_reservation'
    | 'reaction_missing'
    | 'correction_open'
    | string;
  closing_ready: boolean;
  current_revision: ExamProtocolRevision;
  history: ExamProtocolRevision[];
  correction_requests: Array<{
    id: number;
    version: number;
    requested_by_member_id: number;
    reason: string;
    status: 'pending' | 'opened' | string;
    reopening_reference: string | null;
  }>;
  permissions: {
    edit: boolean;
    submit: boolean;
    respond: boolean;
    request_correction: boolean;
    coordinate_correction: boolean;
    manage_retention: boolean;
  };
  _links: Record<string, ApiLink>;
};

export type AssessmentCriterion = {
  key: string;
  label: string;
  raw_min: string;
  raw_max: string;
  weight: string;
};

export type AssessmentComponent = {
  key: string;
  label: string;
  mode: 'committee' | 'independent';
  weight: string;
  day_scoped: boolean;
  required_assessors: number;
  max_deviation: string;
  additional_assessor_on_deviation: boolean;
  criteria: AssessmentCriterion[];
};

export type AssessmentModelRules = {
  components: AssessmentComponent[];
  external_areas: Array<{
    key: string;
    label: string;
    weight: string;
    required: boolean;
  }>;
  rounding: {
    intermediate: { mode: 'none' | 'half_up'; digits: number | null };
    overall: { mode: 'none' | 'half_up'; digits: number | null };
    threshold_basis: 'unrounded' | 'rounded';
  };
  grades: Array<{ label: string; min_points: string }>;
  passing: {
    overall_min: string;
    component_minima: Record<string, string>;
    external_minima: Record<string, string>;
  };
  quorum: { minimum_members: number; majority: 'simple' };
};

export type ExamResult = {
  id: number;
  round_candidate_id: number;
  day_revisions?: Record<string, number>;
  version: number;
  state: 'incomplete' | 'calculation_ready' | 'determined' | 'communicated' | string;
  correction_open: boolean;
  legacy_status: string | null;
  candidate: {
    id: number;
    first_name: string;
    last_name: string;
    ihk_exam_number: string;
    specialization: string;
  };
  model_version: {
    id: number;
    model_key: string;
    version: number;
    ihk: string;
    occupation: string;
    specialization: string | null;
    valid_from: string;
    valid_until: string | null;
    rules: AssessmentModelRules;
    retention_rule_reference: string;
    retention_years: number;
  };
  participants: number[];
  disclosures: Array<{
    component_key: string;
    disclosed_by_member_id: number;
    disclosed_at: string;
  }>;
  individual_assessments: Array<{
    id: number;
    component_key: string;
    criterion_key: string;
    assessor_member_id: number;
    revision: number;
    raw_points: string;
    normalized_points: string;
    rationale: string | null;
    status: 'draft' | 'submitted' | 'withdrawn' | 'superseded';
    change_reason: string | null;
    submitted_at: string | null;
  }>;
  individual_assessment_counts: Array<{
    component_key: string;
    draft: number;
    submitted: number;
  }>;
  committee_assessments: Array<{
    id: number;
    component_key: string;
    revision: number;
    points: string;
    rationale: string | null;
    participant_member_ids: number[];
    vote: { yes: number[]; no: number[]; abstain: number[] };
    dissent: Array<{ member_id: number; statement: string }>;
    status: 'current' | 'superseded';
    determined_at: string;
  }>;
  external_results: Array<{
    id: number;
    area_key: string;
    revision: number;
    points: string;
    grade: string | null;
    professional_status: string;
    determining_authority: string;
    source_reference: string;
    status: 'unconfirmed' | 'confirmed' | 'replaced';
    recorded_by_member_id: number;
    confirmed_by_member_id: number | null;
    correction_reason: string | null;
  }>;
  current_calculation: null | {
    id: number;
    version: number;
    total_points: string;
    grade: string;
    passed: boolean;
    path: {
      inputs: Array<{ kind: string; key: string; points: string; weight: string }>;
      unrounded_total: string;
      rounded_total: string;
      threshold_basis: string;
    };
  };
  determinations: Array<{
    id: number;
    revision: number;
    participant_member_ids: number[];
    vote: { yes: number[]; no: number[]; abstain: number[] };
    dissent: Array<{ member_id: number; statement: string }>;
    status: 'current' | 'superseded';
    determined_at: string;
    confirmation_member_ids: number[];
  }>;
  current_determination: ExamResult['determinations'][number] | null;
  corrections: Array<{
    id: number;
    reason: string;
    status: 'open' | 'completed';
    reopening_reference: string | null;
  }>;
  communications: Array<{
    id: number;
    method: string;
    communicated_at: string;
    external_document_status: string | null;
    external_document_reference: string | null;
    status: 'current' | 'obsolete';
  }>;
  retention: null | {
    rule_reference: string;
    period_start: string | null;
    retain_until: string | null;
    legal_hold: boolean;
    hold_reason: string | null;
  };
  exports: Array<{
    id: number;
    result_determination_id: number | null;
    export_kind: 'machine' | 'human';
    status: 'draft' | 'determined' | 'superseded';
    generated_at: string;
  }>;
  permissions: {
    assess_own: boolean;
    disclose: boolean;
    determine_component: boolean;
    manage_external: boolean;
    determine_result: boolean;
    confirm_record: boolean;
    coordinate_correction: boolean;
    communicate: boolean;
    manage_retention: boolean;
  };
  _links: Record<string, ApiLink>;
};

export type RoundSummary = {
  round: {
    id: number;
    name: string;
    status: RoundStatus;
    committee_name: string;
  };
  counts: {
    candidates: number;
    mep_count: number;
    required_exam_slots: number;
  };
  settings: PlanningSettings | null;
  availability: AvailabilityCount[];
  _links: Record<string, ApiLink>;
};

export type ExamRound = {
  id: number;
  exam_half_year_id: number;
  name: string;
  committee_id: number;
  status: RoundStatus;
  availability_deadline: string | null;
  availability_reminder_at: string | null;
  created_at?: string;
  updated_at?: string;
  notification_warning?: string;
  _links?: Record<string, ApiLink>;
};

export type ExamHalfYear = {
  id: number;
  season: 'summer' | 'winter';
  year: number;
  status: 'draft' | 'active' | 'completed' | 'archived' | string;
  created_at?: string;
  updated_at?: string;
};

export type ExamRoundCreate = Pick<ExamRound, 'exam_half_year_id' | 'committee_id' | 'name'>;

export type ExamRoundUpdate = Pick<
  ExamRound,
  'name' | 'availability_deadline' | 'availability_reminder_at'
>;

export type AvailabilityRequest = ExamRoundUpdate;

/**
 * Current server-side planning state.
 *
 * The open ``string`` member deliberately keeps the UI forward-compatible with
 * newly introduced backend states; presentation code must provide a fallback.
 */
export type RoundStatus =
  'draft' | 'availability_requested' | 'plan_proposed' | 'plan_confirmed' | string;

export type PlanningSettings = {
  id?: number;
  exam_round_id?: number;
  calendar_week_from: string;
  calendar_week_to: string;
  exams_per_day: number;
  max_exam_days_per_week: number;
  lunch_break_enabled?: number;
  exclude_public_holidays?: number;
  holiday_subdivision_code?: string | null;
  default_location_id?: number | null;
  updated_by_member_id?: number;
};

export type AvailabilityCount = {
  availability: AvailabilityValue;
  count: number;
};

/**
 * A member's declared availability for one candidate day.
 *
 * As with round status, unknown future values are retained instead of being
 * coerced, so a user never silently overwrites a server-side state.
 */
export type AvailabilityValue =
  'full_day' | 'morning' | 'afternoon' | 'pending' | 'unavailable' | string;

/** Result of generating or confirming a proposal, including user-facing rule validation. */
export type PlanningResult = {
  status: RoundStatus;
  validation?: {
    passed: boolean;
    messages: string[];
  };
  conflicts?: PlanningConflict[];
  counts: Record<string, number>;
  notification_warning?: string;
  calendar_warning?: string;
  _links?: Record<string, ApiLink>;
};

/** A person-wide reservation that prevented an overlapping committee assignment. */
export type PlanningConflict = {
  date: string;
  day_part: 'morning' | 'afternoon' | string;
  reservation: 'confirmed' | 'proposed' | string;
  message: string;
};

/** One ordered slot inside the editable, revisioned planning aggregate. */
export type PlanningProposalSlot = {
  id: number | null;
  round_candidate_id: number;
  slot_type: 'regular' | 'mep';
  starts_at: string;
  ends_at: string;
  sequence_number: number;
  status: 'proposed';
};

/** One examiner or fallback assignment for a proposal day part. */
export type PlanningProposalAssignment = {
  id: number | null;
  committee_member_id: number;
  assignment_role: 'examiner' | 'fallback';
  day_part: 'morning' | 'afternoon' | 'full_day';
  fallback_status: string | null;
};

/** One candidate exam day and its complete editable proposal content. */
export type PlanningProposalDay = {
  id: number | null;
  candidate_exam_day_id: number;
  date: string;
  location_id: number;
  status: 'proposed';
  slots: PlanningProposalSlot[];
  assignments: PlanningProposalAssignment[];
};

/** Complete proposal exchanged through the optimistic-lock aggregate endpoint. */
export type EditablePlanningProposal = {
  round_id: number;
  revision: number;
  exam_days: PlanningProposalDay[];
  _links?: Record<string, ApiLink>;
};

/** Stable backend validation finding addressable by the editor. */
export type PlanningValidationViolation = {
  code: string;
  message: string;
  day_id: number | null;
  slot_id: number | null;
  member_id: number | null;
};

export type PlanningProblem = {
  error?: {
    code?: string;
    message?: string;
    violations?: PlanningValidationViolation[];
  };
};

export type ExamDay = {
  id: number;
  exam_round_id: number;
  location_id: number;
  date: string;
  status: 'proposed' | 'confirmed' | 'cancelled' | string;
  lunch_break_enabled: number;
};

export type ExamSlot = {
  id: number;
  exam_day_id: number;
  round_candidate_id: number;
  slot_type: 'regular' | 'mep' | string;
  starts_at: string;
  ends_at: string;
  sequence_number: number;
  status: 'proposed' | 'confirmed' | string;
};

export type ExamDayAssignment = {
  id: number;
  exam_day_id: number;
  committee_member_id: number;
  assignment_role: 'examiner' | 'fallback' | string;
  day_part: 'morning' | 'afternoon' | string;
  fallback_status: 'proposed' | 'confirmed' | null;
};

export type Committee = {
  id: number;
  name: string;
  occupation: string;
  ihk: string;
  created_at?: string;
  updated_at?: string;
};

/**
 * A membership in one committee, enriched with the globally stored person data.
 *
 * ``id`` is the membership identifier used by availability and assignment APIs;
 * ``person_id`` is used for conflict checks across committees.
 */
export type CommitteeMember = {
  id: number;
  person_id: number;
  committee_id: number;
  first_name: string;
  last_name: string;
  member_status: 'ordinary' | 'deputy' | string;
  committee_role: string;
  representing_side: string;
  email: string;
  email_verified_at: string | null;
  mobile: string | null;
  is_active: number;
};

export type Person = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  mobile: string | null;
};

export type Location = {
  id: number;
  committee_id?: number;
  name: string;
  street?: string;
  postal_code?: string;
  room: string;
  city: string;
  is_active?: number;
  created_at?: string;
  updated_at?: string;
};

export type Candidate = {
  id: number;
  first_name: string;
  last_name: string;
  ihk_exam_number: string;
  specialization: string;
  training_company: string;
  created_at?: string;
  updated_at?: string;
};

export type RoundCandidate = {
  id: number;
  exam_round_id: number;
  candidate_id: number;
  attempt_number: number;
  requires_mep: number;
  is_active: number;
  created_at?: string;
  updated_at?: string;
};

/** A time-bounded responsibility of a candidate within one exam half-year. */
export type CandidateCommitteeAssignment = {
  id: number;
  candidate_id: number;
  exam_half_year_id: number;
  exam_round_id: number;
  round_candidate_id: number;
  assigned_at: string;
  ended_at: string | null;
  change_reason: string | null;
  created_at?: string;
  updated_at?: string;
};

/** A global candidate enriched with the optional data of the active exam round. */
export type CandidateView = {
  candidate: Candidate;
  roundCandidate?: RoundCandidate;
};

export type CandidateExamDay = {
  id: number;
  exam_round_id: number;
  date: string;
  is_active: number;
};

export type CandidateDayGenerationResult = {
  round_id: number;
  calendar_week_from: string;
  calendar_week_to: string;
  exclude_public_holidays: number;
  holiday_subdivision_code: string | null;
  created_days: CandidateExamDay[];
  skipped_existing: string[];
  excluded_holidays: Array<{ date: string; name: string }>;
  counts: {
    calculated_weekdays: number;
    created: number;
    existing: number;
    excluded_holidays: number;
  };
  _links?: Record<string, ApiLink>;
};

export type MemberAvailability = {
  id: number;
  exam_round_id?: number;
  committee_member_id: number;
  candidate_exam_day_id: number;
  availability: AvailabilityValue;
  responded_at?: string | null;
};

export type PlanningDayView = {
  day: ExamDay;
  slots: ExamSlot[];
  assignments: ExamDayAssignment[];
  location?: Location;
};

/**
 * Client-side aggregate assembled from several API collections for planning views.
 *
 * Slots and assignments are grouped under their day to make the template avoid
 * repeated cross-collection joins.
 */
export type PlanningBoard = {
  days: PlanningDayView[];
  members: CommitteeMember[];
  candidates: CandidateView[];
  candidateDays: CandidateExamDay[];
  availabilities: MemberAvailability[];
  locations: Location[];
};

export type MasterData = {
  committees: Committee[];
  examHalfYears: ExamHalfYear[];
  persons: Person[];
  members: CommitteeMember[];
  candidates: CandidateView[];
  examRounds: ExamRound[];
  candidateAssignments: CandidateCommitteeAssignment[];
  locations: Location[];
};
