import { Injectable, inject } from '@angular/core';

import type { DemoRole, DemoScenarioOverview } from './api.models';
import { ApiClient } from './api-client.service';

/** HTTP adapter for optional demonstration scenarios. */
@Injectable({ providedIn: 'root' })
export class RuntimeExperienceApiService {
  private readonly client = inject(ApiClient);

  startDemoSession(role: DemoRole) {
    return this.client.post<void>('/api/demo/session', { role });
  }

  getDemoScenarios() {
    return this.client.get<DemoScenarioOverview>('/api/demo/scenarios');
  }

  resetDemoScenarios() {
    return this.client.post<{ status: 'reset'; role: string; expires_at: string }>(
      '/api/demo/reset',
      {},
    );
  }
}
