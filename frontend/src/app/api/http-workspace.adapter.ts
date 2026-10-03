import { Injectable, inject } from '@angular/core';
import { forkJoin, map } from 'rxjs';

import { PlanningApiService } from './planning-api.service';
import { MasterDataApiService } from './master-data-api.service';
import { withoutHttpLinks } from '../application/without-http-links';
import type { WorkspacePort } from '../shell/workspace.port';

@Injectable({ providedIn: 'root' })
export class HttpWorkspaceAdapter implements WorkspacePort {
  private readonly planningApi = inject(PlanningApiService);
  private readonly masterDataApi = inject(MasterDataApiService);

  loadDashboard(roundId: number) {
    return this.planningApi.refreshDashboard(roundId).pipe(
      map(({ root, round, summary, board, masterData }) => {
        const workspaceMasterData = withoutHttpLinks(masterData);
        return {
          applicationVersion: root.version,
          round: withoutHttpLinks(round),
          summary: withoutHttpLinks(summary),
          board: withoutHttpLinks(board),
          masterData: workspaceMasterData,
        };
      }),
    );
  }

  loadLocations() {
    return this.planningApi
      .getLocations()
      .pipe(map((locations) => locations.map(withoutHttpLinks)));
  }

  loadCandidateReferences(roundId: number) {
    return forkJoin({
      candidates: this.masterDataApi.getCandidateViews(roundId),
      candidateAssignments: this.masterDataApi.getCandidateAssignments(),
    }).pipe(
      map(({ candidates, candidateAssignments }) => ({
        candidates: candidates.map(withoutHttpLinks),
        candidateAssignments: candidateAssignments.map(withoutHttpLinks),
      })),
    );
  }

  loadCommitteeMembers() {
    return this.masterDataApi
      .getCommitteeMembers()
      .pipe(map((members) => members.map(withoutHttpLinks)));
  }
}
