import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { of, Subject } from 'rxjs';

import type { ExamRound } from '../api/api.models';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import type { PlanningComponent } from './planning.component';
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
    const markAvailabilityError = vi.fn();
    workflow.connect({ markAvailabilityError } as unknown as PlanningComponent);
    const payload = {
      committee_member_id: 1,
      candidate_exam_day_id: 5,
      availability: 'morning' as const,
    };

    workflow.saveAvailability(payload);

    expect(planning.saveMemberAvailability).not.toHaveBeenCalled();
    expect(markAvailabilityError).toHaveBeenCalledWith(payload, true);
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
    const markAvailabilitySaved = vi.fn();
    const markAvailabilityError = vi.fn();
    workflow.connect({
      markAvailabilitySaved,
      markAvailabilityError,
    } as unknown as PlanningComponent);
    const payload = {
      committee_member_id: 1,
      candidate_exam_day_id: 5,
      availability: 'morning' as const,
    };
    workflow.saveAvailability(payload);

    expect(planning.saveMemberAvailability).toHaveBeenCalledWith(payload, 1);
    context.select(2);
    availabilityResponse.next({ id: 7, ...payload });
    availabilityResponse.complete();

    expect(board()).toEqual({ availabilities: [] });
    expect(markAvailabilitySaved).not.toHaveBeenCalled();
    expect(markAvailabilityError).not.toHaveBeenCalled();
    expect(feedback.notify).not.toHaveBeenCalled();
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
});
