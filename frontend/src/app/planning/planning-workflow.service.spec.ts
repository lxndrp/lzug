import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { Observable, Subject, of, throwError } from 'rxjs';

import type {
  CandidateExamDay,
  EditablePlanningProposal,
  PlanningSnapshot,
} from './planning.models';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { ApplicationShellContextService } from '../shell/application-shell-context.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import { PLANNING_PORT } from './planning.port';
import { PlanningWorkflowService } from './planning-workflow.service';

describe('PlanningWorkflowService', () => {
  it('loads a feature-owned snapshot for the route round', () => {
    const { workflow, port, roundId } = createHarness();
    const view = Symbol('planning-view');

    roundId.set(8);
    workflow.activateView(view, 8);

    expect(port.loadPlanning).toHaveBeenCalledWith(8);
    expect(workflow.snapshot()?.round.id).toBe(8);
    expect(workflow.snapshot()?.board).toEqual(emptySnapshot(8).board);
  });

  it('reloads only the active planning view on an application refresh', () => {
    const { workflow, port, roundId } = createHarness();
    const view = Symbol('planning-view');
    roundId.set(8);
    workflow.activateView(view, 8);

    workflow.refreshActiveView();

    expect(port.loadPlanning).toHaveBeenCalledTimes(2);
    expect(port.loadPlanning).toHaveBeenLastCalledWith(8);
    workflow.deactivateView(view);
    workflow.refreshActiveView();
    expect(port.loadPlanning).toHaveBeenCalledTimes(2);
  });

  it('redirects a stale planning deep link when the round is already confirmed', () => {
    const { workflow } = createHarness({
      loadPlanning: vi.fn((id: number) =>
        of({
          ...emptySnapshot(id),
          round: { ...emptySnapshot(id).round, status: 'plan_confirmed' },
        }),
      ),
    });
    const router = TestBed.inject(Router);
    const navigateByUrl = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);

    workflow.activateView(Symbol('planning-view'), 1);

    expect(navigateByUrl).toHaveBeenCalledWith('/confirmed-plans/1', { replaceUrl: true });
    expect(workflow.snapshot()).toBeNull();
  });

  it('keeps an accepted mutation bound to its captured round after selection changes', () => {
    const response = new Subject<unknown>();
    const { workflow, port, roundId } = createHarness({
      updateExamRound: vi.fn(() => response),
    });
    const view = Symbol('planning-view');
    const values = {
      name: 'Runde aktualisiert',
      availability_deadline: null,
      availability_reminder_at: null,
    };

    workflow.activateView(view, 1);
    workflow.saveExamRound(values, 1, view);
    roundId.set(2);
    workflow.activateView(view, 2);
    response.next({ id: 1 });
    response.complete();

    expect(port.updateExamRound).toHaveBeenCalledWith(values, 1);
    expect(workflow.snapshot()?.round.id).toBe(2);
  });

  it('passes the proposal source revision and round ID through the port', () => {
    const response = new Subject<EditablePlanningProposal>();
    const { workflow, port } = createHarness({ savePlanningProposal: vi.fn(() => response) });
    const view = Symbol('planning-view');
    const proposal: EditablePlanningProposal = {
      round_id: 1,
      revision: 17,
      exam_days: [],
    };

    workflow.activateView(view, 1);
    workflow.savePlanningProposal(proposal, 1, view);

    expect(port.savePlanningProposal).toHaveBeenCalledWith(1, {
      ...proposal,
      revision: 17,
    });
    response.next({ ...proposal, revision: 18 });
    response.complete();
    expect(workflow.proposal()?.revision).toBe(18);
  });

  it('does not let a late proposal answer replace a later view draft', () => {
    const saveResponse = new Subject<EditablePlanningProposal>();
    const proposalResponses: Subject<EditablePlanningProposal>[] = [];
    const proposal = { round_id: 1, revision: 3, exam_days: [] };
    const { workflow, port } = createHarness({
      loadPlanning: vi.fn((id: number) =>
        of({
          ...emptySnapshot(id),
          round: { ...emptySnapshot(id).round, status: 'plan_proposed' },
        }),
      ),
      getPlanningProposal: vi.fn(() => {
        const response = new Subject<EditablePlanningProposal>();
        proposalResponses.push(response);
        return response;
      }),
      savePlanningProposal: vi.fn(() => saveResponse),
    });
    const viewA = Symbol('planning-view-a');
    const viewB = Symbol('planning-view-b');
    const staleCommand = { ...proposal, revision: 7 };

    workflow.activateView(viewA, 1);
    proposalResponses[0]!.next(proposal);
    proposalResponses[0]!.complete();
    workflow.savePlanningProposal(staleCommand, 1, viewA);
    workflow.activateView(viewB, 1);
    proposalResponses[1]!.next({ ...proposal, revision: 7 });
    proposalResponses[1]!.complete();
    const viewBProposal = workflow.proposal();
    saveResponse.next({ ...staleCommand, revision: 8 });
    saveResponse.complete();

    expect(port.savePlanningProposal).toHaveBeenCalledWith(1, staleCommand);
    expect(workflow.proposal()).toBe(viewBProposal);
    expect(port.getPlanningProposal).toHaveBeenCalledTimes(3);
    proposalResponses[2]!.next({ ...proposal, revision: 8 });
    proposalResponses[2]!.complete();
    expect(workflow.proposal()?.revision).toBe(8);
  });

  it('holds pending through confirmation and the resulting mutation', () => {
    const confirmation = new Subject<boolean>();
    const response = new Subject<unknown>();
    const feedback = {
      notify: vi.fn(),
      roleRestriction: vi.fn(),
      confirm$: vi.fn(() => confirmation),
    };
    const { workflow, port } = createHarness({ confirmPlan: vi.fn(() => response) }, feedback);
    const view = Symbol('planning-view');

    workflow.activateView(view, 1);
    workflow.requestPlanConfirmation(1, view);
    workflow.requestPlanConfirmation(1, view);
    expect(workflow.actionBusy()).toBe(true);

    confirmation.next(true);
    confirmation.complete();
    expect(port.confirmPlan).toHaveBeenCalledWith(1);
    expect(workflow.actionBusy()).toBe(true);

    response.next({ counts: { confirmed_slots: 4 } });
    response.complete();
    expect(workflow.actionBusy()).toBe(false);
    expect(feedback.confirm$).toHaveBeenCalledOnce();
  });

  it('keeps a confirmation result in its source view after navigation', () => {
    const confirmation = new Subject<boolean>();
    const response = new Subject<{ counts: Record<string, number> }>();
    const feedback = {
      notify: vi.fn(),
      roleRestriction: vi.fn(),
      confirm$: vi.fn(() => confirmation),
    };
    const { workflow, port } = createHarness({ confirmPlan: vi.fn(() => response) }, feedback);
    const viewA = Symbol('planning-view-a');
    const viewB = Symbol('planning-view-b');

    workflow.activateView(viewA, 1);
    workflow.requestPlanConfirmation(1, viewA);
    confirmation.next(true);
    confirmation.complete();
    expect(port.confirmPlan).toHaveBeenCalledWith(1);

    workflow.activateView(viewB, 1);
    const viewBSnapshot = workflow.snapshot();
    response.next({ counts: { confirmed_slots: 4 } });
    response.complete();

    expect(workflow.snapshot()).toBe(viewBSnapshot);
    expect(workflow.lastResult()).toBeNull();
    expect(workflow.actionBusy()).toBe(false);
  });

  it('updates the planning-owned availability projection from the accepted response', () => {
    const response = new Subject<{
      id: number;
      committee_member_id: number;
      candidate_exam_day_id: number;
      availability: string;
    }>();
    const { workflow, port } = createHarness({ saveMemberAvailability: vi.fn(() => response) });
    const view = Symbol('planning-view');
    const command = {
      committee_member_id: 11,
      candidate_exam_day_id: 21,
      availability: 'morning',
    } as const;

    workflow.activateView(view, 1);
    workflow.saveAvailability(command, 1, view);
    response.next({ id: 4, ...command });

    expect(port.saveMemberAvailability).toHaveBeenCalledWith(command, 1);
    expect(workflow.snapshot()?.board.availabilities).toEqual([{ id: 4, ...command }]);
    expect(workflow.viewEffects().map((effect) => effect.type)).toEqual(['availability-saved']);
  });

  it('cancels route reads when the route is rebound to another round', () => {
    const requests: Subject<PlanningSnapshot>[] = [];
    const { workflow, port } = createHarness({
      loadPlanning: vi.fn(() => {
        const request = new Subject<PlanningSnapshot>();
        requests.push(request);
        return request;
      }),
    });
    const view = Symbol('planning-view');

    workflow.activateView(view, 1);
    const oldRequest = requests[0]!;
    TestBed.inject(RoundContextService).select(2);
    workflow.activateView(view, 2);
    const currentRequest = requests[1]!;
    expect(oldRequest.observed).toBe(false);

    oldRequest.next(emptySnapshot(1));
    currentRequest.next(emptySnapshot(2));

    expect(port.loadPlanning).toHaveBeenNthCalledWith(1, 1);
    expect(port.loadPlanning).toHaveBeenNthCalledWith(2, 2);
    expect(workflow.snapshot()?.round.id).toBe(2);
  });

  it('shows a load error and retries the active route when activated again', () => {
    const { workflow, port } = createHarness({
      loadPlanning: vi
        .fn()
        .mockReturnValueOnce(throwError(() => new Error('offline')))
        .mockReturnValueOnce(of(emptySnapshot(1))),
    });
    const view = Symbol('planning-view');

    workflow.activateView(view, 1);

    expect(workflow.loadError()).toBe(true);
    expect(workflow.snapshot()).toBeNull();

    workflow.activateView(view, 1);

    expect(port.loadPlanning).toHaveBeenCalledTimes(2);
    expect(workflow.loadError()).toBe(false);
    expect(workflow.snapshot()?.round.id).toBe(1);
  });

  it('disables commands when a mutation refresh fails and keeps the stale snapshot visible', () => {
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn(), confirm$: vi.fn(() => of(true)) };
    const { workflow, port } = createHarness(
      {
        loadPlanning: vi
          .fn()
          .mockReturnValueOnce(of(emptySnapshot(1)))
          .mockReturnValueOnce(throwError(() => new Error('offline'))),
      },
      feedback,
    );
    const view = Symbol('planning-view');
    const day: CandidateExamDay = { id: 31, exam_round_id: 1, date: '2027-01-11', is_active: 0 };

    workflow.activateView(view, 1);
    workflow.toggleCandidateDay(day, 1, view);
    expect(port.updateCandidateExamDay).toHaveBeenCalledTimes(1);
    expect(workflow.snapshot()?.round.id).toBe(1);
    expect(workflow.loadError()).toBe(true);
    expect(workflow.actionBusy()).toBe(true);

    workflow.toggleCandidateDay(day, 1, view);

    expect(port.updateCandidateExamDay).toHaveBeenCalledTimes(1);
    expect(feedback.notify).toHaveBeenCalledWith(
      'error',
      'Prüfungsdaten nicht aktualisiert',
      expect.any(String),
    );
  });

  it('clears planning state when a session ends and reloads after it is established', () => {
    const sessionChanges = new Subject<{ previousEstablished: boolean; established: boolean }>();
    const { workflow, port } = createHarness({
      sessionScopeChanges: sessionChanges,
    });
    const view = Symbol('planning-view');

    workflow.activateView(view, 1);
    workflow.generateProposal(1, view);
    expect(workflow.snapshot()).not.toBeNull();

    sessionChanges.next({ previousEstablished: true, established: false });

    expect(workflow.snapshot()).toBeNull();
    expect(workflow.lastResult()).toBeNull();
    expect(port.loadPlanning).toHaveBeenCalledTimes(2);

    sessionChanges.next({ previousEstablished: false, established: true });

    expect(port.loadPlanning).toHaveBeenCalledTimes(3);
    expect(workflow.snapshot()?.round.id).toBe(1);
  });

  it('cancels feature reads when the planning route is deactivated', () => {
    const response = new Subject<PlanningSnapshot>();
    const { workflow } = createHarness({ loadPlanning: vi.fn(() => response) });
    const view = Symbol('planning-view');

    workflow.activateView(view, 1);
    workflow.deactivateView(view);
    response.next(emptySnapshot(1));

    expect(response.observed).toBe(false);
    expect(workflow.snapshot()).toBeNull();
  });
});

