import { Injectable, inject } from '@angular/core';

import { CONFIRMED_PLANS_PORT } from './confirmed-plans.port';

/** Application operations used by the confirmed-plan list and editor. */
@Injectable({ providedIn: 'root' })
export class ConfirmedPlansWorkflowService {
  private readonly plans = inject(CONFIRMED_PLANS_PORT);

  getConfirmedPlans() {
    return this.plans.list();
  }

  getEditableConfirmedPlan(roundId: number) {
    return this.plans.getEditable(roundId);
  }

  saveEditableConfirmedPlan(
    roundId: number,
    proposal: Parameters<typeof this.plans.saveEditable>[1],
    reason: string,
  ) {
    return this.plans.saveEditable(roundId, proposal, reason);
  }

  getConfirmedPlanRevisions(roundId: number) {
    return this.plans.listRevisions(roundId);
  }
}
