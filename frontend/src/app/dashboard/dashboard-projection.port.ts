import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

export type DashboardRound = {
  id: number;
  status: string;
  name: string;
  availability_deadline: string | null;
  availability_reminder_at: string | null;
};

export type DashboardSummary = {
  round: { name: string; status: string; committee_name: string };
  counts: { candidates: number; mep_count: number; required_exam_slots: number };
  settings: {
    calendar_week_from: string;
    calendar_week_to: string;
    exams_per_day: number;
    max_exam_days_per_week: number;
  } | null;
  availability: Array<{ availability: string; count: number }>;
};

export type DashboardLocation = { id: number; name: string; room: string };
export type DashboardMember = {
  id: number;
  first_name: string;
  last_name: string;
  representing_side: string;
};
export type DashboardCandidate = { first_name: string; last_name: string };
export type DashboardCandidateView = {
  candidate: DashboardCandidate;
  roundCandidate?: { id: number };
};
export type DashboardDayView = {
  day: { id: number; date: string; status: string; location_id: number };
  slots: Array<{
    id: number;
    round_candidate_id: number;
    starts_at: string;
    ends_at: string;
    slot_type: string;
  }>;
  assignments: Array<{
    id: number;
    committee_member_id: number;
    assignment_role: string;
    day_part: string;
  }>;
  location?: DashboardLocation;
};
export type DashboardBoard = {
  days: DashboardDayView[];
  members: DashboardMember[];
  candidates: DashboardCandidateView[];
  candidateDays: Array<{ id: number; is_active: number }>;
  locations: DashboardLocation[];
};
export type DashboardPlanningResult = {
  status?: string;
  counts?: Record<string, number>;
  validation?: { passed: boolean; messages: string[] };
};

export type DashboardProjection = {
  round: DashboardRound;
  summary: DashboardSummary;
  board: DashboardBoard;
};

/** Dashboard-owned read model; its venue refresh does not reload other board data. */
export interface DashboardProjectionPort {
  load(roundId: number): Observable<DashboardProjection>;
  loadLocations(): Observable<DashboardLocation[]>;
  loadCandidateReferences(roundId: number): Observable<{
    candidates: DashboardCandidateView[];
    summary: DashboardSummary;
  }>;
  loadCommitteeMembers(): Observable<DashboardMember[]>;
}

export const DASHBOARD_PROJECTION_PORT = new InjectionToken<DashboardProjectionPort>(
  'DASHBOARD_PROJECTION_PORT',
);
