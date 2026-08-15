import { ErrorHandler, Injectable } from '@angular/core';

export type FrontendErrorKind = 'bootstrap' | 'http' | 'runtime';

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
    void error;
    reportFrontendError('runtime');
  }
}

export function providePrivacyPreservingErrorHandler() {
  return { provide: ErrorHandler, useClass: PrivacyPreservingErrorHandler };
}
