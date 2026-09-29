import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject } from 'rxjs';

import type { ExamRound } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { UiFeedbackService } from './ui-feedback.service';
import { ApplicationWorkspaceService } from './application-workspace.service';

describe('ApplicationWorkspaceService', () => {
  let requests: Subject<unknown>[];
  let refreshDashboard: ReturnType<typeof vi.fn>;
  let feedback: { notify: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    requests = [];
    refreshDashboard = vi.fn(() => {
      const request = new Subject<unknown>();
      requests.push(request);
      return request;
    });
    feedback = { notify: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: PlanningApiService, useValue: { refreshDashboard } },
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

    expect(refreshDashboard).toHaveBeenNthCalledWith(1, 1);
    expect(refreshDashboard).toHaveBeenNthCalledWith(2, 2);
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
});

function dashboard(id: number, name: string) {
  return {
    root: { version: 'test' },
    round: { id, name, status: 'planning' } as ExamRound,
    summary: {},
    board: {},
    masterData: { committees: [] },
  };
}
