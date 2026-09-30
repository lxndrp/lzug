import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { ConfirmedPlanApiService } from './confirmed-plan-api.service';
import { withoutHttpLinks } from '../application/without-http-links';
import type { ConfirmedPlansPort } from '../confirmed-plans/confirmed-plans.port';

/** HTTP adapter for confirmed-plan application operations. */
@Injectable({ providedIn: 'root' })
export class HttpConfirmedPlansAdapter implements ConfirmedPlansPort {
  private readonly api = inject(ConfirmedPlanApiService);

  list() {
    return this.api.getConfirmedPlans().pipe(map(withoutHttpLinks));
  }

  getEditable(roundId: number) {
    return this.api.getEditableConfirmedPlan(roundId).pipe(map(withoutHttpLinks));
  }

  saveEditable(...args: Parameters<ConfirmedPlansPort['saveEditable']>) {
    return this.api.saveEditableConfirmedPlan(...args).pipe(map(withoutHttpLinks));
  }

  listRevisions(roundId: number) {
    return this.api.getConfirmedPlanRevisions(roundId).pipe(map(withoutHttpLinks));
  }
}
