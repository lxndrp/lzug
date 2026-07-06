import {
  ApiRoot,
  CandidateExamDay,
  Committee,
  CommitteeMember,
  ExamDay,
  ExamDayAssignment,
  ExamSlot,
  Location,
  MasterData,
  MemberAvailability,
  PlanningBoard,
  RoundSummary,
} from '../api/api.models';

export const apiRootFixture: ApiRoot = {
  name: 'lzug API',
  _links: {},
};

export const committeesFixture: Committee[] = [
  { id: 1, name: 'PA Fachinformatiker Hamburg 1', occupation: 'Fachinformatiker/in' },
  { id: 2, name: 'PA Fachinformatiker Hamburg 2', occupation: 'Fachinformatiker/in' },
];

export const membersFixture: CommitteeMember[] = [
  {
    id: 1,
    committee_id: 1,
    first_name: 'Martin',
    last_name: 'Koenig',
    member_status: 'ordinary',
    committee_role: 'chair',
    representing_side: 'employer',
    email: 'martin.koenig@example.de',
    email_verified_at: null,
    mobile: '+49 170 1234567',
    is_active: 1,
  },
  {
    id: 2,
    committee_id: 1,
    first_name: 'Anne',
    last_name: 'Berg',
    member_status: 'ordinary',
    committee_role: 'member',
    representing_side: 'school',
    email: 'anne.berg@example.de',
    email_verified_at: null,
    mobile: null,
    is_active: 0,
  },
  {
    id: 3,
    committee_id: 2,
    first_name: 'Tobias',
    last_name: 'Rehm',
    member_status: 'deputy',
    committee_role: 'member',
    representing_side: 'employee',
    email: 'tobias.rehm@example.de',
    email_verified_at: null,
    mobile: null,
    is_active: 1,
  },
];

export const locationsFixture: Location[] = [
  { id: 1, name: 'Bildungszentrum HafenCity', room: '3.12', city: 'Hamburg' },
];

export const candidateDaysFixture: CandidateExamDay[] = [
  { id: 1, exam_round_id: 1, date: '2026-11-16', is_active: 1 },
  { id: 2, exam_round_id: 1, date: '2026-11-17', is_active: 0 },
];

export const availabilitiesFixture: MemberAvailability[] = [
  { id: 1, committee_member_id: 1, candidate_exam_day_id: 1, availability: 'full_day' },
  { id: 2, committee_member_id: 2, candidate_exam_day_id: 1, availability: 'pending' },
];

export const examDaysFixture: ExamDay[] = [
  {
    id: 2,
    exam_round_id: 1,
    location_id: 1,
    date: '2026-11-17',
    status: 'proposed',
    lunch_break_enabled: 1,
  },
  {
    id: 1,
    exam_round_id: 1,
    location_id: 1,
    date: '2026-11-16',
    status: 'proposed',
    lunch_break_enabled: 1,
  },
];

export const examSlotsFixture: ExamSlot[] = [
  {
    id: 2,
    exam_day_id: 1,
    round_candidate_id: 2,
    slot_type: 'mep',
    starts_at: '2026-11-16 09:30:00',
    ends_at: '2026-11-16 10:30:00',
    sequence_number: 2,
    status: 'proposed',
  },
  {
    id: 1,
    exam_day_id: 1,
    round_candidate_id: 1,
    slot_type: 'regular',
    starts_at: '2026-11-16 08:30:00',
    ends_at: '2026-11-16 09:30:00',
    sequence_number: 1,
    status: 'proposed',
  },
];

export const assignmentsFixture: ExamDayAssignment[] = [
  {
    id: 1,
    exam_day_id: 1,
    committee_member_id: 1,
    assignment_role: 'examiner',
    day_part: 'morning',
    fallback_status: null,
  },
  {
    id: 2,
    exam_day_id: 1,
    committee_member_id: 2,
    assignment_role: 'fallback',
    day_part: 'morning',
    fallback_status: 'proposed',
  },
];

export const summaryFixture: RoundSummary = {
  round: {
    id: 1,
    name: 'Winter 2026/27',
    status: 'availability_requested',
    committee_name: 'PA Fachinformatiker Hamburg 1',
  },
  counts: {
    candidates: 12,
    mep_count: 4,
    required_exam_slots: 16,
  },
  settings: {
    calendar_week_from: '2026-W47',
    calendar_week_to: '2026-W49',
    exams_per_day: 6,
    max_exam_days_per_week: 3,
  },
  availability: [
    { availability: 'full_day', count: 8 },
    { availability: 'pending', count: 2 },
  ],
  _links: {},
};

export const masterDataFixture: MasterData = {
  committees: committeesFixture,
  members: membersFixture,
};

export const planningBoardFixture: PlanningBoard = {
  members: membersFixture,
  locations: locationsFixture,
  candidateDays: candidateDaysFixture,
  availabilities: availabilitiesFixture,
  days: [
    {
      day: examDaysFixture[1],
      location: locationsFixture[0],
      slots: [examSlotsFixture[1], examSlotsFixture[0]],
      assignments: assignmentsFixture,
    },
  ],
};
