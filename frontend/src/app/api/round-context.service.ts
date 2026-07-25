import { Injectable, signal } from '@angular/core';

export const DEFAULT_ROUND_ID = 1;

/**
 * Holds the exam round selected by the application shell.
 *
 * API services read this signal at request time, so a changed selection is
 * consistently applied to subsequent round-scoped requests.
 */
@Injectable({ providedIn: 'root' })
export class RoundContextService {
  readonly roundId = signal(DEFAULT_ROUND_ID);
}
