import type { ExamResult } from './execution.models';
import { Injectable, inject } from '@angular/core';

import { ApiClient } from './api-client.service';

/** Assessment, determination, communication, correction, and retention operations. */

@Injectable({ providedIn: 'root' })
export class ExamResultApiService {
  private readonly client = inject(ApiClient);
  getExamResult(dayId: number, slotId: number) {
    return this.client.get<ExamResult>(`/api/confirmed-plan-days/${dayId}/slots/${slotId}/result`);
  }

  saveIndividualAssessment(
    resultId: number,
    version: number,
    componentKey: string,
    criterionKey: string,
    rawPoints: string,
    rationale: string,
    submitted: boolean,
    changeReason?: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client.post<ExamResult>(`/api/exam-results/${resultId}/individual-assessments`, {
      version,
      component_key: componentKey,
      criterion_key: criterionKey,
      raw_points: rawPoints,
      rationale: rationale.trim() || null,
      submitted,
      ...(changeReason?.trim() ? { change_reason: changeReason.trim() } : {}),
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  withdrawIndividualAssessment(
    resultId: number,
    version: number,
    assessmentId: number,
    reason: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client.post<ExamResult>(
      `/api/exam-results/${resultId}/individual-assessments/${assessmentId}/withdraw`,
      { version, reason: reason.trim(), ...(dayRevisions ? { day_revisions: dayRevisions } : {}) },
    );
  }

  discloseAssessments(
    resultId: number,
    version: number,
    componentKey: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client.post<ExamResult>(`/api/exam-results/${resultId}/disclosures`, {
      version,
      component_key: componentKey,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  determineComponent(
    resultId: number,
    version: number,
    componentKey: string,
    points: string,
    rationale: string,
    participants: number[],
    dissent: Array<{ member_id: number; statement: string }>,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client.post<ExamResult>(`/api/exam-results/${resultId}/committee-assessments`, {
      version,
      component_key: componentKey,
      points,
      rationale: rationale.trim() || null,
      participant_member_ids: participants,
      vote: { yes: participants, no: [], abstain: [] },
      dissent,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  recordExternalResult(
    resultId: number,
    version: number,
    payload: {
      area_key: string;
      points: string;
      grade?: string;
      professional_status: string;
      determining_authority: string;
      source_reference: string;
      correction_reason?: string;
    },
    dayRevisions?: Record<string, number>,
  ) {
    return this.client.post<ExamResult>(`/api/exam-results/${resultId}/external-results`, {
      version,
      ...payload,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  confirmExternalResult(
    resultId: number,
    version: number,
    externalResultId: number,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client.post<ExamResult>(
      `/api/exam-results/${resultId}/external-results/${externalResultId}/confirm`,
      { version, ...(dayRevisions ? { day_revisions: dayRevisions } : {}) },
    );
  }

  determineExamResult(
    resultId: number,
    version: number,
    participants: number[],
    dissent: Array<{ member_id: number; statement: string }>,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client.post<ExamResult>(`/api/exam-results/${resultId}/determine`, {
      version,
      participant_member_ids: participants,
      vote: { yes: participants, no: [], abstain: [] },
      dissent,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  confirmResultRecord(resultId: number, version: number, dayRevisions?: Record<string, number>) {
    return this.client.post<ExamResult>(`/api/exam-results/${resultId}/record-confirmations`, {
      version,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  openResultCorrection(
    resultId: number,
    version: number,
    reason: string,
    reopeningReference?: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client.post<ExamResult>(`/api/exam-results/${resultId}/corrections`, {
      version,
      reason: reason.trim(),
      ...(reopeningReference?.trim() ? { reopening_reference: reopeningReference.trim() } : {}),
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  communicateExamResult(
    resultId: number,
    version: number,
    method: string,
    communicatedAt: string,
    externalDocumentReference?: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client.post<ExamResult>(`/api/exam-results/${resultId}/communications`, {
      version,
      method: method.trim(),
      communicated_at: new Date(communicatedAt).toISOString(),
      ...(externalDocumentReference?.trim()
        ? {
            external_document_status: 'extern dokumentiert',
            external_document_reference: externalDocumentReference.trim(),
          }
        : {}),
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  setExamResultRetention(
    resultId: number,
    version: number,
    payload: {
      period_start?: string;
      retain_until?: string;
      legal_hold: boolean;
      hold_reason?: string;
      release_reason?: string;
    },
    dayRevisions?: Record<string, number>,
  ) {
    return this.client.put<ExamResult>(`/api/exam-results/${resultId}/retention`, {
      version,
      ...payload,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }
}
