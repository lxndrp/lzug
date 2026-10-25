import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type { CommitteeMember } from '../api/master-data.models';
import type { Location } from '../api/master-data.models';
import type { PlanningBoard, PlanningRound, PlanningSummary } from '../planning/planning.models';

export type DashboardProjection = {
  round: PlanningRound;
  summary: PlanningSummary;
  board: PlanningBoard;
};

/** Dashboard-owned read model; its venue refresh does not reload other board data. */
export interface DashboardProjectionPort {
  load(roundId: number): Observable<DashboardProjection>;
  loadLocations(): Observable<Location[]>;
  loadCandidateReferences(roundId: number): Observable<{
    candidates: PlanningBoard['candidates'];
    summary: PlanningSummary;
  }>;
  loadCommitteeMembers(): Observable<CommitteeMember[]>;
}

export const DASHBOARD_PROJECTION_PORT = new InjectionToken<DashboardProjectionPort>(
  'DASHBOARD_PROJECTION_PORT',
);
