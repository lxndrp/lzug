import { TestBed } from '@angular/core/testing';
import { of, Subject, throwError } from 'rxjs';

import type { Candidate, CommitteeMember } from '../api/api.models';
import { MasterDataApiService } from '../api/master-data-api.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { MasterDataWorkflowService } from './master-data-workflow.service';

describe('MasterDataWorkflowService', () => {
  let service: MasterDataWorkflowService;
  let api: {
    createCandidate: ReturnType<typeof vi.fn>;
    createMember: ReturnType<typeof vi.fn>;
  };
  let workspace: {
    selectedCommitteeId: ReturnType<typeof vi.fn>;
    refresh: ReturnType<typeof vi.fn>;
  };

  const candidate = {
    id: 7,
    first_name: 'Ada',
    last_name: 'Lovelace',
  } as Candidate;
  const member = {
    id: 8,
    committee_id: 3,
    first_name: 'Grace',
    last_name: 'Hopper',
  } as CommitteeMember;

  beforeEach(() => {
    api = {
      createCandidate: vi.fn(),
      createMember: vi.fn(),
    };
    workspace = {
      selectedCommitteeId: vi.fn(() => 3),
      refresh: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [
        MasterDataWorkflowService,
        { provide: MasterDataApiService, useValue: api },
        { provide: ApplicationWorkspaceService, useValue: workspace },
      ],
    });
    service = TestBed.inject(MasterDataWorkflowService);
  });

  it('returns a typed successful result and clears busy state', () => {
    api.createCandidate.mockReturnValue(of(candidate));
    let result: unknown;

    service.createCandidate({ first_name: 'Ada' } as never).subscribe((value) => (result = value));

    expect(result).toMatchObject({ ok: true, value: candidate, current: true });
    expect(service.actionBusy()).toBe(false);
    expect(workspace.refresh).toHaveBeenCalledOnce();
  });

  it('returns a typed error result without leaving a permanent busy state', () => {
    const error = new Error('request failed');
    api.createCandidate.mockReturnValue(throwError(() => error));
    let result: unknown;

    service.createCandidate({ first_name: 'Ada' } as never).subscribe((value) => (result = value));

    expect(result).toMatchObject({ ok: false, error, current: true });
    expect(service.actionBusy()).toBe(false);
    expect(service.requestState().status).toBe('error');
  });

  it('does not start a second write while the first one is pending', () => {
    const pending = new Subject<Candidate>();
    api.createCandidate.mockReturnValue(pending);
    service.createCandidate({ first_name: 'Ada' } as never).subscribe();
    service.createCandidate({ first_name: 'Ada' } as never).subscribe();

    expect(api.createCandidate).toHaveBeenCalledOnce();
    expect(service.actionBusy()).toBe(true);

    pending.next(candidate);
    pending.complete();
    expect(service.actionBusy()).toBe(false);
  });

  it('marks a response stale after the selected committee changes', () => {
    const pending = new Subject<CommitteeMember>();
    api.createMember.mockReturnValue(pending);
    let result: unknown;
    service.createMember({ committee_id: 3 } as never).subscribe((value) => (result = value));
    workspace.selectedCommitteeId.mockReturnValue(4);

    pending.next(member);
    pending.complete();

    expect(result).toMatchObject({ ok: true, value: member, current: false });
    expect(service.actionBusy()).toBe(false);
    expect(service.requestState().status).toBe('idle');
  });

  it('clears busy state when a pending request is aborted', () => {
    const pending = new Subject<Candidate>();
    api.createCandidate.mockReturnValue(pending);
    const subscription = service.createCandidate({ first_name: 'Ada' } as never).subscribe();

    subscription.unsubscribe();

    expect(service.actionBusy()).toBe(false);
    expect(service.requestState().status).toBe('idle');
  });
});
