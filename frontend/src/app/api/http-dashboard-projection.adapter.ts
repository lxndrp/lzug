import { Injectable, inject } from '@angular/core';
import { forkJoin, map } from 'rxjs';

import type { DashboardProjectionPort } from '../dashboard/dashboard-projection.port';
import type { CommitteeMember } from './master-data.models';
import { MasterDataApiService } from './master-data-api.service';
import { PlanningApiService } from './planning-api.service';

/** HTTP adapter for dashboard-owned data; targeted references are read separately. */
@Injectable({ providedIn: 'root' })
export class HttpDashboardProjectionAdapter implements DashboardProjectionPort {
  private readonly api = inject(PlanningApiService);
  private readonly masterData = inject(MasterDataApiService);

  load(roundId: number) {
    return this.api.loadDashboardProjection(roundId).pipe(
      map(({ round, summary, board }) => {
        const { _links: summaryLinks, ...summaryProjection } = summary;
        void summaryLinks;
        return {
          round: {
            id: round.id,
            exam_half_year_id: round.exam_half_year_id,
            name: round.name,
            committee_id: round.committee_id,
            status: round.status,
            revision: round.revision,
            lifecycle_status: round.lifecycle_status,
            legacy_status: round.legacy_status,
            availability_deadline: round.availability_deadline,
            availability_reminder_at: round.availability_reminder_at,
            updated_at: round.updated_at,
          },
          summary: summaryProjection,
          board,
        };
      }),
    );
  }

  loadLocations() {
    return this.api.getLocations();
  }

  loadCandidateReferences(roundId: number) {
    return forkJoin({
      candidates: this.masterData.getCandidateViews(roundId),
      summary: this.api.getRoundSummary(roundId),
    }).pipe(
      map(({ candidates, summary }) => {
        const { _links, ...summaryProjection } = summary;
        void _links;
        return { candidates, summary: summaryProjection };
      }),
    );
  }

  loadCommitteeMembers() {
    return this.masterData.getCommitteeMembers().pipe(
      map((items): CommitteeMember[] =>
        items.map((item) => ({
          id: item.id,
          person_id: item.person_id,
          committee_id: item.committee_id,
          first_name: item.first_name,
          last_name: item.last_name,
          member_status: item.member_status,
          committee_role: item.committee_role,
          representing_side: item.representing_side,
          email: item.email,
          email_verified_at: item.email_verified_at ?? null,
          mobile: item.mobile,
          is_active: item.is_active,
        })),
      ),
    );
  }
}
