import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject } from 'rxjs';

import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { UiFeedbackService } from './ui-feedback.service';
import { ApplicationWorkspaceService } from './application-workspace.service';
import { WORKSPACE_PORT } from './workspace.port';

describe('ApplicationWorkspaceService', () => {
  let requests: Subject<unknown>[];
  let loadDashboard: ReturnType<typeof vi.fn>;
  let feedback: { notify: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    requests = [];
    loadDashboard = vi.fn(() => {
      const request = new Subject<unknown>();
      requests.push(request);
      return request;
    });
    feedback = { notify: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: WORKSPACE_PORT, useValue: { loadDashboard } },
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
    workspace.refresh();
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
    workspace.refresh();
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
    workspace.refresh();
    requests[0].complete();

    expect(workspace.loading()).toBe(true);
    requests[1].next(dashboard(2, 'Runde B'));
    requests[1].complete();
    expect(workspace.loading()).toBe(false);
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
    workspace.selectedCommitteeId.set(6);
    workspace.refresh();

    scope.clear();
    requests[1].next(dashboard(8, 'Veraltete Antwort'));
    requests[1].complete();

    expect(workspace.round()).toBeNull();
    expect(workspace.masterData()).toBeNull();
    expect(workspace.candidateWorkspace()).toBeNull();
    expect(workspace.committeeWorkspace()).toBeNull();
    expect(workspace.selectedCommitteeId()).toBeNull();
    expect(context.roundId()).toBe(1);
    expect(workspace.loading()).toBe(false);
  });
});

function dashboard(id: number, name: string) {
  return {
    applicationVersion: 'test',
    round: { id, name, status: 'planning' },
    summary: {},
    board: {},
    masterData: { committees: [] },
    candidateWorkspace: {
      candidates: [],
      assignments: [],
      examRounds: [],
      committees: [],
      activeRound: null,
    },
    committeeWorkspace: { committees: [], members: [], persons: [] },
  };
}
