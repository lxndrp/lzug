import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

export type ApplicationShellContext = {
  applicationVersion: string;
  roundId: number;
  halfYear: string;
  round: string;
  committee: string;
  status: string;
};

export interface ApplicationShellContextPort {
  load(roundId: number): Observable<ApplicationShellContext>;
}

export const APPLICATION_SHELL_CONTEXT_PORT = new InjectionToken<ApplicationShellContextPort>(
  'APPLICATION_SHELL_CONTEXT_PORT',
);
