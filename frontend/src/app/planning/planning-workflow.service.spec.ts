import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { of, Subject } from 'rxjs';

import type { CandidateExamDay, ExamRound } from '../api/api.models';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import { PLANNING_PORT } from './planning.port';
import { PlanningWorkflowService } from './planning-workflow.service';

describe('PlanningWorkflowService', () => {
  it('blocks stale round drafts during refresh and saves only the displayed round values', () => {
    const displayedRound = signal<ExamRound | null>(null);
    const loading = signal(true);
    const workspace = {
      round: displayedRound,
      loading,
      actionBusy: signal(false),
      refresh: vi.fn(),
    };
    const planning = {
      updateExamRound: vi.fn(() => of({ id: 2, name: 'Runde B aktualisiert' })),
    };
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: PLANNING_PORT, useValue: planning },
        { provide: AuthService, useValue: { hasCapability: () => true, session: () => null } },
        { provide: UiFeedbackService, useValue: feedback },
      ],
    });

    const context = TestBed.inject(RoundContextService);
    context.select(2);
    const workflow = TestBed.inject(PlanningWorkflowService);
    const roundBValues = {
      name: 'Runde B aktualisiert',
      availability_deadline: null,
      availability_reminder_at: null,
    };

    workflow.saveExamRound(roundBValues);
    expect(planning.updateExamRound).not.toHaveBeenCalled();

    displayedRound.set({
      id: 2,
      exam_half_year_id: 4,
      name: 'Runde B',
      committee_id: 3,
      status: 'draft',
      availability_deadline: null,
      availability_reminder_at: null,
    });
    loading.set(false);
    workflow.saveExamRound(roundBValues);

    expect(planning.updateExamRound).toHaveBeenCalledWith(roundBValues, 2);
    expect(context.roundId()).toBe(displayedRound()?.id);
    expect(feedback.notify).toHaveBeenCalledWith(
      'success',
      'Prüfungsrunde gespeichert',
      'Die Änderungen sind übernommen.',
    );
  });

  it('shows feedback when a same-round save is rejected during refresh', () => {
    const workspace = {
      round: signal<ExamRound | null>({
        id: 2,
        exam_half_year_id: 4,
        name: 'Runde B',
        committee_id: 3,
        status: 'draft',
        availability_deadline: null,
        availability_reminder_at: null,
      }),
      loading: signal(true),
      actionBusy: signal(false),
      refresh: vi.fn(),
    };
    const planning = { updateExamRound: vi.fn(() => of({})) };
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: PLANNING_PORT, useValue: planning },
        { provide: AuthService, useValue: { hasCapability: () => true, session: () => null } },
        { provide: UiFeedbackService, useValue: feedback },
      ],
    });

    TestBed.inject(RoundContextService).select(2);
    const workflow = TestBed.inject(PlanningWorkflowService);
    workflow.saveExamRound({
      name: 'Runde B aktualisiert',
      availability_deadline: null,
      availability_reminder_at: null,
    });

    expect(planning.updateExamRound).not.toHaveBeenCalled();
    expect(feedback.notify).toHaveBeenCalledWith(
      'error',
      'Prüfungsrunde wird aktualisiert',
      'Die Daten der ausgewählten Prüfungsrunde werden noch aktualisiert. Bitte warten Sie kurz und versuchen Sie es erneut.',
    );
  });

  it('rolls back an availability edit rejected while the current round refreshes', () => {
    const displayedRound = signal<ExamRound | null>({
      id: 2,
      exam_half_year_id: 4,
      name: 'Runde B',
      committee_id: 3,
      status: 'availability_requested',
      availability_deadline: null,
      availability_reminder_at: null,
    });
    const workspace = {
      round: displayedRound,
      loading: signal(true),
      actionBusy: signal(false),
      refresh: vi.fn(),
      board: signal(null),
    };
    const planning = {
      saveMemberAvailability: vi.fn(() => of({})),
    };
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: PLANNING_PORT, useValue: planning },
        { provide: AuthService, useValue: { hasCapability: () => true, session: () => null } },
        { provide: UiFeedbackService, useValue: feedback },
      ],
    });

    const context = TestBed.inject(RoundContextService);
    context.select(2);
    const workflow = TestBed.inject(PlanningWorkflowService);
    const view = Symbol('planning-view');
    workflow.activateView(view);
    const payload = {
      committee_member_id: 1,
      candidate_exam_day_id: 5,
      availability: 'morning' as const,
    };

    workflow.saveAvailability(payload, view);

    expect(planning.saveMemberAvailability).not.toHaveBeenCalled();
    expect(workflow.viewEffects()).toMatchObject([
      {
        type: 'availability-error',
        payload,
        usePersistedValue: true,
      },
    ]);
  });

  it('does not apply a late availability response to the newly selected round', () => {
    const availabilityResponse = new Subject<{
      id: number;
      committee_member_id: number;
      candidate_exam_day_id: number;
      availability: 'morning';
    }>();
    const board = signal({ availabilities: [] as Array<{ id: number }> });
    const workspace = {
      round: signal<ExamRound | null>({
        id: 1,
        exam_half_year_id: 4,
        name: 'Runde A',
        committee_id: 3,
        status: 'draft',
        availability_deadline: null,
        availability_reminder_at: null,
      }),
      loading: signal(false),
      actionBusy: signal(false),
      board,
      refresh: vi.fn(),
    };
    const planning = { saveMemberAvailability: vi.fn(() => availabilityResponse) };
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: PLANNING_PORT, useValue: planning },
        { provide: AuthService, useValue: { hasCapability: () => true, session: () => null } },
        { provide: UiFeedbackService, useValue: feedback },
      ],
    });

    const context = TestBed.inject(RoundContextService);
    context.select(1);
    const workflow = TestBed.inject(PlanningWorkflowService);
    const viewA = Symbol('planning-view-a');
    const viewB = Symbol('planning-view-b');
    workflow.activateView(viewA);
    const payload = {
      committee_member_id: 1,
      candidate_exam_day_id: 5,
      availability: 'morning' as const,
    };
    workflow.saveAvailability(payload, viewA);

    expect(planning.saveMemberAvailability).toHaveBeenCalledWith(payload, 1);
    context.select(2);
    workflow.activateView(viewB);
    availabilityResponse.next({ id: 7, ...payload });
    availabilityResponse.complete();

    expect(board()).toEqual({ availabilities: [] });
    expect(workflow.viewEffects()).toEqual([]);
    expect(feedback.notify).not.toHaveBeenCalled();
  });

  it('settles proposal loading when a view is destroyed and reloads on the next route view', () => {
    const requests: Subject<never>[] = [];
    const planning = {
      getPlanningProposal: vi.fn(() => {
        const response = new Subject<never>();
        requests.push(response);
        return response;
      }),
    };
    const workspace = createPlanningWorkspace('plan_proposed');
    configureWorkflow(workspace, planning);
    TestBed.inject(RoundContextService).select(1);
    const workflow = TestBed.inject(PlanningWorkflowService);
    const viewA = Symbol('planning-route-a');
    const viewB = Symbol('planning-route-b');

    workflow.activateView(viewA);
    const staleRequest = requests.at(-1)!;
    expect(workflow.editorState()).toBe('loading');
    expect(staleRequest.observed).toBe(true);

    workflow.deactivateView(viewA);
    expect(workflow.editorState()).toBe('idle');
    expect(staleRequest.observed).toBe(false);

    workflow.activateView(viewB);
    const activeRequest = requests.at(-1)!;
    expect(activeRequest).not.toBe(staleRequest);
    expect(workflow.editorState()).toBe('loading');
    staleRequest.next({} as never);
    expect(workflow.editorState()).toBe('loading');
    activeRequest.next({} as never);
    activeRequest.complete();

    expect(workflow.editorState()).toBe('ready');
  });

  it('restarts proposal loading after a save error arrives from a discarded view', () => {
    const saveResponse = new Subject<never>();
    const proposalRequests: Subject<never>[] = [];
    const planning = {
      getPlanningProposal: vi.fn(() => {
        const response = new Subject<never>();
        proposalRequests.push(response);
        return response;
      }),
      savePlanningProposal: vi.fn(() => saveResponse),
    };
    const workspace = createPlanningWorkspace('plan_proposed');
    configureWorkflow(workspace, planning);
    TestBed.inject(RoundContextService).select(1);
    const workflow = TestBed.inject(PlanningWorkflowService);
    const viewA = Symbol('planning-route-a');
    const viewB = Symbol('planning-route-b');
    workflow.activateView(viewA);
    workflow.savePlanningProposal({} as never, viewA);
    workflow.activateView(viewB);
    const proposalLoadsBeforeFailure = proposalRequests.length;

    saveResponse.error({ kind: 'conflict' });

    expect(planning.savePlanningProposal).toHaveBeenCalledOnce();
    expect(proposalRequests).toHaveLength(proposalLoadsBeforeFailure + 1);
    expect(workflow.editorState()).toBe('loading');
    expect(workflow.actionBusy()).toBe(false);
  });

  it('cancels plan confirmation and clears pending when the planning route is destroyed', () => {
    const confirmation = new Subject<boolean>();
    const planning = {
      confirmPlan: vi.fn(() => of({ counts: {} })),
      getPlanningProposal: vi.fn(() => of({})),
    };
    const workspace = createPlanningWorkspace('plan_proposed');
    const feedback = {
      notify: vi.fn(),
      roleRestriction: vi.fn(),
      confirm$: vi.fn(() => confirmation),
    };
    configureWorkflow(workspace, planning, feedback);
    TestBed.inject(RoundContextService).select(1);
    const workflow = TestBed.inject(PlanningWorkflowService);
    const view = Symbol('planning-route-view');
    workflow.activateView(view);

    workflow.requestPlanConfirmation(view);

    expect(workflow.actionBusy()).toBe(true);
    expect(confirmation.observed).toBe(true);
    workflow.deactivateView(view);

    expect(confirmation.observed).toBe(false);
    expect(workflow.actionBusy()).toBe(false);
    expect(planning.confirmPlan).not.toHaveBeenCalled();
  });

  it('delivers parallel availability save effects without overwriting either cell result', () => {
    const responses = new Map<string, Subject<never>>();
    const planning = {
      saveMemberAvailability: vi.fn(
        (payload: { committee_member_id: number; candidate_exam_day_id: number }) => {
          const response = new Subject<never>();
          responses.set(
            `${payload.committee_member_id}:${payload.candidate_exam_day_id}`,
            response,
          );
          return response;
        },
      ),
    };
    const workspace = createPlanningWorkspace('availability_requested');
    configureWorkflow(workspace, planning);
    TestBed.inject(RoundContextService).select(1);
    const workflow = TestBed.inject(PlanningWorkflowService);
    const view = Symbol('planning-route');
    workflow.activateView(view);
    const first = {
      committee_member_id: 11,
      candidate_exam_day_id: 21,
      availability: 'morning',
    } as const;
    const second = {
      committee_member_id: 12,
      candidate_exam_day_id: 22,
      availability: 'afternoon',
    } as const;

    workflow.saveAvailability(first, view);
    workflow.saveAvailability(second, view);
    responses.get('11:21')!.next({ id: 1, ...first } as never);
    responses.get('12:22')!.next({ id: 2, ...second } as never);

    expect(workflow.viewEffects()).toHaveLength(2);
    expect(workflow.viewEffects().map((effect) => effect.type)).toEqual([
      'availability-saved',
      'availability-saved',
    ]);
    const lastVersion = workflow.viewEffects()[1].version;
    workflow.acknowledgeViewEffects(view, lastVersion);
    expect(workflow.viewEffects()).toEqual([]);
  });

  it('blocks duplicate planning submits and keeps a late success out of a new view', () => {
    const response = new Subject<CandidateExamDay>();
    const workspace = {
      round: signal<ExamRound | null>({
        id: 1,
        exam_half_year_id: 4,
        name: 'Runde A',
        committee_id: 3,
        status: 'draft',
        availability_deadline: null,
        availability_reminder_at: null,
      }),
      loading: signal(false),
      actionBusy: signal(false),
      refresh: vi.fn(),
    };
    const planning = { createCandidateExamDay: vi.fn(() => response) };
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: PLANNING_PORT, useValue: planning },
        { provide: AuthService, useValue: { hasCapability: () => true, session: () => null } },
        { provide: UiFeedbackService, useValue: feedback },
      ],
    });

    const context = TestBed.inject(RoundContextService);
    context.select(1);
    const workflow = TestBed.inject(PlanningWorkflowService);
    const viewA = Symbol('planning-view-a');
    const viewB = Symbol('planning-view-b');
    workflow.activateView(viewA);
    const payload = { date: '2026-11-01' } as never;

    workflow.createCandidateDay(payload, viewA);
    workflow.createCandidateDay(payload, viewA);

    expect(planning.createCandidateExamDay).toHaveBeenCalledOnce();
    expect(workflow.actionBusy()).toBe(true);
    workflow.activateView(viewB);
    response.next({ id: 6, date: '2026-11-01' } as CandidateExamDay);
    response.complete();

    expect(workflow.viewEffects()).toEqual([]);
    expect(workflow.actionBusy()).toBe(false);
    expect(workspace.refresh).not.toHaveBeenCalled();
  });

  it('keeps availability request steps on the validated round if selection changes mid-request', () => {
    const requestResponse = new Subject<ExamRound>();
    const planning = { requestAvailabilities: vi.fn(() => requestResponse) };
    const workspace = {
      round: signal<ExamRound | null>({
        id: 1,
        exam_half_year_id: 4,
        name: 'Runde A',
        committee_id: 3,
        status: 'draft',
        availability_deadline: null,
        availability_reminder_at: null,
      }),
      loading: signal(false),
      actionBusy: signal(false),
      refresh: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: PLANNING_PORT, useValue: planning },
        { provide: AuthService, useValue: { hasCapability: () => true, session: () => null } },
        { provide: UiFeedbackService, useValue: { notify: vi.fn(), roleRestriction: vi.fn() } },
      ],
    });

    const context = TestBed.inject(RoundContextService);
    context.select(1);
    const workflow = TestBed.inject(PlanningWorkflowService);
    workflow.requestAvailabilities({
      name: 'Runde A',
      availability_deadline: null,
      availability_reminder_at: null,
    });

    expect(planning.requestAvailabilities).toHaveBeenCalledWith(
      { name: 'Runde A', availability_deadline: null, availability_reminder_at: null },
      1,
    );
    context.select(2);
    requestResponse.next({} as ExamRound);
    requestResponse.complete();
  });

  it('keeps candidate-day generation on the validated round if selection changes while saving settings', () => {
    const settingsResponse = new Subject<unknown>();
    const planning = {
      savePlanningSettings: vi.fn(() => settingsResponse),
      generateCandidateExamDays: vi.fn(() => of({ counts: { created: 1, existing: 0 } })),
    };
    const workspace = {
      round: signal<ExamRound | null>({
        id: 1,
        exam_half_year_id: 4,
        name: 'Runde A',
        committee_id: 3,
        status: 'draft',
        availability_deadline: null,
        availability_reminder_at: null,
      }),
      loading: signal(false),
      actionBusy: signal(false),
      refresh: vi.fn(),
    };
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: PLANNING_PORT, useValue: planning },
        {
          provide: AuthService,
          useValue: {
            hasCapability: () => true,
            session: () => null,
          },
        },
        { provide: UiFeedbackService, useValue: feedback },
      ],
    });

    const context = TestBed.inject(RoundContextService);
    context.select(1);
    const workflow = TestBed.inject(PlanningWorkflowService);
    workflow.generateCandidateDays({} as never);

    expect(planning.savePlanningSettings).toHaveBeenCalledWith({}, 1);
    context.select(2);
    settingsResponse.next({});
    settingsResponse.complete();

    expect(planning.generateCandidateExamDays).toHaveBeenCalledWith(1);
    expect(workflow.candidateDayGeneration()).toBeNull();
    expect(feedback.notify).not.toHaveBeenCalled();
    expect(workspace.refresh).not.toHaveBeenCalled();
  });

  it('ignores candidate-day generation results after the session changes', () => {
    const settingsResponse = new Subject<unknown>();
    const generationResponse = new Subject<{ counts: { created: number; existing: number } }>();
    const planning = {
      savePlanningSettings: vi.fn(() => settingsResponse),
      generateCandidateExamDays: vi.fn(() => generationResponse),
    };
    const workspace = {
      round: signal<ExamRound | null>({
        id: 1,
        exam_half_year_id: 4,
        name: 'Runde A',
        committee_id: 3,
        status: 'draft',
        availability_deadline: null,
        availability_reminder_at: null,
      }),
      loading: signal(false),
      actionBusy: signal(false),
      refresh: vi.fn(),
    };
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: PLANNING_PORT, useValue: planning },
        {
          provide: AuthService,
          useValue: {
            hasCapability: () => true,
            session: () => null,
          },
        },
        { provide: UiFeedbackService, useValue: feedback },
      ],
    });

    const context = TestBed.inject(RoundContextService);
    context.select(1);
    const scope = TestBed.inject(SessionScopeService);
    scope.establish({
      authenticated: true,
      account_id: 7,
      person_id: 9,
      committee_member_id: 12,
      is_operator: false,
    });
    const workflow = TestBed.inject(PlanningWorkflowService);
    workflow.generateCandidateDays({} as never);

    settingsResponse.next({});
    settingsResponse.complete();
    expect(planning.generateCandidateExamDays).toHaveBeenCalledWith(1);

    scope.clear();
    generationResponse.next({ counts: { created: 1, existing: 0 } });
    generationResponse.complete();

    expect(workflow.candidateDayGeneration()).toBeNull();
    expect(feedback.notify).not.toHaveBeenCalled();
    expect(workspace.refresh).not.toHaveBeenCalled();
  });
});

function createPlanningWorkspace(status: ExamRound['status']) {
  return {
    round: signal<ExamRound | null>({
      id: 1,
      exam_half_year_id: 4,
      name: 'Runde A',
      committee_id: 3,
      status,
      availability_deadline: null,
      availability_reminder_at: null,
    }),
    loading: signal(false),
    actionBusy: signal(false),
    board: signal({ availabilities: [] as Array<{ id: number }> }),
    refresh: vi.fn(),
  };
}

function configureWorkflow(workspace: object, planning: object, feedback?: object): void {
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: ApplicationWorkspaceService, useValue: workspace },
      { provide: PLANNING_PORT, useValue: planning },
      { provide: AuthService, useValue: { hasCapability: () => true, session: () => null } },
      {
        provide: UiFeedbackService,
        useValue: feedback ?? { notify: vi.fn(), roleRestriction: vi.fn() },
      },
    ],
  });
}
