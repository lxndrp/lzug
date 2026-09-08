import type { ApiLink } from './common.models';
import type { ExamHalfYear, RoundStatus } from './planning.models';

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
  days: Array<Omit<ConfirmedPlanDay, 'closure'>>;
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
