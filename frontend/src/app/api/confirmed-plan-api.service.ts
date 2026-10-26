import type { ConfirmedPlan } from './execution.models';
import type { ConfirmedPlanRevision } from './planning.models';
import type {
  ConfirmedPlanChangeRequest,
  PlanningProposalResponse,
  PlanningProposalWriteRequest,
} from './generated/types.gen';
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
    return this.client.get<PlanningProposalResponse>(`/api/exam-rounds/${roundId}/confirmed-plan`);
  }

  saveEditableConfirmedPlan(
    roundId: number,
    proposal: PlanningProposalWriteRequest,
    reason: string,
  ) {
    const request = {
      round_id: proposal.round_id,
      revision: proposal.revision,
      exam_days: proposal.exam_days,
      reason: reason.trim(),
    } satisfies ConfirmedPlanChangeRequest;
    return this.client.put<PlanningProposalResponse>(
      `/api/exam-rounds/${roundId}/confirmed-plan`,
      request,
    );
  }

  getConfirmedPlanRevisions(roundId = this.roundId) {
    return this.client.list<ConfirmedPlanRevision>(
      `/api/exam-rounds/${roundId}/confirmed-plan/revisions`,
    );
  }
}
