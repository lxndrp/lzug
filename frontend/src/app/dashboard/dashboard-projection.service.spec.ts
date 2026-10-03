import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import {
  examRoundFixture,
  locationsFixture,
  planningBoardFixture,
  summaryFixture,
} from '../testing/fixtures';
import { DASHBOARD_PROJECTION_PORT } from './dashboard-projection.port';
import { DashboardProjectionService } from './dashboard-projection.service';

describe('DashboardProjectionService', () => {
  const auth = { state: () => 'authenticated', markAnonymous: vi.fn() };
  let load: ReturnType<typeof vi.fn>;
  let loadLocations: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    load = vi.fn(() =>
      of({
        applicationVersion: 'test',
        round: examRoundFixture,
        summary: summaryFixture,
        board: planningBoardFixture,
      }),
    );
    loadLocations = vi.fn(() => of(locationsFixture));
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: AuthService, useValue: auth },
        { provide: DASHBOARD_PROJECTION_PORT, useValue: { load, loadLocations } },
      ],
    });
  });

  it('loads an independent projection and exposes its own failure state', () => {
    load.mockReturnValueOnce(throwError(() => new Error('dashboard unavailable')));
    const service = TestBed.inject(DashboardProjectionService);

    service.refresh();

    expect(service.error()).toBe(true);
    expect(service.projection()).toBeNull();
    expect(loadLocations).not.toHaveBeenCalled();
  });

  it('ignores a projection response after the authenticated session changes', () => {
    const pending = new Subject<never>();
    load.mockReturnValueOnce(pending);
    const service = TestBed.inject(DashboardProjectionService);
    const scope = TestBed.inject(SessionScopeService);
    scope.establish({
      authenticated: true,
      account_id: 1,
      person_id: 2,
      committee_member_id: 3,
      is_operator: false,
    });

    service.refresh();
    scope.clear();
    pending.next({
      applicationVersion: 'stale',
      round: examRoundFixture,
      summary: summaryFixture,
      board: planningBoardFixture,
    } as never);

    expect(service.projection()).toBeNull();
    expect(service.loading()).toBe(false);
  });

  it('refreshes only locations in the loaded dashboard and updates day references', () => {
    const service = TestBed.inject(DashboardProjectionService);
    service.refresh();
    const initialBoard = service.projection()!.board;
    const firstLocation = locationsFixture[0];
    const updatedLocation = { ...firstLocation, name: 'Updated venue' };
    loadLocations.mockReturnValueOnce(of([updatedLocation]));

    service.refreshLocations();

    expect(load).toHaveBeenCalledOnce();
    expect(loadLocations).toHaveBeenCalledOnce();
    expect(service.projection()!.board.locations[0].name).toBe('Updated venue');
    expect(service.projection()!.board.days).not.toBe(initialBoard.days);
    expect(service.error()).toBe(false);
  });

  it('keeps a location refresh error separate from the dashboard read error', () => {
    const service = TestBed.inject(DashboardProjectionService);
    service.refresh();
    loadLocations.mockReturnValueOnce(throwError(() => new Error('locations unavailable')));

    service.refreshLocations();

    expect(service.locationRefreshError()).toBe(true);
    expect(service.error()).toBe(false);
    expect(service.projection()).not.toBeNull();
  });
});
