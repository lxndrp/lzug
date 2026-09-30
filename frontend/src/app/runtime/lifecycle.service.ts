import { Injectable, computed, inject, signal } from '@angular/core';
import { catchError, finalize, map, of, tap, timeout } from 'rxjs';

import { LifecycleApiService } from '../api/lifecycle-api.service';
import type { LifecycleAvailabilityPort } from './lifecycle.port';
import type { LifecycleState } from './lifecycle.models';

export { lifecycleStates } from './lifecycle.models';
export type { LifecycleState } from './lifecycle.models';

/** Initial check and explicit refresh only; never replays a business request. */
@Injectable({ providedIn: 'root' })
export class LifecycleService implements LifecycleAvailabilityPort {
  private readonly api = inject(LifecycleApiService);
  readonly state = signal<LifecycleState | 'unreachable'>('initializing');
  readonly checking = signal(false);
  readonly checkedAt = signal<Date | null>(null);
  readonly ready = computed(() => this.state() === 'ready');

  check() {
    if (this.checking()) return of(false);
    this.checking.set(true);
    return this.api.check().pipe(
      timeout(10000),
      catchError(() => of('unreachable' as const)),
      tap((state) => {
        this.state.set(state);
        this.checkedAt.set(new Date());
      }),
      map((state) => state === 'ready'),
      finalize(() => this.checking.set(false)),
    );
  }

  isReady(): boolean {
    return this.ready();
  }

  currentState(): LifecycleState | 'unreachable' {
    return this.state();
  }

  acceptUnavailable(state: LifecycleState | 'unreachable'): void {
    this.state.set(state === 'ready' ? 'unreachable' : state);
    this.checkedAt.set(new Date());
  }
}
