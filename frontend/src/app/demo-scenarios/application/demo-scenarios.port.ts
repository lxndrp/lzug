import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import { DemoScenarioOverview } from '../demo-scenarios.models';

/** Read and reset the current demo scenario workspace. */
export interface DemoScenariosPort {
  getOverview(): Observable<DemoScenarioOverview>;
  reset(): Observable<void>;
}

export const DEMO_SCENARIOS_PORT = new InjectionToken<DemoScenariosPort>('DEMO_SCENARIOS_PORT');
