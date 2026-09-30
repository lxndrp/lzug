import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { DemoScenarioOverview } from '../demo-scenarios.models';
import { DemoScenariosApplication } from './demo-scenarios.application';
import { DEMO_SCENARIOS_PORT } from './demo-scenarios.port';

describe('DemoScenariosApplication', () => {
  it('delegates scenario reads and resets through the transport-neutral port', () => {
    const overview = {} as DemoScenarioOverview;
    const getOverview = vi.fn(() => of(overview));
    const reset = vi.fn(() => of(undefined));
    TestBed.configureTestingModule({
      providers: [
        DemoScenariosApplication,
        { provide: DEMO_SCENARIOS_PORT, useValue: { getOverview, reset } },
      ],
    });
    const application = TestBed.inject(DemoScenariosApplication);

    expect(application.getOverview()).toBe(getOverview.mock.results[0]?.value);
    expect(application.reset()).toBe(reset.mock.results[0]?.value);
    expect(getOverview).toHaveBeenCalledOnce();
    expect(reset).toHaveBeenCalledOnce();
  });
});
