import type { ApiLink } from './common.models';
import type { ExamHalfYear, ExamRound, RoundCandidateTerminalStatus } from './planning.models';

export type Committee = {
  id: number;
  name: string;
  occupation: string;
  ihk: string;
  is_active: number;
  bootstrap_state: 'ready' | 'needs_clarification' | 'conflict';
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
  committee_id?: number | null;
  name: string;
  street?: string;
  postal_code?: string;
  room: string;
  city: string;
  is_active?: number;
  created_at?: string;
  updated_at?: string;
};

export type ExamRoom = {
  id: number;
  venue_id: number;
  name: string;
  building: string | null;
  wing: string | null;
  floor: string | null;
  room_number: string | null;
  access_notes: string | null;
  capacity: number | null;
  is_active: number;
  revision: number;
  consequence_warning?: string;
  _links: Record<string, ApiLink>;
};

export type VenueChangeImpact = {
  count: number;
  date_from: string | null;
  date_to: string | null;
  requires_confirmation: boolean;
  calendar: { event_count: number; fields: string[] };
  notifications: { recipient_count: number; fields: string[] };
};

export type VenueConsequenceProblem = {
  audit_id: number;
  venue_id: number;
  entity_type: 'venue' | 'room';
  entity_id: number;
  consequence_type: 'calendar' | 'notification' | 'derivation';
  status: 'temporarily_failed' | 'permanently_failed';
  attempt_count: number;
  error_code: string | null;
  updated_at: string;
};

export type ExamVenueContact = {
  id: number;
  venue_id: number;
  label: string;
  role: string | null;
  phone: string | null;
  email: string | null;
  availability_notes: string | null;
  is_active: number;
  revision: number;
  room_ids: number[];
  _links: Record<string, ApiLink>;
};

export type ExamVenue = {
  id: number;
  scope: 'global' | 'committee';
  committee_id: number | null;
  name: string;
  street: string;
  postal_code: string;
  city: string;
  country: string;
  site_name: string | null;
  entrance: string | null;
  travel_directions: string | null;
  is_accessible: number | null;
  accessibility_status: 'confirmed' | 'needs_clarification';
  accessibility_notes: string | null;
  latitude?: number | null;
  longitude?: number | null;
  coordinate_status?: 'missing' | 'needs_review' | 'confirmed';
  coordinate_source?: string | null;
  is_active: number;
  revision: number;
  consequence_warning?: string;
  rooms: ExamRoom[];
  contacts: ExamVenueContact[];
  consequence_problems?: VenueConsequenceProblem[];
  map_provider?: {
    mode: 'off' | 'osm' | 'google';
    attribution?: string;
    attribution_url?: string;
  };
  capabilities: {
    manage: boolean;
    retry_consequences?: boolean;
    geocode?: boolean;
    request_promotion: boolean;
    decide_promotion: boolean;
  };
  _links: Record<string, ApiLink>;
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
  terminal_status?: RoundCandidateTerminalStatus;
  terminal_reason?: string | null;
  effective_new_round_id?: number | null;
  postponed_until?: string | null;
  ihk_decision_reference?: string | null;
  terminal_at?: string | null;
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

export type MasterData = {
  committees: Committee[];
  examHalfYears: ExamHalfYear[];
  persons: Person[];
  members: CommitteeMember[];
  candidates: CandidateView[];
  examRounds: ExamRound[];
  candidateAssignments: CandidateCommitteeAssignment[];
  locations: Location[];
  examVenues: ExamVenue[];
  examVenuesCanCreate?: boolean;
};
