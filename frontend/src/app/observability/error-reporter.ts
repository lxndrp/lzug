import { ErrorHandler, Injectable, inject } from '@angular/core';

import { FRONTEND_ERROR_REPORTER_PORT } from './frontend-error.port';
export type { FrontendErrorKind } from './frontend-error.port';

const RESIZE_OBSERVER_LOOP_PATTERN =
  /ResizeObserver loop completed with undelivered notifications/i;

function getRuntimeErrorMessage(error: unknown): string {
  if (typeof error === 'string') {
    return error;
  }
  if (error && typeof error === 'object' && 'message' in error) {
    return String((error as { message?: unknown }).message ?? '');
  }
  return '';
}

function isResizeObserverLoopWarning(error: unknown): boolean {
  return RESIZE_OBSERVER_LOOP_PATTERN.test(getRuntimeErrorMessage(error));
}

@Injectable()
export class PrivacyPreservingErrorHandler implements ErrorHandler {
  private readonly reporter = inject(FRONTEND_ERROR_REPORTER_PORT);

  handleError(error: unknown): void {
    if (isResizeObserverLoopWarning(error)) {
      return;
    }

    this.reporter.report('runtime');
  }
}

export function providePrivacyPreservingErrorHandler() {
  return { provide: ErrorHandler, useClass: PrivacyPreservingErrorHandler };
}
