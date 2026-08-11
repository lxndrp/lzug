import {
  ApplicationConfig,
  provideBrowserGlobalErrorListeners,
  provideZoneChangeDetection,
  inject,
  signal,
} from '@angular/core';
import {
  HttpInterceptorFn,
  provideHttpClient,
  withInterceptors,
  withXsrfConfiguration,
} from '@angular/common/http';
import { catchError, throwError } from 'rxjs';
import { provideRouter } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { TUI_LANGUAGE } from '@taiga-ui/i18n';
import { TUI_GERMAN_LANGUAGE } from '@taiga-ui/i18n/languages/german';

import { routes } from './app.routes';
import { AuthService } from './auth/auth.service';

const withSessionCredentials: HttpInterceptorFn = (request, next) =>
  next(request.clone({ withCredentials: true })).pipe(
    catchError((error: { status?: number }) => {
      if (error.status === 401 && !request.url.endsWith('/api/auth/login')) {
        inject(AuthService).markAnonymous();
      }
      return throwError(() => error);
    }),
  );

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(
      withXsrfConfiguration({
        cookieName: 'lzug_csrf',
        headerName: 'X-CSRF-Token',
      }),
      withInterceptors([withSessionCredentials]),
    ),
    provideTaiga({ scrollbars: 'native' }),
    TuiConfirmService,
    { provide: TUI_LANGUAGE, useValue: signal(TUI_GERMAN_LANGUAGE) },
  ],
};
