import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { Subject } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { PlanningWorkflowService } from '../planning/planning-workflow.service';
import { PlanningRouteComponent } from './planning-route.component';

describe('PlanningRouteComponent', () => {
  it('creates a distinct view token for each A to B to A activation', () => {
    const routeData = new Subject<Record<string, unknown>>();
    const workflow = { activateView: vi.fn(), deactivateView: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        { provide: ActivatedRoute, useValue: { data: routeData } },
        { provide: Router, useValue: { navigateByUrl: vi.fn() } },
        {
          provide: AuthService,
          useValue: { session: () => null, hasCapability: () => false },
        },
        { provide: PlanningWorkflowService, useValue: workflow },
      ],
    });

    TestBed.runInInjectionContext(() => new PlanningRouteComponent());
    routeData.next({ roundId: 1 });
    routeData.next({ roundId: 2 });
    routeData.next({ roundId: 1 });

    const activations = workflow.activateView.mock.calls;
    expect(activations.map(([, roundId]) => roundId)).toEqual([1, 2, 1]);
    expect(new Set(activations.map(([view]) => view)).size).toBe(3);
  });

  it('retries planning with the existing route view token', () => {
    const routeData = new Subject<Record<string, unknown>>();
    const workflow = { activateView: vi.fn(), deactivateView: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        { provide: ActivatedRoute, useValue: { data: routeData } },
        { provide: Router, useValue: { navigateByUrl: vi.fn() } },
        {
          provide: AuthService,
          useValue: { session: () => null, hasCapability: () => false },
        },
        { provide: PlanningWorkflowService, useValue: workflow },
      ],
    });

    const route = TestBed.runInInjectionContext(() => new PlanningRouteComponent()) as unknown as {
      reloadPlanning(): void;
    };
    routeData.next({ roundId: 1 });
    const originalView = workflow.activateView.mock.calls[0][0];

    route.reloadPlanning();

    expect(workflow.activateView).toHaveBeenLastCalledWith(originalView, 1);
    expect(workflow.activateView).toHaveBeenCalledTimes(2);
  });

  it('redirects when the round resolver returns an invalid route parameter', () => {
    const routeData = new Subject<Record<string, unknown>>();
    const workflow = { activateView: vi.fn(), deactivateView: vi.fn() };
    const router = { navigateByUrl: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        { provide: ActivatedRoute, useValue: { data: routeData } },
        { provide: Router, useValue: router },
        {
          provide: AuthService,
          useValue: { session: () => null, hasCapability: () => false },
        },
        { provide: PlanningWorkflowService, useValue: workflow },
      ],
    });

    TestBed.runInInjectionContext(() => new PlanningRouteComponent());
    routeData.next({ roundId: null });

    expect(router.navigateByUrl).toHaveBeenCalledWith('/scheduling-overview', {
      replaceUrl: true,
    });
    expect(workflow.activateView).not.toHaveBeenCalled();
  });
});
