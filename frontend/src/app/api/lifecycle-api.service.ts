import { Injectable, inject } from '@angular/core';
import { catchError, map, of, throwError } from 'rxjs';

import { ApplicationError } from './application-error';
import { ApiClient } from './api-client.service';
import { lifecycleStates } from '../runtime/lifecycle.models';
import type { LifecycleState } from '../runtime/lifecycle.models';

function stateFrom(payload: unknown): LifecycleState | null {
  if (!payload || typeof payload !== 'object') return null;
  const value = payload as { state?: unknown; ready?: unknown };
  return lifecycleStates.includes(value.state as LifecycleState) &&
    value.ready === (value.state === 'ready')
    ? (value.state as LifecycleState)
    : null;
}

function unavailableState(error: ApplicationError): LifecycleState | 'unreachable' {
  if (error.code !== 'runtime_not_ready' || !error.details || typeof error.details !== 'object') {
    return 'unreachable';
  }
  const state = stateFrom(error.details);
  return state && state !== 'ready' ? state : 'unreachable';
}

/** HTTP adapter for the public runtime lifecycle endpoint. */
@Injectable({ providedIn: 'root' })
export class LifecycleApiService {
  private readonly client = inject(ApiClient);

  check() {
    return this.client.get<unknown>('/api/lifecycle').pipe(
      map((payload) => stateFrom(payload) ?? ('unreachable' as const)),
      catchError((error: ApplicationError) =>
        error.code === 'runtime_not_ready' ? of(unavailableState(error)) : throwError(() => error),
      ),
    );
  }
}
