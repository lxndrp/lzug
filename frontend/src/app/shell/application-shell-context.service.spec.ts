import { TestBed } from '@angular/core/testing';
import { of, Subject, throwError } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { RoundContextService } from '../api/round-context.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { APPLICATION_SHELL_CONTEXT_PORT } from './application-shell-context.port';
import { ApplicationShellContextService } from './application-shell-context.service';
import { PlanningWriteEventsService } from '../application/planning-write-events.service';

describe('ApplicationShellContextService', () => {
  const context = {
    applicationVersion: 'test',
    roundId: 1,
    halfYear: 'Winter 2026',
    round: 'Runde 1',
    committee: 'Ausschuss A',
    status: 'planning',
  };
  let load: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    load = vi.fn((roundId = 1) => of({ ...context, roundId }));
    TestBed.configureTestingModule({
      providers: [
        {
          provide: AuthService,
          useValue: { state: () => 'authenticated', markAnonymous: vi.fn() },
        },
        { provide: APPLICATION_SHELL_CONTEXT_PORT, useValue: { load } },
      ],
    });
  });

  it('loads compact context labels and reports its own read failure', () => {
    load.mockReturnValueOnce(throwError(() => new Error('context read failed')));
    const service = TestBed.inject(ApplicationShellContextService);

    service.refresh();

    expect(service.error()).toBe(true);
    expect(service.context()).toBeNull();
  });

  it('clears context and ignores old responses when the session changes', () => {
    const pending = new Subject<typeof context>();
    load.mockReturnValueOnce(pending);
    const service = TestBed.inject(ApplicationShellContextService);
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
    pending.next(context);

    expect(service.context()).toBeNull();
    expect(service.loading()).toBe(false);
  });

  it('captures and fences the selected round', () => {
    const service = TestBed.inject(ApplicationShellContextService);
    const roundContext = TestBed.inject(RoundContextService);
    roundContext.select(4);

    service.refresh();

    expect(load).toHaveBeenCalledWith(4);
    expect(service.context()).toMatchObject({ roundId: 4 });
  });

  it('reloads shell labels after same-round partial and complete planning commits', () => {
    const service = TestBed.inject(ApplicationShellContextService);
    service.refresh();
    load.mockReturnValueOnce(of({ ...context, round: 'Runde nach Teilcommit' }));

    TestBed.inject(PlanningWriteEventsService).notifyCommitted(1, 'round', 'partial');

    expect(load).toHaveBeenCalledTimes(2);
    expect(service.context()?.round).toBe('Runde nach Teilcommit');

    load.mockReturnValueOnce(of({ ...context, round: 'Runde nach Commit' }));
    TestBed.inject(PlanningWriteEventsService).notifyCommitted(1, 'round', 'complete');

    expect(load).toHaveBeenCalledTimes(3);
    expect(service.context()?.round).toBe('Runde nach Commit');
  });
});
