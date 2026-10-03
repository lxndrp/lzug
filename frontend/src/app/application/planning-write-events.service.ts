import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

/** Application-level invalidation events for projections affected by planning writes. */
@Injectable({ providedIn: 'root' })
export class PlanningWriteEventsService {
  private readonly committed = new Subject<number>();

  readonly committed$ = this.committed.asObservable();

  notifyCommitted(roundId: number): void {
    this.committed.next(roundId);
  }
}
