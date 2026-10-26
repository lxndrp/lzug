import { Injectable, inject } from '@angular/core';

import type { DemoRole } from '../auth/auth.models';
import type { DemoScenarioOverviewResponse } from './generated/types.gen';
import { ApiClient } from './api-client.service';

/** HTTP adapter for optional demonstration scenarios. */
@Injectable({ providedIn: 'root' })
export class RuntimeExperienceApiService {
  private readonly client = inject(ApiClient);

  startDemoSession(role: DemoRole) {
    return this.client.post<void>('/api/demo/session', { role });
  }

  getDemoScenarios() {
    return this.client.get<DemoScenarioOverviewResponse>('/api/demo/scenarios');
  }

  resetDemoScenarios() {
    return this.client.post<{ status: 'reset'; role: string; expires_at: string }>(
      '/api/demo/reset',
      {},
    );
  }
}
