import { Injectable, inject } from '@angular/core';
import { forkJoin, map } from 'rxjs';

import { withoutHttpLinks } from '../application/without-http-links';
import type { DashboardProjectionPort } from '../dashboard/dashboard-projection.port';
import { MasterDataApiService } from './master-data-api.service';
import { PlanningApiService } from './planning-api.service';

/** HTTP adapter for dashboard-owned data; targeted references are read separately. */
@Injectable({ providedIn: 'root' })
export class HttpDashboardProjectionAdapter implements DashboardProjectionPort {
  private readonly api = inject(PlanningApiService);
  private readonly masterData = inject(MasterDataApiService);

  load(roundId: number) {
    return this.api.loadDashboardProjection(roundId).pipe(
      map(({ round, summary, board }) => ({
        round: withoutHttpLinks(round),
        summary: withoutHttpLinks(summary),
        board: withoutHttpLinks(board),
      })),
    );
  }

  loadLocations() {
    return this.api.getLocations().pipe(map((locations) => locations.map(withoutHttpLinks)));
  }

  loadCandidateReferences(roundId: number) {
    return forkJoin({
      candidates: this.masterData.getCandidateViews(roundId),
      summary: this.api.getRoundSummary(roundId),
    }).pipe(map((references) => withoutHttpLinks(references)));
  }

  loadCommitteeMembers() {
    return this.masterData
      .getCommitteeMembers()
      .pipe(map((members) => members.map(withoutHttpLinks)));
  }
}
