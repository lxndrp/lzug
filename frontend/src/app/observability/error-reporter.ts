import { ErrorHandler, Injectable } from '@angular/core';

export type FrontendErrorKind = 'bootstrap' | 'http' | 'runtime';

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

export function reportFrontendError(kind: FrontendErrorKind, status?: number): void {
  const payload = kind === 'http' ? { kind, status: status ?? 0 } : { kind };
  void fetch('/api/observability/frontend-errors', {
    method: 'POST',
    credentials: 'same-origin',
    keepalive: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).catch(() => undefined);
}

@Injectable()
export class PrivacyPreservingErrorHandler implements ErrorHandler {
  handleError(error: unknown): void {
    if (isResizeObserverLoopWarning(error)) {
      return;
    }

    reportFrontendError('runtime');
  }
}

export function providePrivacyPreservingErrorHandler() {
  return { provide: ErrorHandler, useClass: PrivacyPreservingErrorHandler };
}
