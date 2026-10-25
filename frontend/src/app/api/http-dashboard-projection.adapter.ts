import { Injectable, inject } from '@angular/core';
import { forkJoin, map } from 'rxjs';

import type { DashboardProjectionPort } from '../dashboard/dashboard-projection.port';
import type { CandidateView, CommitteeMember, Location } from './master-data.models';
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
          board: {
            ...board,
            candidates: board.candidates.map(projectCandidateView),
            locations: board.locations.map(projectLocation),
            days: board.days.map((view) => ({
              ...view,
              ...(view.location ? { location: projectLocation(view.location) } : {}),
            })),
          },
        };
      }),
    );
  }

  loadLocations() {
    return this.api.getLocations().pipe(map((items) => items.map(projectLocation)));
  }

  loadCandidateReferences(roundId: number) {
    return forkJoin({
      candidates: this.masterData.getCandidateViews(roundId),
      summary: this.api.getRoundSummary(roundId),
    }).pipe(
      map(({ candidates, summary }) => {
        const { _links, ...summaryProjection } = summary;
        void _links;
        return { candidates: candidates.map(projectCandidateView), summary: summaryProjection };
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

function projectCandidateView(view: CandidateView): CandidateView {
  return {
    ...view,
    candidate: projectCandidate(view.candidate),
  };
}

function projectCandidate(candidate: CandidateView['candidate']) {
  return {
    id: candidate.id,
    first_name: candidate.first_name,
    last_name: candidate.last_name,
    ihk_exam_number: candidate.ihk_exam_number,
    specialization: candidate.specialization,
    training_company: candidate.training_company,
    ...(candidate.created_at !== undefined ? { created_at: candidate.created_at } : {}),
    ...(candidate.updated_at !== undefined ? { updated_at: candidate.updated_at } : {}),
  };
}

function projectLocation(location: Location): Location {
  return {
    id: location.id,
    ...(location.committee_id !== undefined ? { committee_id: location.committee_id } : {}),
    name: location.name,
    ...(location.street !== undefined ? { street: location.street } : {}),
    ...(location.postal_code !== undefined ? { postal_code: location.postal_code } : {}),
    room: location.room,
    city: location.city,
    ...(location.is_active !== undefined ? { is_active: location.is_active } : {}),
    ...(location.created_at !== undefined ? { created_at: location.created_at } : {}),
    ...(location.updated_at !== undefined ? { updated_at: location.updated_at } : {}),
  };
}
