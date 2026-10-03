import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

export type PlanningWriteInvalidationScope = 'round' | 'related-rounds';
export type PlanningWriteCommit = {
  sourceRoundId: number;
  scope: PlanningWriteInvalidationScope;
};

/** Application-level invalidation events for projections affected by planning writes. */
@Injectable({ providedIn: 'root' })
export class PlanningWriteEventsService {
  private readonly committed = new Subject<PlanningWriteCommit>();

  readonly committed$ = this.committed.asObservable();

  notifyCommitted(sourceRoundId: number, scope: PlanningWriteInvalidationScope = 'round'): void {
    this.committed.next({ sourceRoundId, scope });
  }
}
