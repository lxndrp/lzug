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
import { PLANNING_PORT } from './planning/planning.port';
import { HttpPlanningAdapter } from './planning/http-planning.adapter';
import { CONFIRMED_PLANS_PORT } from './confirmed-plans/confirmed-plans.port';
import { HttpConfirmedPlansAdapter } from './api/http-confirmed-plans.adapter';
import { EXAM_HALF_YEARS_PORT } from './exam-half-years/exam-half-years.port';
import { HttpExamHalfYearsAdapter } from './api/http-exam-half-years.adapter';
import { PERSONAL_PORT } from './personal/personal.port';
import { HttpPersonalAdapter } from './api/http-personal.adapter';
import { HttpExamProtocolAdapter } from './api/http-exam-protocol.adapter';
import { EXAM_PROTOCOL_PORT } from './exam-protocol/exam-protocol.port';
import { LOCATIONS_PORT } from './locations/locations.port';
import { HttpLocationsAdapter } from './api/http-locations.adapter';
import { HttpLocationsReadAdapter } from './api/http-locations-read.adapter';
import { LOCATIONS_READ_PORT } from './locations/locations.port';
import { HttpDemoScenariosAdapter } from './api/http-demo-scenarios.adapter';
import { DEMO_SCENARIOS_PORT } from './demo-scenarios/application/demo-scenarios.port';
import { MASTER_DATA_PORT } from './master-data/master-data.port';
import { HttpMasterDataAdapter } from './api/http-master-data.adapter';
import { EXAM_DAY_PORT } from './exam-day/exam-day.port';
import { HttpExamDayAdapter } from './api/http-exam-day.adapter';

export const appConfig: ApplicationConfig = {
  providers: [
    { provide: SCHEDULING_OVERVIEW_PORT, useClass: HttpSchedulingOverviewAdapter },
    { provide: PLANNING_PORT, useClass: HttpPlanningAdapter },
    { provide: EXAM_HALF_YEARS_PORT, useClass: HttpExamHalfYearsAdapter },
    { provide: PERSONAL_PORT, useClass: HttpPersonalAdapter },
    { provide: EXAM_PROTOCOL_PORT, useClass: HttpExamProtocolAdapter },
    { provide: LOCATIONS_PORT, useClass: HttpLocationsAdapter },
    { provide: LOCATIONS_READ_PORT, useClass: HttpLocationsReadAdapter },
    { provide: MASTER_DATA_PORT, useClass: HttpMasterDataAdapter },
    { provide: EXAM_DAY_PORT, useClass: HttpExamDayAdapter },
    { provide: WORKSPACE_PORT, useClass: HttpWorkspaceAdapter },
    { provide: CONFIRMED_PLANS_PORT, useClass: HttpConfirmedPlansAdapter },
    { provide: DEMO_SCENARIOS_PORT, useClass: HttpDemoScenariosAdapter },
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
