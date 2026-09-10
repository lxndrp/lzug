import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  convertToParamMap,
  type ResolveFn,
  type Route,
  RouterStateSnapshot,
} from '@angular/router';
import { vi } from 'vitest';

import { RoundContextService } from './api/round-context.service';
import { routes } from './app.routes';
import { AuthService } from './auth/auth.service';
import { PlanningWorkflowService } from './planning/planning-workflow.service';
import { ApplicationWorkspaceService } from './shell/application-workspace.service';

describe('application routes', () => {
  it('activates every concrete application path through a lazy route component', () => {
    const concreteRoutes = routes.filter((route) => route.redirectTo === undefined);

    expect(concreteRoutes.length).toBeGreaterThan(0);
    for (const route of concreteRoutes) {
      expect(route.children, route.path).toBeUndefined();
      expect(route.component, route.path).toBeUndefined();
      expect(route.loadComponent, route.path).toEqual(expect.any(Function));
    }
  });

  it('keeps the established deep-link and redirect contracts', () => {
    expect(routeFor('scheduling-overview/:roundId').resolve?.['roundId']).toEqual(
      expect.any(Function),
    );
    expect(routeFor('confirmed-plans/:roundId/edit').resolve?.['roundId']).toEqual(
      expect.any(Function),
    );
    expect(routeFor('confirmed-plans/:roundId/days/:dayId').resolve?.['roundId']).toEqual(
      expect.any(Function),
    );
    expect(routeFor('planning').redirectTo).toBe('scheduling-overview');
    expect(routeFor('**').redirectTo).toBe('dashboard');
  });

  it('does not load protected workspace data before authentication completes', () => {
    const roundId = signal<number | null>(null);
    const authState = signal<'checking' | 'authenticated'>('checking');
    const refresh = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        {
          provide: RoundContextService,
          useValue: { roundId, select: (id: number) => roundId.set(id) },
        },
        { provide: AuthService, useValue: { state: authState } },
        { provide: PlanningWorkflowService, useValue: { resetForRoundChange: vi.fn() } },
        { provide: ApplicationWorkspaceService, useValue: { refresh } },
      ],
    });
    const resolver = routeFor('scheduling-overview/:roundId').resolve?.['roundId'] as ResolveFn<
      number | null
    >;
    const route = {
      paramMap: convertToParamMap({ roundId: '7' }),
    } as ActivatedRouteSnapshot;

    TestBed.runInInjectionContext(() => resolver(route, {} as RouterStateSnapshot));

    expect(roundId()).toBe(7);
    expect(refresh).not.toHaveBeenCalled();
  });
});

function routeFor(path: string): Route {
  const route = routes.find((candidate) => candidate.path === path);
  expect(route).toBeDefined();
  return route as Route;
}
