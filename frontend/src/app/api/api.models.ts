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
  name: string;
  committee_id: number;
  status: RoundStatus;
  availability_deadline: string | null;
  availability_reminder_at: string | null;
  created_at?: string;
  updated_at?: string;
  _links?: Record<string, ApiLink>;
};

export type RoundStatus =
  | 'draft'
  | 'availability_requested'
  | 'plan_proposed'
  | 'plan_confirmed'
  | string;

export type PlanningSettings = {
  id?: number;
  exam_round_id?: number;
  calendar_week_from: string;
  calendar_week_to: string;
  exams_per_day: number;
  max_exam_days_per_week: number;
  lunch_break_enabled?: number;
  default_location_id?: number | null;
  updated_by_member_id?: number;
};

export type AvailabilityCount = {
  availability: AvailabilityValue;
  count: number;
};

export type AvailabilityValue =
  | 'full_day'
  | 'morning'
  | 'afternoon'
  | 'pending'
  | 'unavailable'
  | string;

export type PlanningResult = {
  status: RoundStatus;
  validation?: {
    passed: boolean;
    messages: string[];
  };
  counts: Record<string, number>;
  _links?: Record<string, ApiLink>;
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

export type CommitteeMember = {
  id: number;
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
  created_at?: string;
  updated_at?: string;
};

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
  members: CommitteeMember[];
  candidates: CandidateView[];
  locations: Location[];
};
