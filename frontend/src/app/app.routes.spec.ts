import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  CanActivateFn,
  convertToParamMap,
  provideRouter,
  Router,
  type ResolveFn,
  type Route,
  UrlTree,
  type RouterStateSnapshot,
} from '@angular/router';
import { vi } from 'vitest';

import { RoundContextService } from './api/round-context.service';
import { roundContextResolver, routes } from './app.routes';
import { AuthService } from './auth/auth.service';
import { SessionScopeService } from './auth/session-scope.service';
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
      expect(
        route.canActivate?.some((guard) => typeof guard === 'function'),
        route.path,
      ).toBe(true);
    }
  });

  it('redirects anonymous users away from application routes', () => {
    const auth = { state: () => 'anonymous', session: () => null, initialize: vi.fn() };
    TestBed.configureTestingModule({
      providers: [provideRouter(routes), { provide: AuthService, useValue: auth }],
    });
    const guard = routeFor('dashboard').canActivate?.[0] as CanActivateFn;
    const result = TestBed.runInInjectionContext(() =>
      guard({ data: {} } as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
    );

    expect(result).toEqual(TestBed.inject(Router).parseUrl('/login'));
    expect(auth.initialize).not.toHaveBeenCalled();
  });

  it('preserves application deep links while session initialization is pending', () => {
    const auth = { state: () => 'checking', session: () => null, initialize: vi.fn() };
    TestBed.configureTestingModule({
      providers: [provideRouter(routes), { provide: AuthService, useValue: auth }],
    });
    const guard = routeFor('dashboard').canActivate?.[0] as CanActivateFn;
    const result = TestBed.runInInjectionContext(() =>
      guard({ data: {} } as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
    );

    expect(result).toBe(true);
    expect(auth.initialize).not.toHaveBeenCalled();
  });

  it('redirects authenticated users away from the login screen', () => {
    const auth = {
      state: () => 'authenticated',
      session: () => ({ demo_role: null }),
      initialize: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [provideRouter(routes), { provide: AuthService, useValue: auth }],
    });
    const guard = routeFor('login').canActivate?.[0] as CanActivateFn;
    const result = TestBed.runInInjectionContext(() =>
      guard(
        { data: { auth: true } } as unknown as ActivatedRouteSnapshot,
        {} as RouterStateSnapshot,
      ),
    );

    expect(result).toEqual(TestBed.inject(Router).parseUrl('/dashboard'));
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
      number | UrlTree
    >;
    const route = {
      paramMap: convertToParamMap({ roundId: '7' }),
    } as ActivatedRouteSnapshot;

    TestBed.runInInjectionContext(() => resolver(route, {} as RouterStateSnapshot));

    expect(roundId()).toBe(7);
    expect(refresh).not.toHaveBeenCalled();
  });

  it('redirects invalid round deep links to their collection routes', () => {
    TestBed.configureTestingModule({ providers: [provideRouter(routes)] });
    const resolver = routeFor('scheduling-overview/:roundId').resolve?.['roundId'] as ResolveFn<
      number | UrlTree
    >;
    const planningRoute = {
      paramMap: convertToParamMap({ roundId: 'foo' }),
      routeConfig: { path: 'scheduling-overview/:roundId' },
    } as ActivatedRouteSnapshot;
    const confirmedPlansRoute = {
      paramMap: convertToParamMap({ roundId: '0' }),
      routeConfig: { path: 'confirmed-plans/:roundId' },
    } as ActivatedRouteSnapshot;

    const planningRedirect = TestBed.runInInjectionContext(() =>
      resolver(planningRoute, {} as RouterStateSnapshot),
    );
    const confirmedPlansRedirect = TestBed.runInInjectionContext(() =>
      resolver(confirmedPlansRoute, {} as RouterStateSnapshot),
    );
    const router = TestBed.inject(Router);

    expect(planningRedirect).toEqual(router.parseUrl('/scheduling-overview'));
    expect(confirmedPlansRedirect).toEqual(router.parseUrl('/confirmed-plans'));
  });

  it('preserves a protected round deep link while the initial session is established', async () => {
    const authState = signal<'checking' | 'authenticated'>('checking');
    let loadedRoundId: number | null = null;
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          {
            path: 'scheduling-overview/:roundId',
            component: RoundDeepLinkProbe,
            resolve: { roundId: roundContextResolver },
          },
        ]),
        { provide: AuthService, useValue: { state: authState } },
        { provide: PlanningWorkflowService, useValue: { resetForRoundChange: vi.fn() } },
        {
          provide: ApplicationWorkspaceService,
          useValue: {
            refresh: () => (loadedRoundId = TestBed.inject(RoundContextService).roundId()),
          },
        },
      ],
    });

    const router = TestBed.inject(Router);
    const scope = TestBed.inject(SessionScopeService);
    await router.navigateByUrl('/scheduling-overview/8');
    const route = router.routerState.root.firstChild;
    const roundContext = TestBed.inject(RoundContextService);

    expect(router.url).toBe('/scheduling-overview/8');
    expect(route?.snapshot.data['roundId']).toBe(8);
    expect(roundContext.roundId()).toBe(8);

    scope.establish({
      authenticated: true,
      account_id: 4,
      person_id: 9,
      committee_member_id: 12,
      is_operator: false,
    });
    authState.set('authenticated');
    TestBed.inject(ApplicationWorkspaceService).refresh();

    expect(router.url).toBe('/scheduling-overview/8');
    expect(route?.snapshot.data['roundId']).toBe(8);
    expect(roundContext.roundId()).toBe(8);
    expect(loadedRoundId).toBe(8);
  });
});

function routeFor(path: string): Route {
  const route = routes.find((candidate) => candidate.path === path);
  expect(route).toBeDefined();
  return route as Route;
}

@Component({ standalone: true, template: '' })
class RoundDeepLinkProbe {}
