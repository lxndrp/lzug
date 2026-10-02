import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, takeUntil, throwError } from 'rxjs';

import { AUTHENTICATION_PORT } from '../auth/auth.models';
import { SessionScopeService } from '../auth/session-scope.service';
import { FRONTEND_ERROR_REPORTER_PORT } from '../observability/frontend-error.port';
import { LIFECYCLE_AVAILABILITY_PORT } from '../runtime/lifecycle.port';
import { LifecycleState, lifecycleStates } from '../runtime/lifecycle.models';

const publicProbePaths = ['/api/health', '/api/ready', '/api/lifecycle'];
const lifecycleExemptPaths = [...publicProbePaths, '/api/session/logout'];

function unavailableState(error: HttpErrorResponse): LifecycleState | null {
  const detail = error.error?.error;
  if (error.status !== 503 || !detail || typeof detail !== 'object') return null;
  if (detail.code !== 'runtime_not_ready' || detail.ready !== false) return null;
  return lifecycleStates.includes(detail.state as LifecycleState)
    ? (detail.state as LifecycleState)
    : null;
}

/** Stops business requests while the runtime is unavailable; never retries mutations. */
export const lifecycleInterceptor: HttpInterceptorFn = (request, next) => {
  const lifecycle = inject(LIFECYCLE_AVAILABILITY_PORT);
  const lifecycleExempt = lifecycleExemptPaths.includes(request.url);
  if (!lifecycleExempt && request.url.startsWith('/api') && !lifecycle.isReady()) {
    return throwError(
      () =>
        new HttpErrorResponse({
          status: 503,
          error: {
            error: {
              code: 'runtime_not_ready',
              state: lifecycle.currentState(),
              ready: false,
            },
          },
        }),
    );
  }
  return next(request).pipe(
    catchError((error: HttpErrorResponse) => {
      if (!publicProbePaths.includes(request.url)) {
        const state = unavailableState(error);
        if (state) lifecycle.acceptUnavailable(state);
      }
      return throwError(() => error);
    }),
  );
};

/** Adds browser credentials and handles transport-level session and failure policy. */
export const withSessionCredentials: HttpInterceptorFn = (request, next) => {
  const authentication = inject(AUTHENTICATION_PORT);
  const sessionScope = inject(SessionScopeService);
  const reporter = inject(FRONTEND_ERROR_REPORTER_PORT);
  const generation = sessionScope.generation();
  const establishesSession = request.method === 'GET' && request.url.endsWith('/api/session');
  const response = next(request.clone({ withCredentials: true }));
  const scopedResponse = establishesSession
    ? response
    : response.pipe(takeUntil(sessionScope.invalidatedAfter(generation)));
  return scopedResponse.pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && !request.url.endsWith('/api/auth/login')) {
        authentication.markAnonymous();
      }
      if (
        error.status >= 500 &&
        error.error?.error?.code !== 'runtime_not_ready' &&
        !publicProbePaths.includes(request.url)
      ) {
        reporter.report('http', error.status);
      }
      return throwError(() => error);
    }),
  );
};
