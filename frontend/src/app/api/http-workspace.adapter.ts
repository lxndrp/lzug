import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { PlanningApiService } from './planning-api.service';
import { withoutHttpLinks } from '../application/without-http-links';
import type { WorkspacePort } from '../shell/workspace.port';

@Injectable({ providedIn: 'root' })
export class HttpWorkspaceAdapter implements WorkspacePort {
  private readonly planningApi = inject(PlanningApiService);

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
}
