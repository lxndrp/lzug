import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

export type ReferenceDataWriteScope = 'locations' | 'candidates' | 'committee-members';

/** Application-level invalidations for shared reference data changed by feature workflows. */
@Injectable({ providedIn: 'root' })
export class ReferenceDataWriteEventsService {
  private readonly committed = new Subject<ReferenceDataWriteScope>();

  readonly committed$ = this.committed.asObservable();

  notifyCommitted(scope: ReferenceDataWriteScope): void {
    this.committed.next(scope);
  }
}
