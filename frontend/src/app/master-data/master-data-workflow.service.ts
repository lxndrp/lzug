import { Injectable, computed, inject, signal } from '@angular/core';
import {
  EMPTY,
  Observable,
  ReplaySubject,
  catchError,
  defer,
  finalize,
  map,
  of,
  share,
  tap,
} from 'rxjs';

import { RoundContextService } from '../api/round-context.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { MASTER_DATA_PORT } from './master-data.port';
import type {
  Candidate,
  CandidateCommand,
  CandidateUpdate,
  CommitteeMember,
  CommitteeMemberCommand,
  CommitteeMemberUpdate,
} from './master-data.models';

export type MasterDataWorkflowResult<T> =
  | { ok: true; value: T; requestId: number; contextKey: string; current: boolean }
  | { ok: false; error: unknown; requestId: number; contextKey: string; current: boolean };

export type MasterDataRequestState =
  | { status: 'idle' }
  | { status: 'pending'; requestId: number; contextKey: string }
  | { status: 'success'; requestId: number; contextKey: string }
  | { status: 'error'; requestId: number; contextKey: string; error: unknown };

/** Candidate and committee-member commands owned outside the application shell. */
@Injectable({ providedIn: 'root' })
export class MasterDataWorkflowService {
  private readonly port = inject(MASTER_DATA_PORT);
  private readonly roundContext = inject(RoundContextService);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly workspace = inject(ApplicationWorkspaceService);
  private readonly requestCounter = signal(0);
  private readonly state = signal<MasterDataRequestState>({ status: 'idle' });

  readonly requestState = this.state.asReadonly();
  readonly actionBusy = computed(() => this.state().status === 'pending');
  readonly candidateWorkspace = computed(() => this.workspace.candidateWorkspace());
  readonly committeeWorkspace = computed(() => this.workspace.committeeWorkspace());

  constructor() {
    this.sessionScope.changes$.subscribe(() => {
      this.requestCounter.update((counter) => counter + 1);
      this.state.set({ status: 'idle' });
    });
  }

  createMember(
    payload: CommitteeMemberCommand,
  ): Observable<MasterDataWorkflowResult<CommitteeMember>> {
    const selectedCommitteeId = this.workspace.selectedCommitteeId();
    return this.run(
      `committee:${payload.committeeId}`,
      () => this.port.createCommitteeMember(payload),
      () =>
        selectedCommitteeId === payload.committeeId &&
        this.workspace.selectedCommitteeId() === selectedCommitteeId,
    );
  }

  createCandidate(payload: CandidateCommand): Observable<MasterDataWorkflowResult<Candidate>> {
    const roundId = this.roundContext.roundId();
    return this.run(
      `candidate:${roundId}:create`,
      () => this.port.createCandidate({ ...payload, examRoundId: payload.examRoundId ?? roundId }),
      () => this.roundContext.roundId() === roundId,
    );
  }

  deleteCandidate(id: number): Observable<MasterDataWorkflowResult<void>> {
    const roundId = this.roundContext.roundId();
    return this.run(
      `candidate:${roundId}:${id}`,
      () => this.port.deleteCandidate(id),
      () => this.roundContext.roundId() === roundId,
    );
  }

  updateCandidate(update: CandidateUpdate): Observable<MasterDataWorkflowResult<Candidate>> {
    const roundId = this.roundContext.roundId();
    return this.run(
      `candidate:${roundId}:${update.id}`,
      () =>
        this.port.updateCandidate({
          ...update,
          payload: { ...update.payload, examRoundId: update.payload.examRoundId ?? roundId },
        }),
      () => this.roundContext.roundId() === roundId,
    );
  }

  toggleMember(member: CommitteeMember): Observable<MasterDataWorkflowResult<CommitteeMember>> {
    const update: CommitteeMemberUpdate = { isActive: !member.isActive };
    const selectedCommitteeId = this.workspace.selectedCommitteeId();
    return this.run(
      `committee:${member.committeeId}`,
      () => this.port.updateCommitteeMember(member.id, update),
      () =>
        selectedCommitteeId === member.committeeId &&
        this.workspace.selectedCommitteeId() === selectedCommitteeId,
    );
  }

  private run<T>(
    contextKey: string,
    request: () => Observable<T>,
    isCurrentContext: () => boolean = () => true,
  ): Observable<MasterDataWorkflowResult<T>> {
    let started = false;
    return defer(() => {
      if (started || this.actionBusy()) {
        started = true;
        return EMPTY;
      }
      started = true;
      const requestId = this.requestCounter() + 1;
      this.requestCounter.set(requestId);
      this.state.set({ status: 'pending', requestId, contextKey });

      return this.sessionScope.forCurrentSession(defer(request)).pipe(
        map((value): MasterDataWorkflowResult<T> => ({
          ok: true,
          value,
          requestId,
          contextKey,
          current: this.requestCounter() === requestId && isCurrentContext(),
        })),
        tap((result) => {
          if (this.requestCounter() === requestId) {
            this.state.set(
              result.current ? { status: 'success', requestId, contextKey } : { status: 'idle' },
            );
          }
          this.workspace.refresh();
        }),
        catchError((error: unknown) => {
          const current = this.requestCounter() === requestId && isCurrentContext();
          if (this.requestCounter() === requestId) {
            this.state.set(
              current ? { status: 'error', requestId, contextKey, error } : { status: 'idle' },
            );
          }
          return of<MasterDataWorkflowResult<T>>({
            ok: false,
            error,
            requestId,
            contextKey,
            current,
          });
        }),
        finalize(() => {
          if (this.requestCounter() === requestId && this.state().status === 'pending') {
            this.state.set({ status: 'idle' });
          }
        }),
      );
    }).pipe(
      share({
        connector: () => new ReplaySubject<MasterDataWorkflowResult<T>>(1),
        resetOnError: false,
        resetOnComplete: false,
        resetOnRefCountZero: true,
      }),
    );
  }
}
