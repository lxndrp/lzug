import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { Subject } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { PlanningWorkflowService } from '../planning/planning-workflow.service';
import { PlanningRouteComponent } from './planning-route.component';

describe('PlanningRouteComponent', () => {
  it('uses a fresh view token for every reused route activation', () => {
    const routeData = new Subject<Record<string, unknown>>();
    const activateView = vi.fn();
    const deactivateView = vi.fn();
    TestBed.configureTestingModule({
      imports: [PlanningRouteComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { data: routeData } },
        {
          provide: PlanningWorkflowService,
          useValue: { activateView, deactivateView },
        },
        { provide: AuthService, useValue: { session: () => null } },
      ],
    }).overrideComponent(PlanningRouteComponent, { set: { template: '' } });

    const fixture = TestBed.createComponent(PlanningRouteComponent);
    routeData.next({ roundId: 1 });
    routeData.next({ roundId: 2 });
    routeData.next({ roundId: 1 });

    const tokens = activateView.mock.calls.map(([token]) => token);
    expect(tokens).toHaveLength(3);
    expect(new Set(tokens).size).toBe(3);
    expect(activateView.mock.calls.map(([, roundId]) => roundId)).toEqual([1, 2, 1]);

    fixture.destroy();
    expect(deactivateView).toHaveBeenCalledWith(tokens[2]);
  });
});
