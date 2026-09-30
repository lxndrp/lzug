import {
  ApplicationConfig,
  provideBrowserGlobalErrorListeners,
  provideZoneChangeDetection,
  signal,
} from '@angular/core';
import { provideHttpClient, withInterceptors, withXsrfConfiguration } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { TUI_LANGUAGE } from '@taiga-ui/i18n';
import { TUI_GERMAN_LANGUAGE } from '@taiga-ui/i18n/languages/german';

import { SCHEDULING_OVERVIEW_PORT } from './scheduling-overview/application/scheduling-overview.port';
import { HttpSchedulingOverviewAdapter } from './scheduling-overview/adapters/http-scheduling-overview.adapter';
import { WORKSPACE_PORT } from './shell/workspace.port';
import { HttpWorkspaceAdapter } from './api/http-workspace.adapter';
import { routes } from './app.routes';
import { AUTHENTICATION_PORT } from './auth/auth.models';
import { AuthService } from './auth/auth.service';
import { LifecycleService } from './runtime/lifecycle.service';
import { LIFECYCLE_AVAILABILITY_PORT } from './runtime/lifecycle.port';
import { lifecycleInterceptor, withSessionCredentials } from './api/http-interceptors';
import { providePrivacyPreservingErrorHandler } from './observability/error-reporter';
import { FRONTEND_ERROR_REPORTER_PORT } from './observability/frontend-error.port';
import { HttpFrontendErrorReporter } from './api/frontend-error-api.adapter';

export const appConfig: ApplicationConfig = {
  providers: [
    { provide: SCHEDULING_OVERVIEW_PORT, useClass: HttpSchedulingOverviewAdapter },
    { provide: WORKSPACE_PORT, useClass: HttpWorkspaceAdapter },
    { provide: AUTHENTICATION_PORT, useExisting: AuthService },
    { provide: LIFECYCLE_AVAILABILITY_PORT, useExisting: LifecycleService },
    { provide: FRONTEND_ERROR_REPORTER_PORT, useClass: HttpFrontendErrorReporter },
    provideBrowserGlobalErrorListeners(),
    providePrivacyPreservingErrorHandler(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(
      withXsrfConfiguration({
        cookieName: 'lzug_csrf',
        headerName: 'X-CSRF-Token',
      }),
      withInterceptors([lifecycleInterceptor, withSessionCredentials]),
    ),
    provideTaiga({ scrollbars: 'native' }),
    TuiConfirmService,
    { provide: TUI_LANGUAGE, useValue: signal(TUI_GERMAN_LANGUAGE) },
  ],
};
