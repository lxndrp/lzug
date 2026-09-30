import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  ConfirmedPlan,
  ConfirmedPlanRevision,
  EditablePlanningProposal,
} from '../api/api.models';
import type { WithoutHttpLinks } from '../application/without-http-links';

/** Confirmed-plan queries and revision commands required by the feature. */
export interface ConfirmedPlansPort {
  list(): Observable<WithoutHttpLinks<ConfirmedPlan>[]>;
  getEditable(roundId: number): Observable<WithoutHttpLinks<EditablePlanningProposal>>;
  saveEditable(
    roundId: number,
    proposal: WithoutHttpLinks<EditablePlanningProposal>,
    reason: string,
  ): Observable<WithoutHttpLinks<EditablePlanningProposal>>;
  listRevisions(roundId: number): Observable<WithoutHttpLinks<ConfirmedPlanRevision>[]>;
}

export const CONFIRMED_PLANS_PORT = new InjectionToken<ConfirmedPlansPort>('CONFIRMED_PLANS_PORT');
