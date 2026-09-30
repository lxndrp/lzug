import { Injectable, inject } from '@angular/core';

import type { DemoRole } from '../api/api.models';
import { RuntimeExperienceApiService } from '../api/runtime-experience-api.service';

@Injectable({ providedIn: 'root' })
export class RuntimeExperienceService {
  private readonly api = inject(RuntimeExperienceApiService);

  startDemoSession(role: DemoRole) {
    return this.api.startDemoSession(role);
  }

  getDemoScenarios() {
    return this.api.getDemoScenarios();
  }

  resetDemoScenarios() {
    return this.api.resetDemoScenarios();
  }
}
