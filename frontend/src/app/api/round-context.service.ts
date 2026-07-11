import { Injectable, signal } from '@angular/core';

export const DEFAULT_ROUND_ID = 1;

@Injectable({ providedIn: 'root' })
export class RoundContextService {
  readonly roundId = signal(DEFAULT_ROUND_ID);
}
