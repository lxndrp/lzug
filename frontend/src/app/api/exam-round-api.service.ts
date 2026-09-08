import type {
  ExamHalfYear,
  ExamRound,
  ExamRoundCreate,
  ExamRoundLifecycle,
} from './planning.models';
import { Injectable, inject } from '@angular/core';

import { ApiClient } from './api-client.service';

/** Exam-half-year and exam-round lifecycle operations. */

@Injectable({ providedIn: 'root' })
export class ExamRoundApiService {
  private readonly client = inject(ApiClient);
  listExamHalfYears() {
    return this.client.list<ExamHalfYear>('/api/exam-half-years');
  }

  listExamRounds() {
    return this.client.list<ExamRound>('/api/exam-rounds');
  }

  createExamHalfYear(payload: Pick<ExamHalfYear, 'season' | 'year' | 'status'>) {
    return this.client.post<ExamHalfYear>('/api/exam-half-years', payload);
  }

  updateExamHalfYear(
    id: number,
    payload: Partial<Pick<ExamHalfYear, 'season' | 'year' | 'status'>>,
  ) {
    return this.client.patch<ExamHalfYear>(`/api/exam-half-years/${id}`, payload);
  }

  createExamRound(payload: ExamRoundCreate) {
    return this.client.post<ExamRound>('/api/exam-rounds', payload);
  }

  getExamRoundLifecycle(roundId: number) {
    return this.client.get<ExamRoundLifecycle>(`/api/exam-rounds/${roundId}/lifecycle`);
  }

  closeExamRound(roundId: number, revision: number) {
    return this.client.post<ExamRoundLifecycle>(`/api/exam-rounds/${roundId}/closure`, {
      revision,
      confirmed: true,
    });
  }

  cancelExamRound(roundId: number, revision: number, reason: string) {
    return this.client.post<ExamRoundLifecycle>(`/api/exam-rounds/${roundId}/cancellation`, {
      revision,
      confirmed: true,
      reason,
    });
  }

  reopenExamRound(
    roundId: number,
    payload: {
      revision: number;
      occasion: string;
      source: string;
      reason: string;
      scope: Array<{ kind: string; entity_id: number }>;
    },
  ) {
    return this.client.post<ExamRoundLifecycle>(`/api/exam-rounds/${roundId}/reopenings`, payload);
  }

  deleteEmptyExamRound(roundId: number) {
    return this.client.delete<void>(`/api/exam-rounds/${roundId}`);
  }

  setRoundCandidateTerminalStatus(
    roundId: number,
    roundCandidateId: number,
    payload: {
      revision: number;
      terminal_status: string;
      reason?: string;
      effective_new_round_id?: number;
      postponed_until?: string;
      ihk_decision_reference?: string;
    },
  ) {
    return this.client.put<ExamRoundLifecycle>(
      `/api/exam-rounds/${roundId}/candidates/${roundCandidateId}/terminal-status`,
      payload,
    );
  }

  documentExamRoundIhkStatus(
    roundId: number,
    resultId: number,
    documentStatus: string,
    documentReference: string,
  ) {
    return this.client.put<ExamRoundLifecycle>(
      `/api/exam-rounds/${roundId}/results/${resultId}/ihk-status`,
      {
        document_status: documentStatus,
        document_reference: documentReference,
      },
    );
  }

  /**
   * Load and deterministically join the collections used by planning views.
   *
   * Slots and assignments are deliberately fetched as full collections and
   * filtered locally because their current endpoints are not round-scoped.
   */
}
