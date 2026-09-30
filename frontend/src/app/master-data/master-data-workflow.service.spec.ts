import { TestBed } from '@angular/core/testing';
import { of, Subject, throwError } from 'rxjs';

import { RoundContextService } from '../api/round-context.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import type { Candidate, CommitteeMember } from './master-data.models';
import { MASTER_DATA_PORT } from './master-data.port';
import { MasterDataWorkflowService } from './master-data-workflow.service';

describe('MasterDataWorkflowService', () => {
  let service: MasterDataWorkflowService;
  let port: {
    createCandidate: ReturnType<typeof vi.fn>;
    updateCandidate: ReturnType<typeof vi.fn>;
    deleteCandidate: ReturnType<typeof vi.fn>;
    createCommitteeMember: ReturnType<typeof vi.fn>;
    updateCommitteeMember: ReturnType<typeof vi.fn>;
  };
  let workspace: {
    round: ReturnType<typeof vi.fn>;
    masterData: ReturnType<typeof vi.fn>;
    selectedCommitteeId: ReturnType<typeof vi.fn>;
    refresh: ReturnType<typeof vi.fn>;
  };
  let roundContext: { roundId: ReturnType<typeof vi.fn> };

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
  const candidateCommand = {
    firstName: 'Ada',
    lastName: 'Lovelace',
    examNumber: 'EX-7',
    specialization: 'application_development',
    trainingCompany: 'Testbetrieb',
  };

  beforeEach(() => {
    port = {
      createCandidate: vi.fn(),
      updateCandidate: vi.fn(),
      deleteCandidate: vi.fn(),
      createCommitteeMember: vi.fn(),
      updateCommitteeMember: vi.fn(),
    };
    workspace = {
      round: vi.fn(() => ({
        id: 12,
        name: 'Winter 2026',
        exam_half_year_id: 4,
        committee_id: 3,
        status: 'planning',
      })),
      masterData: vi.fn(() => null),
      selectedCommitteeId: vi.fn(() => 3),
      refresh: vi.fn(),
    };
    roundContext = { roundId: vi.fn(() => 12) };
    TestBed.configureTestingModule({
      providers: [
        MasterDataWorkflowService,
        { provide: MASTER_DATA_PORT, useValue: port },
        { provide: RoundContextService, useValue: roundContext },
        { provide: ApplicationWorkspaceService, useValue: workspace },
      ],
    });
    service = TestBed.inject(MasterDataWorkflowService);
  });

  it('projects shared backend data into feature-owned candidate and committee views', () => {
    workspace.masterData.mockReturnValue({
      candidates: [
        {
          candidate: {
            id: 7,
            first_name: 'Ada',
            last_name: 'Lovelace',
            ihk_exam_number: 'EX-7',
            specialization: 'application_development',
            training_company: 'Testbetrieb',
          },
          roundCandidate: { attempt_number: 2, requires_mep: 1 },
        },
      ],
      candidateAssignments: [
        {
          id: 1,
          candidate_id: 7,
          exam_round_id: 12,
          assigned_at: '2026-01-01',
          ended_at: null,
          change_reason: null,
        },
      ],
      examRounds: [{ id: 12, name: 'Winter 2026', exam_half_year_id: 4, committee_id: 3 }],
      committees: [{ id: 3, name: 'Prüfungsausschuss', occupation: 'IT', ihk: 'IHK' }],
      members: [
        {
          id: 8,
          person_id: 9,
          committee_id: 3,
          first_name: 'Grace',
          last_name: 'Hopper',
          member_status: 'ordinary',
          committee_role: 'member',
          representing_side: 'employer',
          email: 'grace@example.invalid',
          email_verified_at: null,
          mobile: null,
          is_active: 1,
        },
      ],
      persons: [
        { id: 9, first_name: 'Grace', last_name: 'Hopper', email: 'grace@example.invalid' },
      ],
    });

    expect(service.candidateWorkspace()).toMatchObject({
      candidates: [
        {
          candidate: { id: 7, firstName: 'Ada', examNumber: 'EX-7' },
          roundCandidate: { attemptNumber: 2, requiresMep: true },
        },
      ],
      assignments: [{ candidateId: 7, examRoundId: 12, endedAt: null }],
      activeRound: { id: 12, halfYearId: 4, committeeId: 3 },
    });
    expect(service.committeeWorkspace()).toMatchObject({
      members: [{ id: 8, personId: 9, committeeId: 3, firstName: 'Grace', isActive: true }],
      persons: [{ id: 9, firstName: 'Grace' }],
    });
  });

  it('passes the active round to the port and refreshes after a successful command', () => {
    port.createCandidate.mockReturnValue(of(candidate));
    let result: unknown;

    service.createCandidate(candidateCommand).subscribe((value) => (result = value));

    expect(port.createCandidate).toHaveBeenCalledWith({ ...candidateCommand, examRoundId: 12 });
    expect(result).toMatchObject({ ok: true, value: candidate, current: true });
    expect(service.actionBusy()).toBe(false);
    expect(workspace.refresh).toHaveBeenCalledOnce();
  });

  it('passes candidate updates and deletions through the feature port', () => {
    port.updateCandidate.mockReturnValue(of(candidate));
    port.deleteCandidate.mockReturnValue(of(undefined));
    const update = { id: candidate.id, payload: candidateCommand };

    service.updateCandidate(update).subscribe();
    service.deleteCandidate(candidate.id).subscribe();

    expect(port.updateCandidate).toHaveBeenCalledWith({
      id: candidate.id,
      payload: { ...candidateCommand, examRoundId: 12 },
    });
    expect(port.deleteCandidate).toHaveBeenCalledWith(candidate.id);
    expect(workspace.refresh).toHaveBeenCalledTimes(2);
  });

  it('does not start a request or change state before subscription', () => {
    const operation = service.createCandidate(candidateCommand);

    expect(port.createCandidate).not.toHaveBeenCalled();
    expect(service.actionBusy()).toBe(false);
    expect(service.requestState()).toEqual({ status: 'idle' });

    operation.subscribe();
    expect(port.createCandidate).toHaveBeenCalledOnce();
  });

  it('shares one mutation across multiple subscriptions to the same operation', () => {
    port.createCandidate.mockReturnValue(of(candidate));
    const operation = service.createCandidate(candidateCommand);
    const results: unknown[] = [];

    operation.subscribe((value) => results.push(value));
    operation.subscribe((value) => results.push(value));

    expect(port.createCandidate).toHaveBeenCalledOnce();
    expect(results).toHaveLength(2);
    expect(service.actionBusy()).toBe(false);
  });

  it('returns a typed error result without leaving a permanent busy state', () => {
    const error = new Error('request failed');
    port.createCandidate.mockReturnValue(throwError(() => error));
    let result: unknown;

    service.createCandidate(candidateCommand).subscribe((value) => (result = value));

    expect(result).toMatchObject({ ok: false, error, current: true });
    expect(service.actionBusy()).toBe(false);
    expect(service.requestState().status).toBe('error');
  });

  it('clears busy state when the port throws synchronously', () => {
    const error = new Error('synchronous failure');
    port.createCandidate.mockImplementation(() => {
      throw error;
    });
    let result: unknown;

    service.createCandidate(candidateCommand).subscribe((value) => (result = value));

    expect(result).toMatchObject({ ok: false, error, current: true });
    expect(service.actionBusy()).toBe(false);
    expect(service.requestState()).toMatchObject({ status: 'error', error });
  });

  it('does not start a second write while the first one is pending', () => {
    const pending = new Subject<Candidate>();
    port.createCandidate.mockReturnValue(pending);
    service.createCandidate(candidateCommand).subscribe();
    service.createCandidate(candidateCommand).subscribe();

    expect(port.createCandidate).toHaveBeenCalledOnce();
    expect(service.actionBusy()).toBe(true);

    pending.next(candidate);
    pending.complete();
    expect(service.actionBusy()).toBe(false);
  });

  it('marks a member response stale after the selected committee changes', () => {
    const pending = new Subject<CommitteeMember>();
    port.createCommitteeMember.mockReturnValue(pending);
    let result: unknown;
    service.createMember({ committeeId: 3 } as never).subscribe((value) => (result = value));
    workspace.selectedCommitteeId.mockReturnValue(4);

    pending.next(member);
    pending.complete();

    expect(result).toMatchObject({ ok: true, value: member, current: false });
    expect(service.actionBusy()).toBe(false);
    expect(service.requestState().status).toBe('idle');
  });

  it('toggles a committee member through the feature port', () => {
    port.updateCommitteeMember.mockReturnValue(of({ ...member, isActive: false }));
    let result: unknown;

    service.toggleMember(member).subscribe((value) => (result = value));

    expect(port.updateCommitteeMember).toHaveBeenCalledWith(member.id, { isActive: false });
    expect(result).toMatchObject({
      ok: true,
      value: { ...member, isActive: false },
      current: true,
    });
    expect(workspace.refresh).toHaveBeenCalledOnce();
  });

  it('marks candidate responses stale after the selected round changes', () => {
    const pending = new Subject<Candidate>();
    port.createCandidate.mockReturnValue(pending);
    let result: unknown;
    service.createCandidate(candidateCommand).subscribe((value) => (result = value));
    roundContext.roundId.mockReturnValue(13);

    pending.next(candidate);
    pending.complete();

    expect(result).toMatchObject({ ok: true, value: candidate, current: false });
    expect(service.requestState().status).toBe('idle');
    expect(service.actionBusy()).toBe(false);
  });

  it('clears busy state when a pending request is aborted', () => {
    const pending = new Subject<Candidate>();
    port.createCandidate.mockReturnValue(pending);
    const operation = service.createCandidate(candidateCommand);
    const subscription = operation.subscribe();

    subscription.unsubscribe();

    expect(service.actionBusy()).toBe(false);
    expect(service.requestState().status).toBe('idle');

    operation.subscribe();
    expect(port.createCandidate).toHaveBeenCalledOnce();
  });
});
