import { Injectable, inject, signal } from '@angular/core';
import { Subject } from 'rxjs';
import { SessionScopeService } from '../auth/session-scope.service';

export const DEFAULT_ROUND_ID = 1;

/**
 * Holds the exam round selected by the application shell.
 *
 * APIs that follow the shell selection read this signal at request time.
 * Features with an explicit source context pass their round ID directly.
 */
@Injectable({ providedIn: 'root' })
export class RoundContextService {
  private readonly sessionScope = inject(SessionScopeService);
  readonly roundId = signal(DEFAULT_ROUND_ID);
  private readonly changes = new Subject<number>();
  readonly changes$ = this.changes.asObservable();

  constructor() {
    this.sessionScope.changes$.subscribe(({ previousEstablished, established }) => {
      if (previousEstablished || !established) this.select(DEFAULT_ROUND_ID);
    });
  }

  select(roundId: number): void {
    if (this.roundId() === roundId) return;
    this.roundId.set(roundId);
    this.changes.next(roundId);
  }
}
