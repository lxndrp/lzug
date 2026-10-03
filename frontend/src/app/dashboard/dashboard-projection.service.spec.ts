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
  let loadCandidateReferences: ReturnType<typeof vi.fn>;
  let loadCommitteeMembers: ReturnType<typeof vi.fn>;

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
    loadCandidateReferences = vi.fn(() =>
      of({ candidates: planningBoardFixture.candidates, summary: summaryFixture }),
    );
    loadCommitteeMembers = vi.fn(() => of(planningBoardFixture.members));
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: AuthService, useValue: auth },
        {
          provide: DASHBOARD_PROJECTION_PORT,
          useValue: { load, loadLocations, loadCandidateReferences, loadCommitteeMembers },
        },
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

  it('reuses an in-flight projection for a round selected before dashboard route entry', () => {
    const pending = new Subject<never>();
    load.mockReturnValueOnce(pending);
    const service = TestBed.inject(DashboardProjectionService);

    service.refresh();
    service.refresh();

    expect(load).toHaveBeenCalledOnce();
    expect(service.loading()).toBe(true);
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

  it('keeps the newer targeted location read when an older full projection finishes later', () => {
    const service = TestBed.inject(DashboardProjectionService);
    service.refresh();
    const oldLocation = locationsFixture[0];
    const updatedLocation = { ...oldLocation, name: 'Aktualisierter Prüfungsort' };
    const staleProjection = {
      applicationVersion: 'test',
      round: examRoundFixture,
      summary: summaryFixture,
      board: { ...planningBoardFixture, locations: [oldLocation] },
    };
    const pending = new Subject<typeof staleProjection>();
    load.mockReturnValueOnce(pending);

    service.refresh();
    loadLocations.mockReturnValueOnce(of([updatedLocation]));
    service.refreshLocations();
    pending.next(staleProjection);
    pending.complete();

    expect(service.projection()?.board.locations[0].name).toBe('Aktualisierter Prüfungsort');
  });

  it('clears a targeted location error after a successful full projection read', () => {
    const service = TestBed.inject(DashboardProjectionService);
    service.refresh();
    loadLocations.mockReturnValueOnce(throwError(() => new Error('locations unavailable')));
    service.refreshLocations();
    expect(service.locationRefreshError()).toBe(true);

    service.refresh();

    expect(service.locationRefreshError()).toBe(false);
  });

  it('refreshes only dashboard candidate references and their round summary', () => {
    const service = TestBed.inject(DashboardProjectionService);
    service.refresh();
    const candidates = planningBoardFixture.candidates.map((item) => ({
      ...item,
      candidate: { ...item.candidate, first_name: 'Updated' },
    }));
    const summary = { ...summaryFixture, counts: { ...summaryFixture.counts, candidates: 8 } };
    loadCandidateReferences.mockReturnValueOnce(of({ candidates, summary }));

    service.refreshCandidateReferences();

    expect(load).toHaveBeenCalledOnce();
    expect(loadCandidateReferences).toHaveBeenCalledOnce();
    expect(loadCommitteeMembers).not.toHaveBeenCalled();
    expect(loadLocations).not.toHaveBeenCalled();
    expect(service.projection()?.board.candidates).toEqual(candidates);
    expect(service.projection()?.summary.counts.candidates).toBe(8);
    expect(service.candidateRefreshError()).toBe(false);
  });

  it('refreshes only dashboard committee member references', () => {
    const service = TestBed.inject(DashboardProjectionService);
    service.refresh();
    const members = planningBoardFixture.members.map((item) => ({
      ...item,
      first_name: 'Updated',
    }));
    loadCommitteeMembers.mockReturnValueOnce(of(members));

    service.refreshCommitteeMembers();

    expect(load).toHaveBeenCalledOnce();
    expect(loadCandidateReferences).not.toHaveBeenCalled();
    expect(loadCommitteeMembers).toHaveBeenCalledOnce();
    expect(service.projection()?.board.members).toEqual(members);
    expect(service.committeeRefreshError()).toBe(false);
  });

  it('preserves targeted candidate and member reads when an older dashboard load completes later', () => {
    const service = TestBed.inject(DashboardProjectionService);
    service.refresh();
    const staleProjection = {
      applicationVersion: 'test',
      round: examRoundFixture,
      summary: summaryFixture,
      board: planningBoardFixture,
    };
    const pending = new Subject<typeof staleProjection>();
    load.mockReturnValueOnce(pending);
    service.refresh();
    const candidates = planningBoardFixture.candidates.map((item) => ({
      ...item,
      candidate: { ...item.candidate, first_name: 'Updated' },
    }));
    const members = planningBoardFixture.members.map((item) => ({
      ...item,
      first_name: 'Updated',
    }));
    const summary = { ...summaryFixture, counts: { ...summaryFixture.counts, candidates: 9 } };
    loadCandidateReferences.mockReturnValueOnce(of({ candidates, summary }));
    loadCommitteeMembers.mockReturnValueOnce(of(members));
    service.refreshCandidateReferences();
    service.refreshCommitteeMembers();

    pending.next(staleProjection);
    pending.complete();

    expect(service.projection()?.board.candidates).toEqual(candidates);
    expect(service.projection()?.board.members).toEqual(members);
    expect(service.projection()?.summary.counts.candidates).toBe(9);
  });

  it('discards targeted master-data reads after the authenticated session changes', () => {
    const service = TestBed.inject(DashboardProjectionService);
    service.refresh();
    const pending = new Subject<{
      candidates: typeof planningBoardFixture.candidates;
      summary: typeof summaryFixture;
    }>();
    loadCandidateReferences.mockReturnValueOnce(pending);
    const scope = TestBed.inject(SessionScopeService);
    scope.establish({
      authenticated: true,
      account_id: 1,
      person_id: 2,
      committee_member_id: 3,
      is_operator: false,
    });
    service.refreshCandidateReferences();
    scope.clear();
    pending.next({ candidates: planningBoardFixture.candidates, summary: summaryFixture });

    expect(service.projection()).toBeNull();
    expect(service.candidateRefreshError()).toBe(false);
    expect(service.candidateRefreshLoading()).toBe(false);
  });

  it('keeps master-data refresh errors separate from the dashboard and each other', () => {
    const service = TestBed.inject(DashboardProjectionService);
    service.refresh();
    loadCandidateReferences.mockReturnValueOnce(
      throwError(() => new Error('candidate references unavailable')),
    );

    service.refreshCandidateReferences();

    expect(service.candidateRefreshError()).toBe(true);
    expect(service.committeeRefreshError()).toBe(false);
    expect(service.error()).toBe(false);
    expect(service.projection()).not.toBeNull();
  });
});
