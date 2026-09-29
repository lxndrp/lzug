import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { of } from 'rxjs';

import type { ExamRound } from '../api/api.models';
import { ApiClient } from '../api/api-client.service';
import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';
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
});
