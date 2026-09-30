import { Injectable } from '@angular/core';

import { FrontendErrorKind, FrontendErrorReporterPort } from '../observability/frontend-error.port';

/** Sends privacy-filtered frontend error classifications to the HTTP endpoint. */
@Injectable({ providedIn: 'root' })
export class HttpFrontendErrorReporter implements FrontendErrorReporterPort {
  report(kind: FrontendErrorKind, status?: number): void {
    const payload = kind === 'http' ? { kind, status: status ?? 0 } : { kind };
    void fetch('/api/observability/frontend-errors', {
      method: 'POST',
      credentials: 'same-origin',
      keepalive: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => undefined);
  }
}
