import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { HttpFrontendErrorReporter } from './app/api/frontend-error-api.adapter';

bootstrapApplication(App, appConfig).catch(() =>
  new HttpFrontendErrorReporter().report('bootstrap'),
);
