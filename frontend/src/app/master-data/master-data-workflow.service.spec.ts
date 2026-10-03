import { TestBed } from '@angular/core/testing';
import { of, Subject, throwError } from 'rxjs';

import { RoundContextService } from '../api/round-context.service';
import { AuthService } from '../auth/auth.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { DashboardProjectionService } from '../dashboard/dashboard-projection.service';
import type {
  Candidate,
  CandidateWorkspace,
  CommitteeMember,
  CommitteeWorkspace,
} from './master-data.models';
import { MASTER_DATA_PORT } from './master-data.port';
import { MasterDataWorkflowService } from './master-data-workflow.service';

describe('MasterDataWorkflowService', () => {
  let service: MasterDataWorkflowService;
  let port: {
    loadCandidateWorkspace: ReturnType<typeof vi.fn>;
    loadCommitteeWorkspace: ReturnType<typeof vi.fn>;
    createCandidate: ReturnType<typeof vi.fn>;
    updateCandidate: ReturnType<typeof vi.fn>;
    deleteCandidate: ReturnType<typeof vi.fn>;
    createCommitteeMember: ReturnType<typeof vi.fn>;
    updateCommitteeMember: ReturnType<typeof vi.fn>;
  };
  let roundContext: { roundId: ReturnType<typeof vi.fn> };
  let workspace: {
    refreshCandidateReferences: ReturnType<typeof vi.fn>;
    refreshCommitteeReferences: ReturnType<typeof vi.fn>;
  };
  let dashboard: {
    refreshCandidateReferences: ReturnType<typeof vi.fn>;
    refreshCommitteeMembers: ReturnType<typeof vi.fn>;
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
  const candidateCommand = {
    firstName: 'Ada',
    lastName: 'Lovelace',
    examNumber: 'EX-7',
    specialization: 'application_development',
    trainingCompany: 'Testbetrieb',
  };

  beforeEach(() => {
    port = {
      loadCandidateWorkspace: vi.fn(() => of(emptyCandidates)),
      loadCommitteeWorkspace: vi.fn(() => of(emptyCommittees)),
      createCandidate: vi.fn(),
      updateCandidate: vi.fn(),
      deleteCandidate: vi.fn(),
      createCommitteeMember: vi.fn(),
      updateCommitteeMember: vi.fn(),
    };
    roundContext = { roundId: vi.fn(() => 12) };
    workspace = {
      refreshCandidateReferences: vi.fn(),
      refreshCommitteeReferences: vi.fn(),
    };
    dashboard = {
      refreshCandidateReferences: vi.fn(),
      refreshCommitteeMembers: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [
        MasterDataWorkflowService,
        { provide: MASTER_DATA_PORT, useValue: port },
        { provide: ApplicationWorkspaceService, useValue: workspace },
        { provide: DashboardProjectionService, useValue: dashboard },
        { provide: RoundContextService, useValue: roundContext },
        {
          provide: AuthService,
          useValue: { state: () => 'authenticated', markAnonymous: vi.fn() },
        },
      ],
    });
    service = TestBed.inject(MasterDataWorkflowService);
  });

  it('exposes feature-owned candidate and committee workspace projections', () => {
    const candidateWorkspace: CandidateWorkspace = {
      candidates: [
        {
          candidate,
          roundCandidate: { attemptNumber: 2, requiresMep: true },
        },
      ],
      assignments: [
        {
          id: 1,
          candidateId: 7,
          examRoundId: 12,
          assignedAt: '2026-01-01T00:00:00Z',
          endedAt: null,
          changeReason: null,
        },
      ],
      examRounds: [{ id: 12, name: 'Winter 2026', halfYearId: 4, committeeId: 3 }],
      committees: [{ id: 3, name: 'Prüfungsausschuss' }],
      activeRound: {
        id: 12,
        name: 'Winter 2026',
        halfYearId: 4,
        committeeId: 3,
        status: 'planning',
      },
    };
    const committeeWorkspace: CommitteeWorkspace = {
      committees: [{ id: 3, name: 'Prüfungsausschuss', occupation: 'IT', ihk: 'IHK' }],
      members: [member],
      persons: [{ id: 9, firstName: 'Grace', lastName: 'Hopper', email: 'grace@example.invalid' }],
    };
    service.candidateWorkspace.set(candidateWorkspace);
    service.committeeWorkspace.set(committeeWorkspace);

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

  it('keeps candidate and committee read failures independent', () => {
    port.loadCandidateWorkspace.mockReturnValue(
      throwError(() => new Error('candidate read failed')),
    );
    port.loadCommitteeWorkspace.mockReturnValue(of({ committees: [], members: [], persons: [] }));

    service.loadCandidates();
    service.loadCommittees();

    expect(service.candidateError()).toBe(true);
    expect(service.committeeError()).toBe(false);
    expect(service.committeeWorkspace()).toEqual({ committees: [], members: [], persons: [] });
  });

  it('discards a candidate read that completes after its route closes', () => {
    const pending = new Subject<CandidateWorkspace>();
    port.loadCandidateWorkspace.mockReturnValueOnce(pending);

    service.loadCandidates();
    service.clearCandidates();
    pending.next({ ...emptyCandidates, candidates: [{ candidate }] });
    pending.complete();

    expect(service.candidateWorkspace()).toBeNull();
    expect(service.candidateLoading()).toBe(false);
  });

  it('passes the active round to the port and refreshes after a successful command', () => {
    port.createCandidate.mockReturnValue(of(candidate));
    let result: unknown;

    service.createCandidate(candidateCommand).subscribe((value) => (result = value));

    expect(port.createCandidate).toHaveBeenCalledWith({ ...candidateCommand, examRoundId: 12 });
    expect(result).toMatchObject({ ok: true, value: candidate, current: true });
    expect(workspace.refreshCandidateReferences).toHaveBeenCalledOnce();
    expect(dashboard.refreshCandidateReferences).toHaveBeenCalledOnce();
    expect(service.actionBusy()).toBe(false);
    expect(port.loadCandidateWorkspace).toHaveBeenCalledWith(12);
    expect(port.loadCommitteeWorkspace).not.toHaveBeenCalled();
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
    expect(port.loadCandidateWorkspace).toHaveBeenCalledTimes(2);
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
    port.loadCommitteeWorkspace.mockReturnValue(
      of({
        committees: [
          { id: 3, name: 'Ausschuss 3', occupation: null, ihk: null },
          { id: 4, name: 'Ausschuss 4', occupation: null, ihk: null },
        ],
        members: [member],
        persons: [],
      }),
    );
    let result: unknown;
    service.createMember({ committeeId: 3 } as never).subscribe((value) => (result = value));
    service.selectedCommitteeId.set(4);

    pending.next(member);
    pending.complete();

    expect(result).toMatchObject({ ok: true, value: member, current: false });
    expect(port.loadCommitteeWorkspace).toHaveBeenCalledOnce();
    expect(workspace.refreshCommitteeReferences).toHaveBeenCalledOnce();
    expect(dashboard.refreshCommitteeMembers).toHaveBeenCalledOnce();
    expect(service.committeeWorkspace()?.members).toEqual([member]);
    expect(service.selectedCommitteeId()).toBe(4);
    expect(service.actionBusy()).toBe(false);
    expect(service.requestState().status).toBe('idle');
  });

  it('toggles a committee member through the feature port', () => {
    service.selectedCommitteeId.set(3);
    port.updateCommitteeMember.mockReturnValue(of({ ...member, isActive: false }));
    let result: unknown;

    service.toggleMember(member).subscribe((value) => (result = value));

    expect(port.updateCommitteeMember).toHaveBeenCalledWith(member.id, { isActive: false });
    expect(result).toMatchObject({
      ok: true,
      value: { ...member, isActive: false },
      current: true,
    });
    expect(port.loadCommitteeWorkspace).toHaveBeenCalledOnce();
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

const emptyCandidates: CandidateWorkspace = {
  candidates: [],
  assignments: [],
  examRounds: [],
  committees: [],
  activeRound: null,
};
const emptyCommittees: CommitteeWorkspace = { committees: [], members: [], persons: [] };
