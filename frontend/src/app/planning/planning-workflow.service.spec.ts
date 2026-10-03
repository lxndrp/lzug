import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { Observable, Subject, of, throwError } from 'rxjs';

import type { EditablePlanningProposal, PlanningSnapshot } from './planning.models';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { ApplicationShellContextService } from '../shell/application-shell-context.service';
import { PlanningWriteEventsService } from '../application/planning-write-events.service';
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

  it('publishes an accepted write after its planning route has exited', () => {
    const response = new Subject<unknown>();
    const { workflow, port } = createHarness({ updateExamRound: vi.fn(() => response) });
    const writeEvents = TestBed.inject(PlanningWriteEventsService);
    const committed = vi.fn();
    writeEvents.committed$.subscribe(committed);
    const view = Symbol('planning-route-activation');

    workflow.activateView(view, 1);
    workflow.saveExamRound(
      { name: 'Runde aktualisiert', availability_deadline: null, availability_reminder_at: null },
      1,
      view,
    );
    workflow.deactivateView(view);
    response.next({ id: 1 });
    response.complete();

    expect(port.updateExamRound).toHaveBeenCalledOnce();
    expect(committed).toHaveBeenCalledWith({
      sourceRoundId: 1,
      scope: 'round',
      phase: 'complete',
    });
    expect(workflow.snapshot()).toBeNull();
  });

  it('publishes the round metadata commit if availability dispatch then fails', () => {
    const { workflow, port } = createHarness({
      updateExamRound: vi.fn(() => of({ id: 1 })),
      sendAvailabilityRequests: vi.fn(() => throwError(() => new Error('dispatch failed'))),
    });
    const committed = vi.fn();
    TestBed.inject(PlanningWriteEventsService).committed$.subscribe(committed);
    const view = Symbol('planning-route-activation');
    workflow.activateView(view, 1);

    workflow.requestAvailabilities(
      { name: 'Runde', availability_deadline: null, availability_reminder_at: null },
      1,
      view,
    );

    expect(committed).toHaveBeenCalledWith({
      sourceRoundId: 1,
      scope: 'round',
      phase: 'partial',
    });
    expect(port.loadPlanning).toHaveBeenCalledTimes(2);
  });

  it('publishes the settings commit if candidate-day generation then fails', () => {
    const { workflow, port } = createHarness({
      savePlanningSettings: vi.fn(() => of({})),
      generateCandidateExamDays: vi.fn(() => throwError(() => new Error('generation failed'))),
    });
    const committed = vi.fn();
    TestBed.inject(PlanningWriteEventsService).committed$.subscribe(committed);
    const view = Symbol('planning-route-activation');
    workflow.activateView(view, 1);

    workflow.generateCandidateDays(
      {
        calendar_week_from: '2026-W40',
        calendar_week_to: '2026-W41',
        exams_per_day: 4,
        max_exam_days_per_week: 2,
      },
      1,
      view,
    );

    expect(committed).toHaveBeenCalledWith({
      sourceRoundId: 1,
      scope: 'round',
      phase: 'partial',
    });
    expect(port.loadPlanning).toHaveBeenCalledTimes(2);
  });

  it('clears prior-round workflow reports when the resolved round context changes', () => {
    const { workflow, roundContext } = createHarness();
    const view = Symbol('planning-route-activation');
    workflow.activateView(view, 1);
    workflow.generateProposal(1, view);
    expect(workflow.lastResult()).not.toBeNull();

    roundContext.select(2);

    expect(workflow.snapshot()).toBeNull();
    expect(workflow.lastResult()).toBeNull();
  });

  it('keeps the planning result available after leaving the planning route', () => {
    const { workflow } = createHarness();
    const view = Symbol('planning-route-activation');
    workflow.activateView(view, 1);
    workflow.generateProposal(1, view);
    const result = workflow.lastResult();

    workflow.deactivateView(view);

    expect(workflow.lastResult()).toBe(result);
  });

  it('reloads round B after a late availability write from round A', () => {
    const response = new Subject<{
      id: number;
      committee_member_id: number;
      candidate_exam_day_id: number;
      availability: string;
    }>();
    const snapshots = [
      emptySnapshot(1),
      emptySnapshot(2),
      {
        ...emptySnapshot(2),
        round: { ...emptySnapshot(2).round, name: 'Runde 2 nach Spiegelung' },
      },
    ];
    const { workflow, port, roundContext } = createHarness({
      loadPlanning: vi.fn(() => of(snapshots.shift()!)),
      saveMemberAvailability: vi.fn(() => response),
    });
    const viewA = Symbol('round-a-view');
    const viewB = Symbol('round-b-view');
    const availability = {
      committee_member_id: 11,
      candidate_exam_day_id: 21,
      availability: 'morning',
    };

    workflow.activateView(viewA, 1);
    workflow.saveAvailability(availability, 1, viewA);
    roundContext.select(2);
    workflow.activateView(viewB, 2);
    response.next({ id: 7, ...availability });
    response.complete();

    expect(port.loadPlanning.mock.calls.map(([id]) => id)).toEqual([1, 2, 2]);
    expect(workflow.snapshot()?.round.name).toBe('Runde 2 nach Spiegelung');
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

    expect(workflow.proposalSaveAcknowledgement()).toBe(0);
    expect(port.savePlanningProposal).toHaveBeenCalledWith(1, {
      ...proposal,
      revision: 17,
    });
    response.next({ ...proposal, revision: 18 });
    response.complete();
    expect(workflow.proposal()?.revision).toBe(18);
    expect(workflow.proposalSaveAcknowledgement()).toBe(1);
  });

  it('does not let a proposal read started before an accepted save replace its response', () => {
    const readResponse = new Subject<EditablePlanningProposal>();
    const saveResponse = new Subject<EditablePlanningProposal>();
    const proposal = { round_id: 1, revision: 3, exam_days: [] };
    const { workflow, port } = createHarness({
      loadPlanning: vi.fn(() =>
        of({
          ...emptySnapshot(1),
          round: { ...emptySnapshot(1).round, status: 'plan_proposed' },
        }),
      ),
      getPlanningProposal: vi.fn(() => readResponse),
      savePlanningProposal: vi.fn(() => saveResponse),
    });
    const view = Symbol('planning-view');
    const savedProposal = { ...proposal, revision: 4 };

    workflow.activateView(view, 1);
    expect(port.getPlanningProposal).toHaveBeenCalledOnce();
    workflow.savePlanningProposal(proposal, 1, view);
    saveResponse.next(savedProposal);
    saveResponse.complete();
    readResponse.next(proposal);
    readResponse.complete();

    expect(port.getPlanningProposal).toHaveBeenCalledOnce();
    expect(workflow.proposal()).toEqual(savedProposal);
    expect(workflow.editorState()).toBe('ready');
    expect(workflow.proposalSaveAcknowledgement()).toBe(1);
  });

  it('fences an active view proposal read after a save from an older view is accepted', () => {
    const proposalReadA = new Subject<EditablePlanningProposal>();
    const proposalReadB = new Subject<EditablePlanningProposal>();
    const saveResponse = new Subject<EditablePlanningProposal>();
    const refreshResponse = new Subject<PlanningSnapshot>();
    const proposedSnapshot = {
      ...emptySnapshot(1),
      round: { ...emptySnapshot(1).round, status: 'plan_proposed' },
    } satisfies PlanningSnapshot;
    const { workflow, port } = createHarness({
      loadPlanning: vi
        .fn()
        .mockReturnValueOnce(of(proposedSnapshot))
        .mockReturnValueOnce(of(proposedSnapshot))
        .mockReturnValueOnce(refreshResponse),
      getPlanningProposal: vi
        .fn()
        .mockReturnValueOnce(proposalReadA)
        .mockReturnValueOnce(proposalReadB),
      savePlanningProposal: vi.fn(() => saveResponse),
    });
    const viewA = Symbol('planning-view-a');
    const viewB = Symbol('planning-view-b');
    const proposal = { round_id: 1, revision: 3, exam_days: [] };

    workflow.activateView(viewA, 1);
    workflow.savePlanningProposal(proposal, 1, viewA);
    workflow.activateView(viewB, 1);
    expect(port.getPlanningProposal).toHaveBeenCalledTimes(2);
    expect(workflow.editorState()).toBe('loading');

    saveResponse.next({ ...proposal, revision: 4 });
    saveResponse.complete();
    expect(workflow.loading()).toBe(true);

    proposalReadB.next(proposal);
    proposalReadB.complete();

    expect(workflow.proposal()).toBeNull();
    expect(workflow.editorState()).toBe('idle');
  });

  it('does not let a late proposal answer replace a later view draft', () => {
    const saveResponse = new Subject<EditablePlanningProposal>();
    const proposal = { round_id: 1, revision: 3, exam_days: [] };
    const { workflow, port } = createHarness({
      getPlanningProposal: vi.fn(() => of(proposal)),
      savePlanningProposal: vi.fn(() => saveResponse),
    });
    const viewA = Symbol('planning-view-a');
    const viewB = Symbol('planning-view-b');
    const staleCommand = { ...proposal, revision: 7 };

    workflow.activateView(viewA, 1);
    workflow.savePlanningProposal(staleCommand, 1, viewA);
    workflow.activateView(viewB, 1);
    const viewBProposal = workflow.proposal();
    saveResponse.next({ ...staleCommand, revision: 8 });
    saveResponse.complete();

    expect(port.savePlanningProposal).toHaveBeenCalledWith(1, staleCommand);
    expect(workflow.proposal()).toBe(viewBProposal);
  });

  it('reloads the active projection when an older view write commits after its read', () => {
    const saveResponse = new Subject<EditablePlanningProposal>();
    const snapshots = [
      emptySnapshot(1),
      emptySnapshot(1),
      { ...emptySnapshot(1), round: { ...emptySnapshot(1).round, name: 'Nach Commit' } },
    ];
    const { workflow, port } = createHarness({
      loadPlanning: vi.fn(() => of(snapshots.shift()!)),
      savePlanningProposal: vi.fn(() => saveResponse),
    });
    const oldView = Symbol('planning-route-activation-a1');
    const reopenedView = Symbol('planning-route-activation-a2');
    const command: EditablePlanningProposal = { round_id: 1, revision: 4, exam_days: [] };

    workflow.activateView(oldView, 1);
    workflow.savePlanningProposal(command, 1, oldView);
    workflow.activateView(reopenedView, 1);
    expect(workflow.snapshot()?.round.name).toBe('Runde 1');

    saveResponse.next({ ...command, revision: 5 });
    saveResponse.complete();

    expect(port.loadPlanning).toHaveBeenCalledTimes(3);
    expect(workflow.snapshot()?.round.name).toBe('Nach Commit');
    expect(workflow.proposal()).toBeNull();
  });

  it('refreshes the active projection after stale round and settings writes', () => {
    const roundResponse = new Subject<{ id: number }>();
    expectStaleWriteRefresh(
      { updateExamRound: vi.fn(() => roundResponse) },
      (workflow, view) =>
        workflow.saveExamRound(
          { name: 'Runde', availability_deadline: null, availability_reminder_at: null },
          1,
          view,
        ),
      () => roundResponse.next({ id: 1 }),
    );

    const settingsResponse = new Subject<Record<string, never>>();
    expectStaleWriteRefresh(
      { savePlanningSettings: vi.fn(() => settingsResponse) },
      (workflow, view) =>
        workflow.savePlanningSettings(
          {
            calendar_week_from: '2026-W40',
            calendar_week_to: '2026-W41',
            exams_per_day: 4,
            max_exam_days_per_week: 2,
          },
          1,
          view,
        ),
      () => settingsResponse.next({}),
    );
  });

  it('refreshes the active projection after stale availability writes', () => {
    const requestResponse = new Subject<{ id: number }>();
    expectStaleWriteRefresh(
      {
        updateExamRound: vi.fn(() => of({ id: 1 })),
        sendAvailabilityRequests: vi.fn(() => requestResponse),
      },
      (workflow, view) =>
        workflow.requestAvailabilities(
          { name: 'Runde', availability_deadline: null, availability_reminder_at: null },
          1,
          view,
        ),
      () => requestResponse.next({ id: 1 }),
    );

    const availabilityResponse = new Subject<{
      id: number;
      committee_member_id: number;
      candidate_exam_day_id: number;
      availability: string;
    }>();
    expectStaleWriteRefresh(
      { saveMemberAvailability: vi.fn(() => availabilityResponse) },
      (workflow, view) =>
        workflow.saveAvailability(
          { committee_member_id: 11, candidate_exam_day_id: 21, availability: 'morning' },
          1,
          view,
        ),
      () =>
        availabilityResponse.next({
          id: 7,
          committee_member_id: 11,
          candidate_exam_day_id: 21,
          availability: 'morning',
        }),
    );
  });

  it('refreshes the active projection after stale candidate-day and proposal generation writes', () => {
    const dayResponse = new Subject<{
      id: number;
      exam_round_id: number;
      date: string;
      is_active: number;
    }>();
    expectStaleWriteRefresh(
      { createCandidateExamDay: vi.fn(() => dayResponse) },
      (workflow, view) =>
        workflow.createCandidateDay({ date: '2026-11-16', is_active: 1 }, 1, view),
      () => dayResponse.next({ id: 8, exam_round_id: 1, date: '2026-11-16', is_active: 1 }),
    );

    const candidateGenerationResponse = new Subject<{
      counts: { created: number; existing: number };
    }>();
    expectStaleWriteRefresh(
      {
        savePlanningSettings: vi.fn(() => of({})),
        generateCandidateExamDays: vi.fn(() => candidateGenerationResponse),
      },
      (workflow, view) =>
        workflow.generateCandidateDays(
          {
            calendar_week_from: '2026-W40',
            calendar_week_to: '2026-W41',
            exams_per_day: 4,
            max_exam_days_per_week: 2,
          },
          1,
          view,
        ),
      () => candidateGenerationResponse.next({ counts: { created: 2, existing: 1 } }),
    );

    const generationResponse = new Subject<{ counts: Record<string, number> }>();
    expectStaleWriteRefresh(
      { generateProposal: vi.fn(() => generationResponse) },
      (workflow, view) => workflow.generateProposal(1, view),
      () => generationResponse.next({ counts: { planned_slots: 2 } }),
    );

    const toggleResponse = new Subject<{ id: number }>();
    expectStaleWriteRefresh(
      { updateCandidateExamDay: vi.fn(() => toggleResponse) },
      (workflow, view) =>
        workflow.toggleCandidateDay(
          { id: 8, exam_round_id: 1, date: '2026-11-16', is_active: 1 },
          1,
          view,
        ),
      () => toggleResponse.next({ id: 8 }),
    );

    const confirmationResponse = new Subject<{
      status: string;
      counts: Record<string, number>;
    }>();
    expectStaleWriteRefresh(
      { confirmPlan: vi.fn(() => confirmationResponse) },
      (workflow, view) => workflow.confirmPlan(1, view),
      () => confirmationResponse.next({ status: 'plan_confirmed', counts: {} }),
    );
  });

  it('ignores a late response from the first A activation after an A to B to A route cycle', () => {
    const saveResponse = new Subject<EditablePlanningProposal>();
    const proposal = { round_id: 1, revision: 2, exam_days: [] };
    const { workflow } = createHarness({
      loadPlanning: vi.fn((roundId: number) => {
        const snapshot = emptySnapshot(roundId);
        return of({
          ...snapshot,
          round: { ...snapshot.round, status: 'plan_proposed' as const },
        });
      }),
      getPlanningProposal: vi.fn(() => of(proposal)),
      savePlanningProposal: vi.fn(() => saveResponse),
    });
    const firstA = Symbol('planning-route-activation-a1');
    const routeB = Symbol('planning-route-activation-b');
    const secondA = Symbol('planning-route-activation-a2');

    workflow.activateView(firstA, 1);
    workflow.savePlanningProposal({ ...proposal, revision: 6 }, 1, firstA);
    workflow.activateView(routeB, 2);
    workflow.activateView(secondA, 1);
    const currentProposal = workflow.proposal();

    saveResponse.next({ ...proposal, revision: 7 });
    saveResponse.complete();

    expect(workflow.proposal()).toBe(currentProposal);
    expect(workflow.proposal()?.revision).toBe(2);
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

  it('refreshes the active round after confirmation succeeds in an older view', () => {
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
    response.next({ counts: { confirmed_slots: 4 } });
    response.complete();

    expect(port.loadPlanning).toHaveBeenCalledTimes(3);
    expect(workflow.snapshot()?.round.id).toBe(1);
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

  it('does not bootstrap-loop after an initial planning read fails', () => {
    const { workflow, port } = createHarness({
      loadPlanning: vi.fn(() => throwError(() => new Error('offline'))),
    });
    const view = Symbol('planning-view');

    workflow.activateView(view, 1);
    TestBed.flushEffects();

    expect(port.loadPlanning).toHaveBeenCalledOnce();
    expect(workflow.loadError()).toBe(true);
  });

  it('clears the failed-read gate and reloads after a new session is established', () => {
    const sessionChanges = new Subject<{ previousEstablished: boolean; established: boolean }>();
    const { workflow, port } = createHarness({
      sessionScopeChanges: sessionChanges,
      loadPlanning: vi
        .fn()
        .mockReturnValueOnce(throwError(() => new Error('offline')))
        .mockReturnValueOnce(of(emptySnapshot(1))),
    });
    const view = Symbol('planning-view');

    workflow.activateView(view, 1);
    expect(workflow.loadError()).toBe(true);

    sessionChanges.next({ previousEstablished: true, established: false });
    expect(workflow.loadError()).toBe(false);
    sessionChanges.next({ previousEstablished: false, established: true });

    expect(port.loadPlanning).toHaveBeenCalledTimes(2);
    expect(workflow.snapshot()?.round.id).toBe(1);
  });

  it('waits for an authenticated session before loading planning data', () => {
    const authState = signal<'checking' | 'authenticated'>('checking');
    const { workflow, port } = createHarness({ authState });
    const view = Symbol('planning-view');

    workflow.activateView(view, 1);

    expect(port.loadPlanning).not.toHaveBeenCalled();

    authState.set('authenticated');
    TestBed.flushEffects();

    expect(port.loadPlanning).toHaveBeenCalledOnce();
    expect(workflow.snapshot()?.round.id).toBe(1);
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

function expectStaleWriteRefresh(
  overrides: Record<string, unknown>,
  startWrite: (workflow: PlanningWorkflowService, view: symbol) => void,
  succeed: () => void,
): void {
  const { workflow, port } = createHarness({
    loadPlanning: vi.fn((roundId: number) => of(emptySnapshot(roundId))),
    ...overrides,
  });
  const oldView = Symbol('planning-view-before-reopen');
  workflow.activateView(oldView, 1);
  startWrite(workflow, oldView);
  workflow.activateView(Symbol('planning-view-after-reopen'), 1);
  expect(port.loadPlanning).toHaveBeenCalledTimes(2);

  succeed();

  expect(port.loadPlanning).toHaveBeenCalledTimes(3);
  expect(workflow.snapshot()?.round.id).toBe(1);
  TestBed.resetTestingModule();
}

function createHarness(
  overrides: Record<string, unknown> = {},
  feedbackOverrides: Record<string, unknown> = {},
) {
  const roundId = signal(1);
  const roundChanges = new Subject<number>();
  const sessionChanges =
    (overrides['sessionScopeChanges'] as Subject<unknown> | undefined) ?? new Subject<unknown>();
  const sessionGeneration = signal(0);
  const authState =
    (overrides['authState'] as ReturnType<typeof signal<'authenticated' | 'checking'>>) ??
    signal<'authenticated' | 'checking'>('authenticated');
  const sessionScope = {
    generation: sessionGeneration,
    changes$: sessionChanges,
    forCurrentSession: <T>(operation: Observable<T>) => operation,
  };
  const roundContext = {
    roundId,
    changes$: roundChanges.asObservable(),
    select: (id: number) => {
      if (roundId() === id) return;
      roundId.set(id);
      roundChanges.next(id);
    },
  };
  const proposal = { round_id: 1, revision: 2, exam_days: [] };
  const port = {
    loadPlanning: vi.fn((id: number) => of(emptySnapshot(id))),
    savePlanningSettings: vi.fn(() => of({})),
    updateExamRound: vi.fn(() => of({})),
    sendAvailabilityRequests: vi.fn(() => of({ notification_warning: null })),
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
      {
        provide: AuthService,
        useValue: { state: authState, hasCapability: () => true, session: () => null },
      },
      { provide: UiFeedbackService, useValue: feedback },
    ],
  });

  return {
    workflow: TestBed.inject(PlanningWorkflowService),
    port,
    feedback,
    roundId,
    roundContext,
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
