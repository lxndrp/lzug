/** A HAL-like link. The optional method describes an allowed state transition. */
export type ApiLink = {
  href: string;
  method?: string;
};

export type ApiRoot = {
  name: string;
  _links: Record<string, ApiLink>;
};

export type ApiCollection<T> = {
  items: T[];
  _links: Record<string, ApiLink>;
};

export type SchedulingStatusGroup = 'open' | 'coordination' | 'confirmed';

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

export type ConfirmedPlan = {
  id: number;
  name: string;
  committee: { id: number; name: string };
  exam_half_year: ExamHalfYear;
  days: Array<{
    id: number;
    date: string;
    location: { id: number; name: string; room: string; city: string } | null;
    slots: Array<{
      id: number;
      starts_at: string;
      ends_at: string;
      sequence_number: number;
      slot_type: 'regular' | 'mep' | string;
      candidate: { id: number; first_name: string; last_name: string; ihk_exam_number: string };
    }>;
    assignments: Array<{
      id: number;
      assignment_role: 'examiner' | 'fallback' | string;
      day_part: 'morning' | 'afternoon' | 'full_day' | string;
      fallback_status: 'confirmed' | null | string;
      member: { id: number; first_name: string; last_name: string; representing_side: string };
    }>;
  }>;
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

export type ExamRoundCreate = Pick<ExamRound, 'exam_half_year_id' | 'committee_id' | 'name'> & {
  created_by_member_id: number;
};

export type ExamRoundUpdate = Pick<
  ExamRound,
  'name' | 'availability_deadline' | 'availability_reminder_at'
>;

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
  _links?: Record<string, ApiLink>;
};

/** A person-wide reservation that prevented an overlapping committee assignment. */
export type PlanningConflict = {
  date: string;
  day_part: 'morning' | 'afternoon' | string;
  reservation: 'confirmed' | 'proposed' | string;
  message: string;
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
  persons: Person[];
  members: CommitteeMember[];
  candidates: CandidateView[];
  examRounds: ExamRound[];
  candidateAssignments: CandidateCommitteeAssignment[];
  locations: Location[];
};
