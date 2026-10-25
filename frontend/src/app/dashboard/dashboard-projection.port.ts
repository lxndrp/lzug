import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type { CommitteeMember, PlanningBoard, RoundSummary } from '../api/api.models';
import type { Location } from '../api/master-data.models';
import type { PlanningRound } from '../planning/planning.models';

export type DashboardProjection = {
  round: PlanningRound;
  summary: RoundSummary;
  board: PlanningBoard;
};

/** Dashboard-owned read model; its venue refresh does not reload other board data. */
export interface DashboardProjectionPort {
  load(roundId: number): Observable<DashboardProjection>;
  loadLocations(): Observable<Location[]>;
  loadCandidateReferences(roundId: number): Observable<{
    candidates: PlanningBoard['candidates'];
    summary: RoundSummary;
  }>;
  loadCommitteeMembers(): Observable<CommitteeMember[]>;
}

export const DASHBOARD_PROJECTION_PORT = new InjectionToken<DashboardProjectionPort>(
  'DASHBOARD_PROJECTION_PORT',
);
