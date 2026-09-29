import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { of, Subject } from 'rxjs';

import type { ExamRound } from '../api/api.models';
import { ApiClient } from '../api/api-client.service';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import type { PlanningComponent } from './planning.component';
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
    const apiClient = {
      patch: vi.fn(() => of({ id: 2, name: 'Runde B aktualisiert' })),
    };
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: ApiClient, useValue: apiClient },
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
    expect(apiClient.patch).not.toHaveBeenCalled();

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

    expect(apiClient.patch).toHaveBeenCalledWith('/api/exam-rounds/2', roundBValues);
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
    const apiClient = { patch: vi.fn(() => of({})) };
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: ApiClient, useValue: apiClient },
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

    expect(apiClient.patch).not.toHaveBeenCalled();
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
    const apiClient = {
      post: vi.fn(() => of({})),
    };
    const feedback = { notify: vi.fn(), roleRestriction: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: ApiClient, useValue: apiClient },
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

    expect(apiClient.post).not.toHaveBeenCalled();
    expect(markAvailabilityError).toHaveBeenCalledWith(payload);
  });

  it('keeps availability request steps on the validated round if selection changes mid-request', () => {
    const patchResponse = new Subject<ExamRound>();
    const apiClient = {
      patch: vi.fn(() => patchResponse),
      post: vi.fn(() => of({})),
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
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: ApiClient, useValue: apiClient },
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

    expect(apiClient.patch).toHaveBeenCalledWith('/api/exam-rounds/1', expect.any(Object));
    context.select(2);
    patchResponse.next({} as ExamRound);
    patchResponse.complete();

    expect(apiClient.post).toHaveBeenCalledWith('/api/exam-rounds/1/request-availabilities', {});
    expect(apiClient.post).not.toHaveBeenCalledWith(
      '/api/exam-rounds/2/request-availabilities',
      {},
    );
  });

  it('keeps candidate-day generation on the validated round if selection changes while saving settings', () => {
    const settingsResponse = new Subject<unknown>();
    const apiClient = {
      post: vi.fn((url: string) =>
        url === '/api/planning-settings'
          ? settingsResponse
          : of({ counts: { created: 1, existing: 0 } }),
      ),
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
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: ApiClient, useValue: apiClient },
        {
          provide: AuthService,
          useValue: {
            hasCapability: () => true,
            session: () => null,
          },
        },
        { provide: UiFeedbackService, useValue: { notify: vi.fn(), roleRestriction: vi.fn() } },
      ],
    });

    const context = TestBed.inject(RoundContextService);
    context.select(1);
    const workflow = TestBed.inject(PlanningWorkflowService);
    workflow.generateCandidateDays({} as never);

    expect(apiClient.post).toHaveBeenCalledWith(
      '/api/planning-settings',
      expect.objectContaining({ exam_round_id: 1 }),
    );
    context.select(2);
    settingsResponse.next({});
    settingsResponse.complete();

    expect(apiClient.post).toHaveBeenCalledWith('/api/candidate-exam-days/generate', {
      round_id: 1,
    });
    expect(apiClient.post).not.toHaveBeenCalledWith('/api/candidate-exam-days/generate', {
      round_id: 2,
    });
  });
});