function createHarness(
  overrides: Record<string, unknown> = {},
  feedbackOverrides: Record<string, unknown> = {},
) {
  const roundId = signal(1);
  const sessionChanges =
    (overrides['sessionScopeChanges'] as Subject<unknown> | undefined) ?? new Subject<unknown>();
  const sessionScope = {
    generation: () => 0,
    changes$: sessionChanges,
    forCurrentSession: <T>(operation: Observable<T>) => operation,
  };
  const roundContext = {
    roundId,
    select: (id: number) => roundId.set(id),
  };
  const proposal = { round_id: 1, revision: 2, exam_days: [] };
  const port = {
    loadPlanning: vi.fn((id: number) => of(emptySnapshot(id))),
    savePlanningSettings: vi.fn(() => of({})),
    updateExamRound: vi.fn(() => of({})),
    requestAvailabilities: vi.fn(() => of({ notification_warning: null })),
    createCandidateExamDay: vi.fn(() => of({ id: 1, exam_round_id: 1, date: '', is_active: 1 })),
    generateCandidateExamDays: vi.fn(() => of({ counts: { created: 0, existing: 0 } })),
    updateCandidateExamDay: vi.fn(() => of({})),
    saveMemberAvailability: vi.fn(() => of({ id: 1 })),
    generateProposal: vi.fn(() => of({ counts: {} })),
    confirmPlan: vi.fn(() => of({ counts: {} })),
    getPlanningProposal: vi.fn(() => of(proposal)),
    savePlanningProposal: vi.fn(() => of(proposal)),
    ...overrides,
  };
  const feedback = {
    notify: vi.fn(),
    roleRestriction: vi.fn(),
    confirm$: vi.fn(() => of(true)),
    ...feedbackOverrides,
  };

  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: RoundContextService, useValue: roundContext },
      { provide: SessionScopeService, useValue: sessionScope },
      { provide: ApplicationShellContextService, useValue: { refresh: vi.fn() } },
      { provide: PLANNING_PORT, useValue: port },
      { provide: AuthService, useValue: { hasCapability: () => true, session: () => null } },
      { provide: UiFeedbackService, useValue: feedback },
    ],
  });

  return {
    workflow: TestBed.inject(PlanningWorkflowService),
    port,
    feedback,
    roundId,
  };
}

function emptySnapshot(id: number): PlanningSnapshot {
  return {
    round: {
      id,
      exam_half_year_id: 4,
      name: `Runde ${id}`,
      committee_id: 3,
      status: 'draft',
      availability_deadline: null,
      availability_reminder_at: null,
    },
    summary: {
      round: { id, name: `Runde ${id}`, status: 'draft', committee_name: 'Ausschuss' },
      counts: { candidates: 0, mep_count: 0, required_exam_slots: 0 },
      settings: null,
      availability: [],
    },
    board: {
      days: [],
      members: [],
      candidates: [],
      candidateDays: [],
      availabilities: [],
      locations: [],
    },
  };
}
