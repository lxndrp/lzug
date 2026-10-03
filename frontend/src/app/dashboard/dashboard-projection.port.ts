import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type { ExamRound, PlanningBoard, RoundSummary } from '../api/api.models';
import type { Location } from '../api/master-data.models';

export type DashboardProjection = {
  applicationVersion: string;
  round: ExamRound;
  summary: RoundSummary;
  board: PlanningBoard;
};

/** Dashboard-owned read model; its venue refresh does not reload other board data. */
export interface DashboardProjectionPort {
  load(roundId: number): Observable<DashboardProjection>;
  loadLocations(): Observable<Location[]>;
}

export const DASHBOARD_PROJECTION_PORT = new InjectionToken<DashboardProjectionPort>(
  'DASHBOARD_PROJECTION_PORT',
);
