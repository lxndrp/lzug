import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';

import { RoundContextService } from '../api/round-context.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
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
        { provide: ApplicationWorkspaceService, useValue: { actionBusy: signal(false) } },
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
