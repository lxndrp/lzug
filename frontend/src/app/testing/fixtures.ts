import {
  ApiRoot,
  Candidate,
  CandidateExamDay,
  CandidateView,
  Committee,
  CommitteeMember,
  ExamDay,
  ExamDayAssignment,
  ExamRound,
  ExamSlot,
  Location,
  MasterData,
  MemberAvailability,
  PlanningBoard,
  RoundCandidate,
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
  {
    id: 1,
    committee_id: 1,
    name: 'Bildungszentrum HafenCity',
    street: 'Prüfungsweg 1',
    postal_code: '20457',
    room: '3.12',
    city: 'Hamburg',
    is_active: 1,
  },
];

export const candidatesFixture: Candidate[] = [
  {
    id: 1,
    first_name: 'Lea',
    last_name: 'Hoffmann',
    ihk_exam_number: 'FI-2026-1042',
    specialization: 'Anwendungsentwicklung',
    training_company: 'Nordlicht Digital GmbH',
  },
  {
    id: 2,
    first_name: 'Jonas',
    last_name: 'Weber',
    ihk_exam_number: 'FI-2026-1057',
    specialization: 'Systemintegration',
    training_company: 'HanseNet Solutions AG',
  },
];

export const roundCandidatesFixture: RoundCandidate[] = [
  {
    id: 1,
    exam_round_id: 1,
    candidate_id: 1,
    attempt_number: 1,
    requires_mep: 0,
  },
  {
    id: 2,
    exam_round_id: 1,
    candidate_id: 2,
    attempt_number: 2,
    requires_mep: 1,
  },
];

export const candidateViewsFixture: CandidateView[] = candidatesFixture.map((candidate) => ({
  candidate,
  roundCandidate: roundCandidatesFixture.find((item) => item.candidate_id === candidate.id),
}));

export const candidateDaysFixture: CandidateExamDay[] = [
  { id: 1, exam_round_id: 1, date: '2026-11-16', is_active: 1 },
  { id: 2, exam_round_id: 1, date: '2026-11-17', is_active: 0 },
];

export const examRoundFixture: ExamRound = {
  id: 1,
  name: 'Winter 2026/27',
  committee_id: 1,
  status: 'availability_requested',
  availability_deadline: '2026-10-15 18:00:00',
  availability_reminder_at: '2026-10-08 09:00:00',
};

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
    exclude_public_holidays: 0,
    holiday_subdivision_code: null,
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
  candidates: candidateViewsFixture,
  locations: locationsFixture,
};

export const planningBoardFixture: PlanningBoard = {
  members: membersFixture,
  locations: locationsFixture,
  candidates: candidateViewsFixture,
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
