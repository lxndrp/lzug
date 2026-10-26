import { Injectable } from '@angular/core';
import { Observable, throwError } from 'rxjs';

import type { DemoRole } from '../auth/auth.models';

@Injectable({ providedIn: 'root' })
export class RuntimeExperienceService {
  startDemoSession(role: DemoRole): Observable<void> {
    void role;
    return this.unavailable();
  }

  resetDemoScenarios(): Observable<{ status: 'reset'; role: string; expires_at: string }> {
    return this.unavailable();
  }

  private unavailable<T>(): Observable<T> {
    return throwError(() => new Error('This runtime experience is not available.'));
  }
}
