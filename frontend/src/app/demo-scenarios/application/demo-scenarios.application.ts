import { Injectable, inject } from '@angular/core';

import { DEMO_SCENARIOS_PORT } from './demo-scenarios.port';

/** Application operations for viewing and restarting the demo scenarios. */
@Injectable({ providedIn: 'root' })
export class DemoScenariosApplication {
  private readonly port = inject(DEMO_SCENARIOS_PORT);

  getOverview() {
    return this.port.getOverview();
  }

  reset() {
    return this.port.reset();
  }
}
