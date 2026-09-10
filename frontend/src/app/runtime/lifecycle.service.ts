import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { catchError, finalize, map, of, tap, throwError, timeout } from 'rxjs';

/** Public state codes shared with the backend's lifecycle response. */
export const lifecycleStates = [
  'initializing',
  'ready',
  'maintenance',
  'migration_required',
  'migrating',
  'error',
  'stopping',
  'stopped',
] as const;
export type LifecycleState = (typeof lifecycleStates)[number];

function stateFrom(payload: unknown): LifecycleState | null {
  if (!payload || typeof payload !== 'object') return null;
  const value = payload as { state?: unknown; ready?: unknown };
  return lifecycleStates.includes(value.state as LifecycleState) &&
    value.ready === (value.state === 'ready')
    ? (value.state as LifecycleState)
    : null;
}

/** Initial check and explicit refresh only; never replays a business request. */
@Injectable({ providedIn: 'root' })
export class LifecycleService {
  private readonly http = inject(HttpClient);
  readonly state = signal<LifecycleState | 'unreachable'>('initializing');
  readonly checking = signal(false);
  readonly checkedAt = signal<Date | null>(null);
  readonly ready = computed(() => this.state() === 'ready');

  check() {
    if (this.checking()) return of(false);
    this.checking.set(true);
    return this.http.get<unknown>('/api/lifecycle').pipe(
      timeout(10000),
      map((payload) => stateFrom(payload) ?? ('unreachable' as const)),
      catchError(() => of('unreachable' as const)),
      tap((state) => {
        this.state.set(state);
        this.checkedAt.set(new Date());
      }),
      map((state) => state === 'ready'),
      finalize(() => this.checking.set(false)),
    );
  }

  acceptUnavailable(error: HttpErrorResponse): boolean {
    if (error.status !== 503 || error.error?.error?.code !== 'runtime_not_ready') return false;
    const state = stateFrom(error.error.error);
    this.state.set(state && state !== 'ready' ? state : 'unreachable');
    this.checkedAt.set(new Date());
    return true;
  }
}

/** Stop new API work while unavailable; already sent mutations are never retried. */
export const lifecycleInterceptor: HttpInterceptorFn = (request, next) => {
  const lifecycle = inject(LifecycleService);
  const publicProbe = ['/api/health', '/api/ready', '/api/lifecycle'].includes(request.url);
  if (!publicProbe && request.url.startsWith('/api') && !lifecycle.ready()) {
    return throwError(
      () =>
        new HttpErrorResponse({
          status: 503,
          error: { error: { code: 'runtime_not_ready', state: lifecycle.state(), ready: false } },
        }),
    );
  }
  return next(request).pipe(
    catchError((error: HttpErrorResponse) => {
      if (!publicProbe) lifecycle.acceptUnavailable(error);
      return throwError(() => error);
    }),
  );
};
