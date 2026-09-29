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

import type { Candidate, CommitteeMember } from '../api/api.models';
import { MasterDataApiService } from '../api/master-data-api.service';
import { RoundContextService } from '../api/round-context.service';
import type { CandidatePayload, CandidateUpdate } from '../candidates/candidates.component';
import type { CommitteeMemberPayload } from '../committee/committee.component';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

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
  private readonly api = inject(MasterDataApiService);
  private readonly roundContext = inject(RoundContextService);
  private readonly workspace = inject(ApplicationWorkspaceService);
  private readonly requestCounter = signal(0);
  private readonly state = signal<MasterDataRequestState>({ status: 'idle' });

  readonly requestState = this.state.asReadonly();
  readonly actionBusy = computed(() => this.state().status === 'pending');

  createMember(
    payload: CommitteeMemberPayload,
  ): Observable<MasterDataWorkflowResult<CommitteeMember>> {
    const selectedCommitteeId = this.workspace.selectedCommitteeId();
    return this.run(
      `committee:${payload.committee_id}`,
      () => this.api.createMember(payload),
      () =>
        selectedCommitteeId === payload.committee_id &&
        this.workspace.selectedCommitteeId() === selectedCommitteeId,
    );
  }

  createCandidate(payload: CandidatePayload): Observable<MasterDataWorkflowResult<Candidate>> {
    const roundId = this.roundContext.roundId();
    return this.run(
      `candidate:${roundId}:create`,
      () => this.api.createCandidate(payload),
      () => this.roundContext.roundId() === roundId,
    );
  }

  deleteCandidate(id: number): Observable<MasterDataWorkflowResult<void>> {
    const roundId = this.roundContext.roundId();
    return this.run(
      `candidate:${roundId}:${id}`,
      () => this.api.deleteCandidate(id),
      () => this.roundContext.roundId() === roundId,
    );
  }

  updateCandidate(update: CandidateUpdate): Observable<MasterDataWorkflowResult<Candidate>> {
    const roundId = this.roundContext.roundId();
    return this.run(
      `candidate:${roundId}:${update.id}`,
      () => this.api.updateCandidate(update.id, update.payload),
      () => this.roundContext.roundId() === roundId,
    );
  }

  toggleMember(member: CommitteeMember): Observable<MasterDataWorkflowResult<CommitteeMember>> {
    const nextActive = member.is_active ? 0 : 1;
    const selectedCommitteeId = this.workspace.selectedCommitteeId();
    return this.run(
      `committee:${member.committee_id}`,
      () => this.api.updateMember(member.id, { is_active: nextActive }),
      () =>
        selectedCommitteeId === member.committee_id &&
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

      return defer(request).pipe(
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
