import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

import { DemoRole, DemoScenarioOverview } from '../api/api.models';

@Injectable({ providedIn: 'root' })
export class RuntimeExperienceService {
  private readonly http = inject(HttpClient);

  startDemoSession(role: DemoRole) {
    return this.http.post<void>('/api/demo/session', { role });
  }

  getDemoScenarios() {
    return this.http.get<DemoScenarioOverview>('/api/demo/scenarios');
  }

  resetDemoScenarios() {
    return this.http.post<{ status: 'reset'; role: string; expires_at: string }>(
      '/api/demo/reset',
      {},
    );
  }
}
