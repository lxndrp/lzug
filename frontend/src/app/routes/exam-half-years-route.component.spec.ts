import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';

import { AuthService } from '../auth/auth.service';
import { RoundContextService } from '../api/round-context.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { ExamHalfYearsRouteComponent } from './exam-half-years-route.component';

describe('ExamHalfYearsRouteComponent', () => {
  it('uses the selected round and reloads only round-specific references when workspace is stale', () => {
    const roundId = signal(2);
    const authState = signal<'checking' | 'authenticated'>('authenticated');
    const workspace = {
      round: signal({ id: 1 }),
      masterData: signal(null),
      candidateReferenceSnapshot: signal({
        roundId: 2,
        candidates: [{ candidate: { id: 9, first_name: 'Ada', last_name: 'Lovelace' } }],
        candidateAssignments: [{ exam_half_year_id: 5, candidate_id: 9, ended_at: null }],
      }),
      refreshCandidateReferences: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: RoundContextService, useValue: { roundId } },
        {
          provide: AuthService,
          useValue: { state: authState, session: () => null, hasCapability: () => false },
        },
      ],
    });

    const route = TestBed.runInInjectionContext(() => new ExamHalfYearsRouteComponent());
    TestBed.flushEffects();

    expect(workspace.refreshCandidateReferences).toHaveBeenCalledExactlyOnceWith(2);
    expect((route as unknown as { candidates: () => unknown }).candidates()).toEqual([
      { id: 9, firstName: 'Ada', lastName: 'Lovelace' },
    ]);
  });

  it('does not reload references when workspace already matches the selected round', () => {
    const workspace = {
      round: signal({ id: 2 }),
      masterData: signal({
        committees: [],
        candidates: [{ candidate: { id: 22, first_name: 'Grace', last_name: 'Hopper' } }],
        candidateAssignments: [],
      }),
      candidateReferenceSnapshot: signal({
        roundId: 2,
        candidates: [{ candidate: { id: 11, first_name: 'Old', last_name: 'Candidate' } }],
        candidateAssignments: [],
      }),
      refreshCandidateReferences: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: RoundContextService, useValue: { roundId: () => 2 } },
        {
          provide: AuthService,
          useValue: {
            state: () => 'authenticated',
            session: () => null,
            hasCapability: () => false,
          },
        },
      ],
    });

    const route = TestBed.runInInjectionContext(() => new ExamHalfYearsRouteComponent());
    TestBed.flushEffects();

    expect(workspace.refreshCandidateReferences).not.toHaveBeenCalled();
    expect((route as unknown as { candidates: () => unknown }).candidates()).toEqual([
      { id: 22, firstName: 'Grace', lastName: 'Hopper' },
    ]);
  });

  it('waits for authentication before loading references for a preserved deep link', () => {
    const authState = signal<'checking' | 'authenticated'>('checking');
    const workspace = {
      round: signal({ id: 1 }),
      masterData: signal(null),
      candidateReferenceSnapshot: signal(null),
      refreshCandidateReferences: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: RoundContextService, useValue: { roundId: () => 2 } },
        {
          provide: AuthService,
          useValue: { state: authState, session: () => null, hasCapability: () => false },
        },
      ],
    });

    TestBed.runInInjectionContext(() => new ExamHalfYearsRouteComponent());
    TestBed.flushEffects();
    expect(workspace.refreshCandidateReferences).not.toHaveBeenCalled();

    authState.set('authenticated');
    TestBed.flushEffects();

    expect(workspace.refreshCandidateReferences).toHaveBeenCalledExactlyOnceWith(2);
  });
});
