import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject, of } from 'rxjs';

import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { UiFeedbackService } from './ui-feedback.service';
import { ApplicationWorkspaceService } from './application-workspace.service';
import { WORKSPACE_PORT } from './workspace.port';
import { locationsFixture } from '../testing/fixtures';

describe('ApplicationWorkspaceService', () => {
  let requests: Subject<unknown>[];
  let loadDashboard: ReturnType<typeof vi.fn>;
  let loadLocations: ReturnType<typeof vi.fn>;
  let loadCandidateReferences: ReturnType<typeof vi.fn>;
  let loadCommitteeMembers: ReturnType<typeof vi.fn>;
  let feedback: { notify: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    requests = [];
    loadDashboard = vi.fn(() => {
      const request = new Subject<unknown>();
      requests.push(request);
      return request;
    });
    loadLocations = vi.fn(() => of([]));
    loadCandidateReferences = vi.fn(() => of({ candidates: [], candidateAssignments: [] }));
    loadCommitteeMembers = vi.fn(() => of([]));
    feedback = { notify: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        {
          provide: WORKSPACE_PORT,
          useValue: { loadDashboard, loadLocations, loadCandidateReferences, loadCommitteeMembers },
        },
        {
          provide: AuthService,
          useValue: { state: () => 'authenticated', markAnonymous: vi.fn() },
        },
        { provide: UiFeedbackService, useValue: feedback },
      ],
    });
  });

  it('keeps the newer round when overlapping refreshes finish out of order', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const context = TestBed.inject(RoundContextService);

    workspace.refresh();
    context.select(2);
    requests[1].next(dashboard(2, 'Runde B'));
    requests[1].complete();
    requests[0].next(dashboard(1, 'Runde A'));
    requests[0].complete();

    expect(loadDashboard).toHaveBeenNthCalledWith(1, 1);
    expect(loadDashboard).toHaveBeenNthCalledWith(2, 2);
    expect(workspace.round()?.id).toBe(2);
    expect(workspace.round()?.name).toBe('Runde B');
    expect(context.roundId()).toBe(workspace.round()?.id);
    expect(workspace.loading()).toBe(false);
  });

  it('ignores an obsolete refresh error and its feedback', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const context = TestBed.inject(RoundContextService);

    workspace.refresh();
    context.select(2);
    requests[1].next(dashboard(2, 'Runde B'));
    requests[1].complete();
    requests[0].error({ status: 500 });

    expect(workspace.round()?.id).toBe(2);
    expect(workspace.masterDataError()).toBe(false);
    expect(workspace.message()).toBe('Daten synchronisiert');
    expect(feedback.notify).not.toHaveBeenCalled();
  });

  it('does not clear loading when an obsolete request finalizes', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const context = TestBed.inject(RoundContextService);

    workspace.refresh();
    context.select(2);
    requests[0].complete();

    expect(workspace.loading()).toBe(true);
    requests[1].next(dashboard(2, 'Runde B'));
    requests[1].complete();
    expect(workspace.loading()).toBe(false);
  });

  it('replaces the shared workspace projection when a route resolver selects another round', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const context = TestBed.inject(RoundContextService);
    workspace.refresh();
    requests[0].next(dashboard(1, 'Runde A'));
    requests[0].complete();

    context.select(2);

    expect(workspace.round()).toBeNull();
    expect(workspace.board()).toBeNull();
    expect(loadDashboard).toHaveBeenLastCalledWith(2);
    requests[1].next(dashboard(2, 'Runde B'));
    requests[1].complete();
    expect(workspace.round()?.id).toBe(2);
  });

  it('updates cached location projections with a targeted read only', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    workspace.refresh();
    requests[0].next(dashboard(1, 'Runde A'));
    requests[0].complete();

    workspace.refreshLocations();

    expect(loadDashboard).toHaveBeenCalledOnce();
    expect(loadLocations).toHaveBeenCalledOnce();
  });

  it('preserves a newer targeted location read when an older full refresh finishes later', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const oldLocation = locationsFixture[0];
    const updatedLocation = { ...oldLocation, name: 'Aktualisierter Prüfungsort' };
    workspace.refresh();
    requests[0].next({
      ...dashboard(1, 'Runde A'),
      board: { days: [], locations: [oldLocation] },
      masterData: { committees: [], locations: [oldLocation] },
    });
    requests[0].complete();

    workspace.refresh();
    loadLocations.mockReturnValueOnce(of([updatedLocation]));
    workspace.refreshLocations();
    requests[1].next({
      ...dashboard(1, 'Runde A'),
      board: { days: [], locations: [oldLocation] },
      masterData: { committees: [], locations: [oldLocation] },
    });
    requests[1].complete();

    expect(workspace.board()?.locations[0].name).toBe('Aktualisierter Prüfungsort');
    expect(workspace.masterData()?.locations[0].name).toBe('Aktualisierter Prüfungsort');
  });

  it('updates only the candidate references used by the transitional planning workspace', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    workspace.refresh();
    requests[0].next(dashboard(1, 'Runde A'));
    requests[0].complete();
    const candidates = [{ candidate: { id: 7 }, roundCandidate: null }];
    const candidateAssignments = [{ id: 8 }];
    loadCandidateReferences.mockReturnValueOnce(of({ candidates, candidateAssignments }));

    workspace.refreshCandidateReferences();

    expect(loadCandidateReferences).toHaveBeenCalledWith(1);
    expect(workspace.board()?.candidates).toEqual(candidates);
    expect(workspace.masterData()?.candidates).toEqual(candidates);
    expect(workspace.masterData()?.candidateAssignments).toEqual(candidateAssignments);
    expect(loadDashboard).toHaveBeenCalledOnce();
  });

  it('loads selected-round candidate references before the workspace snapshot exists', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const context = TestBed.inject(RoundContextService);
    const candidates = [{ candidate: { id: 7 }, roundCandidate: null }];
    const candidateAssignments = [{ id: 8 }];
    context.select(2);
    loadCandidateReferences.mockReturnValueOnce(of({ candidates, candidateAssignments }));

    workspace.refreshCandidateReferences(2);

    expect(loadCandidateReferences).toHaveBeenCalledWith(2);
    expect(workspace.candidateReferenceSnapshot()).toEqual({
      roundId: 2,
      candidates,
      candidateAssignments,
    });
    expect(workspace.masterData()).toBeNull();
    expect(loadDashboard).toHaveBeenCalledOnce();
    expect(loadDashboard).toHaveBeenCalledWith(2);
  });

  it('keeps targeted references out of a workspace snapshot for another round', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const context = TestBed.inject(RoundContextService);
    const roundOneCandidates = [{ candidate: { id: 1 }, roundCandidate: null }];
    const roundOneAssignments = [{ id: 10 }];
    const roundTwoCandidates = [{ candidate: { id: 2 }, roundCandidate: null }];
    const roundTwoAssignments = [{ id: 20 }];
    workspace.refresh();
    requests[0].next({
      ...dashboard(1, 'Runde A'),
      board: { days: [], locations: [], candidates: roundOneCandidates },
      masterData: {
        committees: [],
        locations: [],
        candidates: roundOneCandidates,
        candidateAssignments: roundOneAssignments,
      },
    });
    requests[0].complete();
    context.select(2);
    loadCandidateReferences.mockReturnValueOnce(
      of({ candidates: roundTwoCandidates, candidateAssignments: roundTwoAssignments }),
    );

    workspace.refreshCandidateReferences(2);

    expect(workspace.candidateReferenceSnapshot()).toEqual({
      roundId: 2,
      candidates: roundTwoCandidates,
      candidateAssignments: roundTwoAssignments,
    });
    expect(workspace.board()).toBeNull();
    expect(workspace.masterData()).toBeNull();
    expect(loadDashboard).toHaveBeenLastCalledWith(2);
  });

  it('updates only committee members in the transitional planning workspace', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    workspace.refresh();
    requests[0].next(dashboard(1, 'Runde A'));
    requests[0].complete();
    const members = [{ id: 9, committee_id: 3 }];
    loadCommitteeMembers.mockReturnValueOnce(of(members));

    workspace.refreshCommitteeReferences();

    expect(loadCommitteeMembers).toHaveBeenCalledOnce();
    expect(workspace.board()?.members).toEqual(members);
    expect(workspace.masterData()?.members).toEqual(members);
    expect(loadDashboard).toHaveBeenCalledOnce();
  });

  it('clears cached workspace and ignores a response from the previous session', () => {
    const workspace = TestBed.inject(ApplicationWorkspaceService);
    const context = TestBed.inject(RoundContextService);
    const scope = TestBed.inject(SessionScopeService);
    scope.establish({
      authenticated: true,
      account_id: 3,
      person_id: 5,
      committee_member_id: 6,
      is_operator: false,
    });

    workspace.refresh();
    requests[0].next(dashboard(1, 'Vorherige Runde'));
    requests[0].complete();
    context.select(8);
    workspace.refresh();

    scope.clear();
    requests[1].next(dashboard(8, 'Veraltete Antwort'));
    requests[1].complete();

    expect(workspace.round()).toBeNull();
    expect(workspace.masterData()).toBeNull();
    expect(context.roundId()).toBe(1);
    expect(workspace.loading()).toBe(false);
  });
});

function dashboard(id: number, name: string) {
  return {
    applicationVersion: 'test',
    round: { id, name, status: 'planning' },
    summary: {},
    board: { days: [], locations: [] },
    masterData: { committees: [], locations: [] },
  };
}
