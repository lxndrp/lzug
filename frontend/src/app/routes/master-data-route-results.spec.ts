import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { MasterDataWorkflowService } from '../master-data/master-data-workflow.service';
import type { Candidate, CommitteeMember } from '../master-data/master-data.models';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import { CandidatesRouteComponent } from './candidates-route.component';
import { CommitteeRouteComponent } from './committee-route.component';

describe('master-data route mutation results', () => {
  const staleSuccess = {
    ok: true,
    current: false,
    requestId: 1,
    contextKey: 'stale-context',
  };
  const candidate: Candidate = {
    id: 7,
    firstName: 'Ada',
    lastName: 'Lovelace',
    examNumber: 'EX-7',
    specialization: 'application_development',
    trainingCompany: 'Testbetrieb',
  };
  const member: CommitteeMember = {
    id: 8,
    personId: 9,
    committeeId: 3,
    firstName: 'Grace',
    lastName: 'Hopper',
    memberStatus: 'ordinary',
    committeeRole: 'member',
    representingSide: 'employer',
    email: 'grace@example.invalid',
    emailVerifiedAt: null,
    mobile: null,
    isActive: true,
  };

  it('does not report stale successful candidate writes as failed or run old form effects', () => {
    const workflow = {
      loadCandidates: vi.fn(),
      createCandidate: vi.fn(() => of({ ...staleSuccess, value: candidate })),
      updateCandidate: vi.fn(() => of({ ...staleSuccess, value: candidate })),
      deleteCandidate: vi.fn(() => of(staleSuccess)),
    };
    const feedback = {
      notify: vi.fn(),
      confirm: (_title: string, _message: string, _label: string, action: () => void) => action(),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: MasterDataWorkflowService, useValue: workflow },
        { provide: AuthService, useValue: { state: () => 'anonymous' } },
        { provide: UiFeedbackService, useValue: feedback },
      ],
    });
    const route = TestBed.runInInjectionContext(
      () => new CandidatesRouteComponent(),
    ) as unknown as {
      component?: { resetDraft: () => void; finishEditing: (id: number) => void };
      createCandidate: (payload: object) => void;
      updateCandidate: (update: object) => void;
      requestCandidateDeletion: (id: number, label: string) => void;
    };
    const component = { resetDraft: vi.fn(), finishEditing: vi.fn() };
    route.component = component;

    route.createCandidate({});
    route.updateCandidate({});
    route.requestCandidateDeletion(candidate.id, 'Ada Lovelace');

    expect(feedback.notify).not.toHaveBeenCalled();
    expect(component.resetDraft).not.toHaveBeenCalled();
    expect(component.finishEditing).not.toHaveBeenCalled();
  });

  it('does not report stale successful committee writes as failed or reset the old form', () => {
    const workflow = {
      loadCommittees: vi.fn(),
      createMember: vi.fn(() => of({ ...staleSuccess, value: member })),
      toggleMember: vi.fn(() => of({ ...staleSuccess, value: member })),
    };
    const feedback = { notify: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        { provide: MasterDataWorkflowService, useValue: workflow },
        { provide: AuthService, useValue: { state: () => 'anonymous' } },
        { provide: UiFeedbackService, useValue: feedback },
      ],
    });
    const route = TestBed.runInInjectionContext(() => new CommitteeRouteComponent()) as unknown as {
      component?: { resetMemberForm: () => void };
      createMember: (payload: object) => void;
      toggleMember: (value: CommitteeMember) => void;
    };
    const component = { resetMemberForm: vi.fn() };
    route.component = component;

    route.createMember({});
    route.toggleMember(member);

    expect(feedback.notify).not.toHaveBeenCalled();
    expect(component.resetMemberForm).not.toHaveBeenCalled();
  });
});
