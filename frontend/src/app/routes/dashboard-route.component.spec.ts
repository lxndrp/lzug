import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';

import { RoundContextService } from '../api/round-context.service';
import { DashboardProjectionService } from '../dashboard/dashboard-projection.service';
import { PlanningWorkflowService } from '../planning/planning-workflow.service';
import { DashboardRouteComponent } from './dashboard-route.component';

describe('DashboardRouteComponent', () => {
  it('activates its projection on entry and deactivates it on exit', () => {
    const dashboard = { activate: vi.fn(), deactivate: vi.fn() };
    TestBed.configureTestingModule({
      imports: [DashboardRouteComponent],
      providers: [
        provideRouter([]),
        { provide: DashboardProjectionService, useValue: dashboard },
        { provide: PlanningWorkflowService, useValue: { lastResult: signal(null) } },
        { provide: RoundContextService, useValue: { roundId: () => 1 } },
      ],
    });
    const fixture = TestBed.createComponent(DashboardRouteComponent);

    expect(dashboard.activate).toHaveBeenCalledOnce();
    fixture.destroy();
    expect(dashboard.deactivate).toHaveBeenCalledOnce();
  });
});
