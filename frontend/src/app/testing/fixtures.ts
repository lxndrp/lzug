import fixtureData from '../../../../fixtures/synthetic-fixtures.json';
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
  ExamVenue,
  Location,
  MasterData,
  MemberAvailability,
  PlanningBoard,
  Person,
  RoundCandidate,
  RoundSummary,
} from '../api/api.models';

// The JSON catalog is deliberately validated by the owning Python component;
// this adapter only maps its stable, component-facing fields.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type FixtureRow = Record<string, any>;
type FixtureGroup =
  | 'organizations'
  | 'committees'
  | 'persons'
  | 'memberships'
  | 'accounts'
  | 'locations'
  | 'rooms'
  | 'location_contacts'
  | 'candidates';

const fixtureGroups: FixtureGroup[] = [
  'organizations',
  'committees',
  'persons',
  'memberships',
  'accounts',
  'locations',
  'rooms',
  'location_contacts',
  'candidates',
];

function records(group: FixtureGroup): readonly FixtureRow[] {
  return fixtureData[group] as readonly FixtureRow[];
}

function fixtureByKey(group: FixtureGroup, key: string): FixtureRow {
  const row = records(group).find((candidate) => candidate['fixture_key'] === key);
  if (!row) {
    throw new Error(`Unknown synthetic fixture key: ${key}`);
  }
  return row;
}

function adapterRows(group: FixtureGroup): readonly FixtureRow[] {
  return records(group).filter((row) => row['adapters']?.includes('frontend'));
}

const specializationLabels: Record<string, string> = {
  application_development: 'Anwendungsentwicklung',
  system_integration: 'Systemintegration',
  data_and_process_analysis: 'Daten- und Prozessanalyse',
  digital_networking: 'Digitale Vernetzung',
};

const frontendRooms = adapterRows('rooms');
const syntheticFixtures = {
  version: fixtureData.version,
  revision: fixtureData.revision,
  fixtureRoot: fixtureData.fixture_root,
  demoMatrixVersion: fixtureData.demo_matrix_version,
  keys: Object.fromEntries(
    fixtureGroups.map((group) => [
      group,
      Object.fromEntries(
        records(group)
          .filter((row) => row['id'] !== undefined)
          .map((row) => [row['fixture_key'], row['id']]),
      ),
    ]),
  ),
  demoRoles: Object.fromEntries(
    fixtureData.accounts
      .filter((account) => account.demo_role)
      .map((account) => {
        const person = fixtureByKey('persons', account.person_key);
        const membership = fixtureByKey('memberships', account.membership_key);
        return [
          account.demo_role,
          {
            account_id: account.id,
            person_id: person['id'],
            committee_member_id: membership['id'],
            first_name: person['first_name'],
            last_name: person['last_name'],
            display_name: `${person['first_name']} ${person['last_name']}`,
            account_email: account.email,
            person_email: person['email'],
            fixture_key: person['fixture_key'],
          },
        ];
      }),
  ),
  committees: adapterRows('committees').map((row) => ({
    id: row['id'],
    name: row['name'],
    occupation: row['occupation'],
    ihk: fixtureByKey('organizations', row['organization_key'])['name'],
    is_active: 1,
    bootstrap_state: 'ready' as const,
  })),
  members: records('memberships')
    .filter((row) => row['adapters']?.includes('frontend'))
    .map((row) => {
      const person = fixtureByKey('persons', row['person_key']);
      const committee = fixtureByKey('committees', row['committee_key']);
      return {
        id: row['id'],
        person_id: person['id'],
        committee_id: committee['id'],
        first_name: person['first_name'],
        last_name: person['last_name'],
        email: person['email'],
        mobile: person['mobile'],
        member_status: row['member_status'],
        committee_role: row['committee_role'],
        representing_side: row['representing_side'],
        is_active: row['is_active'],
        email_verified_at: null,
      };
    }),
  locations: frontendRooms.map((room) => {
    const venue = fixtureByKey('locations', room['venue_key']);
    const committee = venue['committee_key']
      ? fixtureByKey('committees', venue['committee_key'])['id']
      : null;
    return {
      id: room['id'],
      committee_id: committee,
      name: venue['name'],
      street: venue['street'],
      postal_code: venue['postal_code'],
      city: venue['city'],
      room: room['name'],
      is_active: Number(Boolean(venue['is_active']) && Boolean(room['is_active'])),
    };
  }),
  examVenues: adapterRows('locations').map((venue) => {
    const venueRooms = frontendRooms.filter((room) => room['venue_key'] === venue['fixture_key']);
    const venueContacts = adapterRows('location_contacts').filter(
      (contact) => contact['venue_key'] === venue['fixture_key'],
    );
    return {
      id: venue['id'],
      scope: venue['scope'],
      committee_id: venue['committee_key']
        ? fixtureByKey('committees', venue['committee_key'])['id']
        : null,
      ...Object.fromEntries(
        [
          'name',
          'street',
          'postal_code',
          'city',
          'country',
          'site_name',
          'entrance',
          'travel_directions',
          'is_accessible',
          'accessibility_status',
          'accessibility_notes',
          'latitude',
          'longitude',
          'coordinate_status',
          'coordinate_source',
          'is_active',
        ].map((field) => [field, venue[field]]),
      ),
      revision: 1,
      rooms: venueRooms.map((room) => ({
        id: room['id'],
        venue_id: venue['id'],
        name: room['name'],
        building: null,
        wing: null,
        floor: null,
        room_number: null,
        access_notes: room['access_notes'],
        capacity: room['capacity'],
        is_active: room['is_active'],
        revision: 1,
        _links: {},
      })),
      contacts: venueContacts.map((contact) => ({
        id: contact['id'],
        venue_id: venue['id'],
        label: contact['label'],
        role: contact['role'],
        phone: contact['phone'],
        email: contact['email'],
        availability_notes: contact['availability_notes'],
        is_active: contact['is_active'],
        revision: 1,
        room_ids: contact['room_keys'].map((key: string) => fixtureByKey('rooms', key)['id']),
        _links: {},
      })),
      map_provider: {
        mode: 'osm',
        attribution: '© OpenStreetMap-Mitwirkende',
        attribution_url: 'https://www.openstreetmap.org/copyright',
      },
      capabilities: { manage: false, request_promotion: false, decide_promotion: false },
      _links: {},
    };
  }) as ExamVenue[],
  candidates: adapterRows('candidates').map((row) => ({
    id: row['id'],
    first_name: row['first_name'],
    last_name: row['last_name'],
    ihk_exam_number: row['ihk_exam_number'],
    specialization: specializationLabels[row['specialization']],
    training_company: row['training_company'],
  })),
};

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
  fixtureId('rooms', 'name.papaspyrou.repertoire.lzug.fixture.room.zappeion.theseus'),
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
  fixtureId('rooms', 'name.papaspyrou.repertoire.lzug.fixture.room.nationalgarden.oberon'),
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
  examVenues: [
    {
      ...syntheticFixtures.examVenues[0],
      scope: 'committee',
      committee_id: 1,
      revision: 2,
      rooms: syntheticFixtures.examVenues[0].rooms.slice(0, 1).map((room) => ({ ...room })),
      contacts: syntheticFixtures.examVenues[0].contacts.map((contact) => ({
        ...contact,
        room_ids: [...contact.room_ids],
      })),
      capabilities: { manage: true, request_promotion: true, decide_promotion: false },
    },
  ] satisfies ExamVenue[],
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
