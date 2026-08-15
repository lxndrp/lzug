import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { reportFrontendError } from './app/observability/error-reporter';

bootstrapApplication(App, appConfig).catch(() => reportFrontendError('bootstrap'));
