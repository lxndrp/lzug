import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type { ExamRound, MasterData, PlanningBoard, RoundSummary } from '../api/api.models';
import type { WithoutHttpLinks } from '../application/without-http-links';
import type { CandidateWorkspace, CommitteeWorkspace } from '../master-data/master-data.models';

/** Shared workspace data for route-level features, without HAL navigation links. */
export type WorkspaceSnapshot = {
  applicationVersion: string;
  round: WithoutHttpLinks<ExamRound>;
  summary: WithoutHttpLinks<RoundSummary>;
  board: WithoutHttpLinks<PlanningBoard>;
  masterData: WithoutHttpLinks<MasterData>;
  candidateWorkspace: CandidateWorkspace;
  committeeWorkspace: CommitteeWorkspace;
};

export interface WorkspacePort {
  loadDashboard(roundId: number): Observable<WorkspaceSnapshot>;
}

export const WORKSPACE_PORT = new InjectionToken<WorkspacePort>('WORKSPACE_PORT');
