import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { PlanningApiService } from './planning-api.service';
import type { WithoutHttpLinks, WorkspacePort } from '../shell/workspace.port';

@Injectable({ providedIn: 'root' })
export class HttpWorkspaceAdapter implements WorkspacePort {
  private readonly planningApi = inject(PlanningApiService);

  loadDashboard(roundId: number) {
    return this.planningApi.refreshDashboard(roundId).pipe(
      map(({ root, round, summary, board, masterData }) => ({
        applicationVersion: root.version,
        round: withoutHttpLinks(round),
        summary: withoutHttpLinks(summary),
        board: withoutHttpLinks(board),
        masterData: withoutHttpLinks(masterData),
      })),
    );
  }
}

function withoutHttpLinks<T>(value: T): WithoutHttpLinks<T> {
  if (Array.isArray(value)) {
    return value.map((item: unknown) => withoutHttpLinks(item)) as WithoutHttpLinks<T>;
  }
  if (typeof value !== 'object' || value === null) {
    return value as WithoutHttpLinks<T>;
  }
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => key !== '_links')
      .map(([key, item]) => [key, withoutHttpLinks(item)]),
  ) as WithoutHttpLinks<T>;
}
