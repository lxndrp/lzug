import { InjectionToken } from '@angular/core';

export type FrontendErrorKind = 'bootstrap' | 'http' | 'runtime';

export interface FrontendErrorReporterPort {
  report(kind: FrontendErrorKind, status?: number): void;
}

export const FRONTEND_ERROR_REPORTER_PORT = new InjectionToken<FrontendErrorReporterPort>(
  'FRONTEND_ERROR_REPORTER_PORT',
);
