import {
  ApiRoot,
  Candidate,
  CandidateCommitteeAssignment,
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
  Person,
  RoundCandidate,
  RoundSummary,
} from '../api/api.models';
import { syntheticFixtures } from './synthetic-fixtures.generated';

function fixtureId(group: keyof typeof syntheticFixtures.keys, key: string): number {
  const id = (syntheticFixtures.keys[group] as Record<string, number>)[key];
  if (id === undefined) {
    throw new Error(`Unknown synthetic fixture key: ${key}`);
  }
  return id;
}

function fixtureById<T extends { id: number }>(items: T[], id: number): T {
  const item = items.find((candidate) => candidate.id === id);
  if (!item) {
    throw new Error(`Unknown synthetic fixture id: ${id}`);
  }
  return item;
}

export const apiRootFixture: ApiRoot = {
  name: 'lzug API',
  version: '0.1.0',
  _links: {},
};

export const committeesFixture: Committee[] = syntheticFixtures.committees.map((item) => ({
  ...item,
}));

export const membersFixture: CommitteeMember[] = syntheticFixtures.members.map((item) => ({
  ...item,
}));

export const personsFixture: Person[] = syntheticFixtures.members.map(
  ({ person_id, first_name, last_name, email, mobile }) => ({
    id: person_id,
    first_name,
    last_name,
    email,
    mobile,
  }),
);

export const locationsFixture: Location[] = syntheticFixtures.locations.map((item) => ({
  ...item,
}));

export const candidatesFixture: Candidate[] = syntheticFixtures.candidates.map((item) => ({
  ...item,
}));

export const athenCommitteeFixture = fixtureById(
  committeesFixture,
  fixtureId('committees', 'name.papaspyrou.repertoire.lzug.fixture.committee.athen'),
);
export const feenwaldCommitteeFixture = fixtureById(
  committeesFixture,
  fixtureId('committees', 'name.papaspyrou.repertoire.lzug.fixture.committee.feenwald'),
);
export const athenChairMembershipFixture = fixtureById(
  membersFixture,
  fixtureId('memberships', 'name.papaspyrou.repertoire.lzug.fixture.membership.chair.athen'),
);
export const athenDeputyMembershipFixture = fixtureById(
  membersFixture,
  fixtureId('memberships', 'name.papaspyrou.repertoire.lzug.fixture.membership.deputy.athen'),
);
export const athenCourtLocationFixture = fixtureById(
  locationsFixture,
  fixtureId('locations', 'name.papaspyrou.repertoire.lzug.fixture.location.synthetic.court'),
);
export const planchangeCandidateFixture = fixtureById(
  candidatesFixture,
  fixtureId('candidates', 'name.papaspyrou.repertoire.lzug.fixture.candidate.planchange'),
);
export const absenceCandidateFixture = fixtureById(
  candidatesFixture,
  fixtureId('candidates', 'name.papaspyrou.repertoire.lzug.fixture.candidate.absence'),
);
export const feenwaldLocationFixture = fixtureById(
  locationsFixture,
  fixtureId('locations', 'name.papaspyrou.repertoire.lzug.fixture.location.synthetic.feenwald'),
);

export const roundCandidatesFixture: RoundCandidate[] = [
  {
    id: 1,
    exam_round_id: 1,
    candidate_id: 1,
    attempt_number: 1,
    requires_mep: 0,
    is_active: 1,
  },
  {
    id: 2,
    exam_round_id: 1,
    candidate_id: 2,
    attempt_number: 2,
    requires_mep: 1,
    is_active: 1,
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
export const inactiveCandidateDayFixture = fixtureById(candidateDaysFixture, 2);

export const examRoundFixture: ExamRound = {
  id: 1,
  exam_half_year_id: 1,
  name: 'Winter 2026/27',
  committee_id: 1,
  status: 'availability_requested',
  availability_deadline: '2026-10-15 18:00:00',
  availability_reminder_at: '2026-10-08 09:00:00',
};

export const examRoundsFixture: ExamRound[] = [
  examRoundFixture,
  {
    id: 2,
    exam_half_year_id: 1,
    name: 'Winter 2026/27',
    committee_id: 2,
    status: 'draft',
    availability_deadline: null,
    availability_reminder_at: null,
  },
];
export const foreignExamRoundFixture = fixtureById(examRoundsFixture, 2);

export const candidateAssignmentsFixture: CandidateCommitteeAssignment[] = [
  {
    id: 1,
    candidate_id: 1,
    exam_half_year_id: 1,
    exam_round_id: 1,
    round_candidate_id: 1,
    assigned_at: '2026-07-01 09:00:00',
    ended_at: null,
    change_reason: null,
  },
  {
    id: 2,
    candidate_id: 2,
    exam_half_year_id: 1,
    exam_round_id: 2,
    round_candidate_id: 2,
    assigned_at: '2026-06-15 09:00:00',
    ended_at: '2026-07-01 09:00:00',
    change_reason: 'Ausschusswechsel',
  },
  {
    id: 3,
    candidate_id: 2,
    exam_half_year_id: 1,
    exam_round_id: 1,
    round_candidate_id: 2,
    assigned_at: '2026-07-01 09:00:00',
    ended_at: null,
    change_reason: null,
  },
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
const primaryExamDayFixture = fixtureById(examDaysFixture, 1);

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
const mepExamSlotFixture = fixtureById(examSlotsFixture, 2);
const regularExamSlotFixture = fixtureById(examSlotsFixture, 1);

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
    committee_name: athenCommitteeFixture.name,
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
  examHalfYears: [{ id: 1, season: 'winter', year: 2026, status: 'active' }],
  persons: personsFixture,
  members: membersFixture,
  candidates: candidateViewsFixture,
  examRounds: examRoundsFixture,
  candidateAssignments: candidateAssignmentsFixture,
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
      day: primaryExamDayFixture,
      location: athenCourtLocationFixture,
      slots: [regularExamSlotFixture, mepExamSlotFixture],
      assignments: assignmentsFixture,
    },
  ],
};
