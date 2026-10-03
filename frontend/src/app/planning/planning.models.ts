/** Feature-owned models used by planning views and commands. */
export type PlanningRound = {
  id: number;
  exam_half_year_id: number;
  name: string;
  committee_id: number;
  status: PlanningRoundStatus;
  revision?: number;
  lifecycle_status?: string;
  legacy_status?: string | null;
  availability_deadline: string | null;
  availability_reminder_at: string | null;
  updated_at?: string;
  notification_warning?: string;
};

export type PlanningRoundStatus =
  'draft' | 'availability_requested' | 'plan_proposed' | 'plan_confirmed' | string;

export type PlanningRoundUpdate = Pick<
  PlanningRound,
  'name' | 'availability_deadline' | 'availability_reminder_at'
>;

export type AvailabilityRequest = PlanningRoundUpdate;

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

export type PlanningSummary = {
  round: {
    id: number;
    name: string;
    status: PlanningRoundStatus;
    committee_name: string;
  };
  counts: {
    candidates: number;
    mep_count: number;
    required_exam_slots: number;
  };
  settings: PlanningSettings | null;
  availability: Array<{ availability: AvailabilityValue; count: number }>;
};

export type AvailabilityValue =
  'full_day' | 'morning' | 'afternoon' | 'pending' | 'unavailable' | string;

export type PlanningCandidate = {
  id: number;
  first_name: string;
  last_name: string;
  ihk_exam_number: string;
  specialization: string;
  training_company: string;
  created_at?: string;
  updated_at?: string;
};

export type PlanningCandidateView = {
  candidate: PlanningCandidate;
  roundCandidate?: {
    id: number;
    candidate_id: number;
    exam_round_id: number;
    attempt_number: number;
    requires_mep: number;
    is_active: number;
    terminal_status?: string;
    terminal_reason?: string | null;
    effective_new_round_id?: number | null;
    postponed_until?: string | null;
    ihk_decision_reference?: string | null;
    terminal_at?: string | null;
    created_at?: string;
    updated_at?: string;
  };
};

export type PlanningMember = {
  id: number;
  person_id: number;
  committee_id: number;
  first_name: string;
  last_name: string;
  member_status: string;
  committee_role: string;
  representing_side: string;
  email: string;
  email_verified_at: string | null;
  mobile: string | null;
  is_active: number;
};

export type PlanningLocation = {
  id: number;
  committee_id?: number | null;
  name: string;
  street?: string;
  postal_code?: string;
  room: string;
  city: string;
  is_active?: number;
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
};

export type PlanningMemberAvailability = {
  id: number;
  exam_round_id?: number;
  committee_member_id: number;
  candidate_exam_day_id: number;
  availability: AvailabilityValue;
  responded_at?: string | null;
};

export type PlanningDay = {
  id: number;
  exam_round_id: number;
  location_id: number;
  date: string;
  status: string;
  lunch_break_enabled: number;
};

export type PlanningSlot = {
  id: number;
  exam_day_id: number;
  round_candidate_id: number;
  slot_type: string;
  starts_at: string;
  ends_at: string;
  sequence_number: number;
  status: string;
};

export type PlanningAssignment = {
  id: number;
  exam_day_id: number;
  committee_member_id: number;
  assignment_role: string;
  day_part: 'morning' | 'afternoon' | string;
  fallback_status: 'proposed' | 'confirmed' | null;
};

export type PlanningDayView = {
  day: PlanningDay;
  slots: PlanningSlot[];
  assignments: PlanningAssignment[];
  location?: PlanningLocation;
};

export type PlanningBoard = {
  days: PlanningDayView[];
  members: PlanningMember[];
  candidates: PlanningCandidateView[];
  candidateDays: CandidateExamDay[];
  availabilities: PlanningMemberAvailability[];
  locations: PlanningLocation[];
};

export type PlanningConflict = {
  date: string;
  day_part: 'morning' | 'afternoon' | string;
  reservation: 'confirmed' | 'proposed' | string;
  message: string;
};

export type PlanningResult = {
  status: PlanningRoundStatus;
  validation?: { passed: boolean; messages: string[] };
  conflicts?: PlanningConflict[];
  counts: Record<string, number>;
  notification_warning?: string;
  calendar_warning?: string;
};

export type PlanningProposalSlot = {
  round_candidate_id: number;
  id: number | null;
  slot_type: 'regular' | 'mep';
  starts_at: string;
  ends_at: string;
  sequence_number: number;
  status: 'proposed' | 'confirmed' | string;
};

export type PlanningProposalAssignment = {
  committee_member_id: number;
  id: number | null;
  assignment_role: 'examiner' | 'fallback';
  day_part: 'morning' | 'afternoon' | 'full_day';
  fallback_status: string | null;
};

export type PlanningProposalDay = {
  candidate_exam_day_id: number;
  id: number | null;
  date: string;
  room_id?: number;
  location_id: number;
  status: 'proposed' | 'confirmed' | 'completed' | 'cancelled' | string;
  slots: PlanningProposalSlot[];
  assignments: PlanningProposalAssignment[];
};

/** Revisioned planning aggregate; `revision` is the optimistic-lock token. */
export type EditablePlanningProposal = {
  round_id: number;
  revision: number;
  exam_days: PlanningProposalDay[];
};

export type PlanningValidationViolation = {
  code: string;
  message: string;
  day_id: number | null;
  slot_id: number | null;
  member_id: number | null;
};

export type PlanningSnapshot = {
  round: PlanningRound;
  summary: PlanningSummary;
  board: PlanningBoard;
};
