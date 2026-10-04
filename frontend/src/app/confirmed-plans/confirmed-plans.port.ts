import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  ConfirmedPlan,
  ConfirmedPlanRevision,
  ConfirmedPlansBoard,
  EditableConfirmedPlan,
} from './confirmed-plans.models';

/** Confirmed-plan queries and revision commands required by the feature. */
export interface ConfirmedPlansPort {
  list(): Observable<ConfirmedPlan[]>;
  loadEditorReferences(roundId: number): Observable<ConfirmedPlansBoard>;
  getEditable(roundId: number): Observable<EditableConfirmedPlan>;
  saveEditable(
    roundId: number,
    proposal: EditableConfirmedPlan,
    reason: string,
  ): Observable<EditableConfirmedPlan>;
  listRevisions(roundId: number): Observable<ConfirmedPlanRevision[]>;
}

export const CONFIRMED_PLANS_PORT = new InjectionToken<ConfirmedPlansPort>('CONFIRMED_PLANS_PORT');
