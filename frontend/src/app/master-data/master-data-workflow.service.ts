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
import type { CandidateWorkspace, CommitteeWorkspace } from './master-data.models';
import { AuthService } from '../auth/auth.service';
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
  private readonly auth = inject(AuthService);
  private readonly requestCounter = signal(0);
  private readonly state = signal<MasterDataRequestState>({ status: 'idle' });

  readonly requestState = this.state.asReadonly();
  readonly actionBusy = computed(() => this.state().status === 'pending');
  readonly candidateWorkspace = signal<CandidateWorkspace | null>(null);
  readonly committeeWorkspace = signal<CommitteeWorkspace | null>(null);
  readonly candidateLoading = signal(false);
  readonly candidateError = signal(false);
  readonly committeeLoading = signal(false);
  readonly committeeError = signal(false);
  readonly selectedCommitteeId = signal<number | null>(null);
  private candidateReadGeneration = 0;
  private committeeReadGeneration = 0;

  constructor() {
    this.sessionScope.changes$.subscribe(() => {
      this.requestCounter.update((counter) => counter + 1);
      this.state.set({ status: 'idle' });
      this.candidateReadGeneration += 1;
      this.committeeReadGeneration += 1;
      this.candidateWorkspace.set(null);
      this.committeeWorkspace.set(null);
      this.selectedCommitteeId.set(null);
      this.candidateLoading.set(false);
      this.committeeLoading.set(false);
      this.candidateError.set(false);
      this.committeeError.set(false);
    });
  }

  loadCandidates(): void {
    if (this.auth.state() !== 'authenticated') return;
    const roundId = this.roundContext.roundId();
    const generation = ++this.candidateReadGeneration;
    const sessionGeneration = this.sessionScope.generation();
    if (this.candidateWorkspace()?.activeRound?.id !== roundId) this.candidateWorkspace.set(null);
    this.candidateLoading.set(true);
    this.candidateError.set(false);
    this.sessionScope
      .forCurrentSession(this.port.loadCandidateWorkspace(roundId))
      .pipe(
        finalize(() => {
          if (generation === this.candidateReadGeneration) this.candidateLoading.set(false);
        }),
      )
      .subscribe({
        next: (workspace) => {
          if (
            generation !== this.candidateReadGeneration ||
            sessionGeneration !== this.sessionScope.generation() ||
            roundId !== this.roundContext.roundId()
          )
            return;
          this.candidateWorkspace.set(workspace);
        },
        error: (error: { kind?: string }) => {
          if (
            generation !== this.candidateReadGeneration ||
            sessionGeneration !== this.sessionScope.generation() ||
            roundId !== this.roundContext.roundId()
          )
            return;
          this.candidateError.set(true);
          if (error.kind === 'unauthenticated') this.auth.markAnonymous();
        },
      });
  }

  loadCommittees(): void {
    if (this.auth.state() !== 'authenticated') return;
    const generation = ++this.committeeReadGeneration;
    const sessionGeneration = this.sessionScope.generation();
    this.committeeLoading.set(true);
    this.committeeError.set(false);
    this.sessionScope
      .forCurrentSession(this.port.loadCommitteeWorkspace())
      .pipe(
        finalize(() => {
          if (generation === this.committeeReadGeneration) this.committeeLoading.set(false);
        }),
      )
      .subscribe({
        next: (workspace) => {
          if (
            generation !== this.committeeReadGeneration ||
            sessionGeneration !== this.sessionScope.generation()
          )
            return;
          this.committeeWorkspace.set(workspace);
          if (!workspace.committees.some(({ id }) => id === this.selectedCommitteeId())) {
            this.selectedCommitteeId.set(workspace.committees[0]?.id ?? null);
          }
        },
        error: (error: { kind?: string }) => {
          if (
            generation !== this.committeeReadGeneration ||
            sessionGeneration !== this.sessionScope.generation()
          )
            return;
          this.committeeError.set(true);
          if (error.kind === 'unauthenticated') this.auth.markAnonymous();
        },
      });
  }

  selectCommittee(id: number | null): void {
    this.selectedCommitteeId.set(id);
  }

  createMember(
    payload: CommitteeMemberCommand,
  ): Observable<MasterDataWorkflowResult<CommitteeMember>> {
    const selectedCommitteeId = this.selectedCommitteeId();
    return this.run(
      `committee:${payload.committeeId}`,
      () => this.port.createCommitteeMember(payload),
      () =>
        selectedCommitteeId === payload.committeeId &&
        this.selectedCommitteeId() === selectedCommitteeId,
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
    const selectedCommitteeId = this.selectedCommitteeId();
    return this.run(
      `committee:${member.committeeId}`,
      () => this.port.updateCommitteeMember(member.id, update),
      () =>
        selectedCommitteeId === member.committeeId &&
        this.selectedCommitteeId() === selectedCommitteeId,
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
          if (!result.current) return;
          if (contextKey.startsWith('candidate:')) this.loadCandidates();
          else if (contextKey.startsWith('committee:')) this.loadCommittees();
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
