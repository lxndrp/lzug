import type { ConfirmedPlan } from './execution.models';
import type { ConfirmedPlanRevision, EditablePlanningProposal } from './planning.models';
import { Injectable, inject } from '@angular/core';

import { ApiClient } from './api-client.service';
import { RoundContextService } from './round-context.service';

/** Confirmed-plan list, revision, and editor operations. */

@Injectable({ providedIn: 'root' })
export class ConfirmedPlanApiService {
  private readonly client = inject(ApiClient);
  private readonly roundContext = inject(RoundContextService);

  private get roundId(): number {
    return this.roundContext.roundId();
  }

  getConfirmedPlans() {
    return this.client.list<ConfirmedPlan>('/api/confirmed-plans');
  }

  getEditableConfirmedPlan(roundId = this.roundId) {
    return this.client.get<EditablePlanningProposal>(`/api/exam-rounds/${roundId}/confirmed-plan`);
  }

  saveEditableConfirmedPlan(roundId: number, proposal: EditablePlanningProposal, reason: string) {
    const { _links, ...payload } = proposal;
    void _links;
    return this.client.put<EditablePlanningProposal>(`/api/exam-rounds/${roundId}/confirmed-plan`, {
      ...payload,
      reason: reason.trim(),
    });
  }

  getConfirmedPlanRevisions(roundId = this.roundId) {
    return this.client.list<ConfirmedPlanRevision>(
      `/api/exam-rounds/${roundId}/confirmed-plan/revisions`,
    );
  }
}
