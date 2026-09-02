import { Injectable } from '@angular/core';
import { Observable, throwError } from 'rxjs';

import { DemoRole, DemoScenarioOverview } from '../api/api.models';

@Injectable({ providedIn: 'root' })
export class RuntimeExperienceService {
  startDemoSession(role: DemoRole): Observable<void> {
    void role;
    return this.unavailable();
  }

  getDemoScenarios(): Observable<DemoScenarioOverview> {
    return this.unavailable();
  }

  resetDemoScenarios(): Observable<{ status: 'reset'; role: string; expires_at: string }> {
    return this.unavailable();
  }

  private unavailable<T>(): Observable<T> {
    return throwError(() => new Error('This runtime experience is not available.'));
  }
}
