import type { ApiLink } from './common.models';
import type { CandidateView, CommitteeMember, Location } from './master-data.models';

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
  revision?: number;
  lifecycle_status?: ExamRoundLifecycleStatus;
  legacy_status?: string | null;
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
  status: 'draft' | 'active' | 'archived' | string;
  legacy_status?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type ExamRoundCreate = Pick<ExamRound, 'committee_id' | 'name'> &
  (
    | { exam_half_year_id: number; season?: never; year?: never }
    | { exam_half_year_id?: never; season: ExamHalfYear['season']; year: number }
  );

export type ExamRoundLifecycleStatus = 'open' | 'closed' | 'cancelled' | 'reopening' | 'historical';

export type ExamRoundLifecycleFinding = {
  code: string;
  label: string;
  ok: boolean;
  details: unknown;
};

export type ExamRoundLifecycle = {
  round_id: number;
  revision: number;
  status: ExamRoundLifecycleStatus;
  legacy_status: string | null;
  historical_without_formal_evidence: boolean;
  evaluation: { ready: boolean; items: ExamRoundLifecycleFinding[] };
  candidates: Array<{
    round_candidate_id: number;
    candidate_id: number;
    terminal_status: RoundCandidateTerminalStatus;
    terminal_reason: string | null;
    effective_new_round_id: number | null;
    postponed_until: string | null;
    ihk_decision_reference: string | null;
    terminal_at: string | null;
  }>;
  current_decision: Record<string, unknown> | null;
  decisions: Array<Record<string, unknown>>;
  reopenings: Array<Record<string, unknown>>;
  history: Array<{
    id: number;
    round_revision: number;
    event_type: string;
    reason: string | null;
    created_at: string;
  }>;
  tasks: Array<Record<string, unknown>>;
  exports: Array<{
    id: number;
    export_kind: 'machine' | 'human';
    round_revision: number;
    generated_at: string;
    obsolete: boolean;
  }>;
  ihk_statuses: Array<{
    id: number;
    exam_result_id: number;
    document_status: string;
    document_reference: string;
    recorded_by_member_id: number;
    recorded_at: string;
  }>;
  retention: {
    retain_until: string | null;
    legal_hold: boolean;
    sources: Array<{
      kind: 'protocol' | 'result';
      id: number;
      retain_until: string | null;
      legal_hold: boolean;
      hold_reason: string | null;
    }>;
  };
  permissions: {
    close: boolean;
    cancel: boolean;
    reopen: boolean;
    delete: boolean;
    export: boolean;
  };
  _links: Record<string, ApiLink>;
};

export type RoundCandidateTerminalStatus =
  'open' | 'result_communicated' | 'transferred' | 'postponed' | 'ihk_terminated';

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
  status: 'proposed' | 'confirmed' | string;
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
  room_id?: number;
  location_id: number;
  status: 'proposed' | 'confirmed' | 'completed' | 'cancelled' | string;
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

/** One immutable audit entry created by a confirmed-plan change. */
export type ConfirmedPlanRevision = {
  id: number;
  previous_revision: number;
  resulting_revision: number;
  reason: string;
  actor_member_id: number;
  created_at: string;
  before: EditablePlanningProposal;
  after: EditablePlanningProposal;
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
