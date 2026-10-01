import { Injectable, inject, signal } from '@angular/core';
import { SessionScopeService } from '../auth/session-scope.service';

export const DEFAULT_ROUND_ID = 1;

/**
 * Holds the exam round selected by the application shell.
 *
 * API services read this signal at request time, so a changed selection is
 * consistently applied to subsequent round-scoped requests.
 */
@Injectable({ providedIn: 'root' })
export class RoundContextService {
  private readonly sessionScope = inject(SessionScopeService);
  readonly roundId = signal(DEFAULT_ROUND_ID);

  constructor() {
    this.sessionScope.changes$.subscribe(() => this.roundId.set(DEFAULT_ROUND_ID));
  }

  select(roundId: number): void {
    this.roundId.set(roundId);
  }
}
