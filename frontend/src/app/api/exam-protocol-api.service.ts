import type {
  ExamProtocol,
  ExamProtocolDeclaration,
  ExamProtocolEntryCategory,
} from './execution.models';
import { Injectable, inject } from '@angular/core';

import { ApiClient } from './api-client.service';

/** Revisioned examination protocol operations. */

@Injectable({ providedIn: 'root' })
export class ExamProtocolApiService {
  private readonly client = inject(ApiClient);
  getExamProtocol(dayId: number, slotId: number) {
    return this.client.get<ExamProtocol>(
      `/api/confirmed-plan-days/${dayId}/slots/${slotId}/protocol`,
    );
  }

  updateExamProtocol(
    protocolId: number,
    version: number,
    declaration: ExamProtocolDeclaration,
    entries: Array<{
      category: ExamProtocolEntryCategory;
      statement: string;
      occurred_from: string;
      occurred_to: string | null;
    }>,
    changeReason?: string,
    dayRevision?: number,
  ) {
    return this.client.patch<ExamProtocol>(`/api/exam-protocols/${protocolId}`, {
      version,
      declaration,
      entries,
      ...(changeReason?.trim() ? { change_reason: changeReason.trim() } : {}),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  submitExamProtocol(protocolId: number, version: number, dayRevision?: number) {
    return this.client.post<ExamProtocol>(`/api/exam-protocols/${protocolId}/submit`, {
      version,
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  respondToExamProtocol(
    protocolId: number,
    version: number,
    response: 'confirmed' | 'reservation',
    entryId?: number,
    statement?: string,
    dayRevision?: number,
  ) {
    return this.client.post<ExamProtocol>(`/api/exam-protocols/${protocolId}/responses`, {
      version,
      response,
      ...(entryId === undefined ? {} : { entry_id: entryId }),
      ...(statement?.trim() ? { statement: statement.trim() } : {}),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  requestExamProtocolCorrection(
    protocolId: number,
    version: number,
    reason: string,
    dayRevision?: number,
  ) {
    return this.client.post<ExamProtocol>(`/api/exam-protocols/${protocolId}/correction-requests`, {
      version,
      reason: reason.trim(),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  openExamProtocolCorrection(
    protocolId: number,
    version: number,
    correctionRequestId: number,
    reason: string,
    reopeningReference?: string,
    dayRevision?: number,
  ) {
    return this.client.post<ExamProtocol>(`/api/exam-protocols/${protocolId}/open-correction`, {
      version,
      correction_request_id: correctionRequestId,
      reason: reason.trim(),
      ...(reopeningReference?.trim() ? { reopening_reference: reopeningReference.trim() } : {}),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }
}
