import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';

import { AuthService } from '../auth/auth.service';
import { RoundContextService } from '../api/round-context.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { ExamHalfYearsRouteComponent } from './exam-half-years-route.component';

describe('ExamHalfYearsRouteComponent', () => {
  it('uses the selected round and reloads only round-specific references when workspace is stale', () => {
    const roundId = signal(2);
    const workspace = {
      round: signal({ id: 1 }),
      masterData: signal(null),
      refreshCandidateReferences: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: RoundContextService, useValue: { roundId } },
        { provide: AuthService, useValue: { session: () => null, hasCapability: () => false } },
      ],
    });

    TestBed.runInInjectionContext(() => new ExamHalfYearsRouteComponent());

    expect(workspace.refreshCandidateReferences).toHaveBeenCalledExactlyOnceWith(2);
  });

  it('does not reload references when workspace already matches the selected round', () => {
    const workspace = {
      round: signal({ id: 2 }),
      masterData: signal(null),
      refreshCandidateReferences: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: RoundContextService, useValue: { roundId: () => 2 } },
        { provide: AuthService, useValue: { session: () => null, hasCapability: () => false } },
      ],
    });

    TestBed.runInInjectionContext(() => new ExamHalfYearsRouteComponent());

    expect(workspace.refreshCandidateReferences).not.toHaveBeenCalled();
  });
});
