import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { ConfirmedPlansRouteComponent } from './confirmed-plans-route.component';

describe('ConfirmedPlansRouteComponent', () => {
  it('passes the requested round and edit capability to the feature component', () => {
    const params = convertToParamMap({ roundId: '2' });
    TestBed.configureTestingModule({
      providers: [
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: of(params),
            snapshot: {
              paramMap: params,
              routeConfig: { path: 'confirmed-plans/:roundId/edit' },
            },
          },
        },
        { provide: AuthService, useValue: { hasCapability: () => true } },
      ],
    });

    const route = TestBed.runInInjectionContext(
      () => new ConfirmedPlansRouteComponent(),
    ) as unknown as {
      roundId: () => number | null;
      editRoundId: () => number | null;
      canEdit: () => boolean;
    };

    expect(route.roundId()).toBe(2);
    expect(route.editRoundId()).toBe(2);
    expect(route.canEdit()).toBe(true);
  });

  it('leaves reference loading to the confirmed-plans feature port', () => {
    const params = convertToParamMap({ roundId: '2' });
    TestBed.configureTestingModule({
      providers: [
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: of(params),
            snapshot: {
              paramMap: params,
              routeConfig: { path: 'confirmed-plans/:roundId' },
            },
          },
        },
        { provide: AuthService, useValue: { hasCapability: () => false } },
      ],
    });

    const route = TestBed.runInInjectionContext(() => new ConfirmedPlansRouteComponent()) as object;
    expect(route).not.toHaveProperty('workspace');
    expect(route).not.toHaveProperty('confirmedPlansBoard');
  });
});
