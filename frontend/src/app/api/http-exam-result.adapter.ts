import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import type { ExamResult as ApiExamResult } from './execution.models';
import { ApiClient } from './api-client.service';
import type {
  DetermineComponent,
  DetermineExamResult,
  ExamResult,
  RecordExternalResult,
  SaveIndividualAssessment,
  SetResultRetention,
} from '../exam-result/exam-result.models';
import type { ExamResultPort } from '../exam-result/exam-result.port';

/** HTTP/OpenAPI adapter for the transport-neutral exam-result feature port. */
@Injectable({ providedIn: 'root' })
export class HttpExamResultAdapter implements ExamResultPort {
  private readonly client = inject(ApiClient);

  get(dayId: number, slotId: number) {
    return this.client
      .get<ApiExamResult>(`/api/confirmed-plan-days/${dayId}/slots/${slotId}/result`)
      .pipe(map(fromApiResult));
  }

  saveIndividualAssessment(command: SaveIndividualAssessment) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${command.resultId}/individual-assessments`, {
        version: command.version,
        component_key: command.componentKey,
        criterion_key: command.criterionKey,
        raw_points: command.rawPoints,
        rationale: command.rationale.trim() || null,
        submitted: command.submitted,
        ...(command.changeReason?.trim() ? { change_reason: command.changeReason.trim() } : {}),
        ...(command.dayRevisions ? { day_revisions: command.dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  withdrawIndividualAssessment(
    resultId: number,
    version: number,
    assessmentId: number,
    reason: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client
      .post<ApiExamResult>(
        `/api/exam-results/${resultId}/individual-assessments/${assessmentId}/withdraw`,
        {
          version,
          reason: reason.trim(),
          ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
        },
      )
      .pipe(map(fromApiResult));
  }

  discloseAssessments(
    resultId: number,
    version: number,
    componentKey: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${resultId}/disclosures`, {
        version,
        component_key: componentKey,
        ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  determineComponent(command: DetermineComponent) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${command.resultId}/committee-assessments`, {
        version: command.version,
        component_key: command.componentKey,
        points: command.points,
        rationale: command.rationale.trim() || null,
        participant_member_ids: command.participants,
        vote: command.vote,
        dissent: command.dissent.map(({ memberId, statement }) => ({
          member_id: memberId,
          statement,
        })),
        ...(command.dayRevisions ? { day_revisions: command.dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  recordExternalResult(command: RecordExternalResult) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${command.resultId}/external-results`, {
        version: command.version,
        area_key: command.areaKey,
        points: command.points,
        ...(command.grade ? { grade: command.grade } : {}),
        professional_status: command.professionalStatus,
        determining_authority: command.determiningAuthority,
        source_reference: command.sourceReference,
        ...(command.correctionReason ? { correction_reason: command.correctionReason } : {}),
        ...(command.dayRevisions ? { day_revisions: command.dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  confirmExternalResult(
    resultId: number,
    version: number,
    externalResultId: number,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client
      .post<ApiExamResult>(
        `/api/exam-results/${resultId}/external-results/${externalResultId}/confirm`,
        { version, ...(dayRevisions ? { day_revisions: dayRevisions } : {}) },
      )
      .pipe(map(fromApiResult));
  }

  determineExamResult(command: DetermineExamResult) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${command.resultId}/determine`, {
        version: command.version,
        participant_member_ids: command.participants,
        vote: command.vote,
        dissent: command.dissent.map(({ memberId, statement }) => ({
          member_id: memberId,
          statement,
        })),
        ...(command.dayRevisions ? { day_revisions: command.dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  confirmResultRecord(resultId: number, version: number, dayRevisions?: Record<string, number>) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${resultId}/record-confirmations`, {
        version,
        ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  openResultCorrection(
    resultId: number,
    version: number,
    reason: string,
    reopeningReference?: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${resultId}/corrections`, {
        version,
        reason: reason.trim(),
        ...(reopeningReference?.trim() ? { reopening_reference: reopeningReference.trim() } : {}),
        ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }

  communicateExamResult(
    resultId: number,
    version: number,
    method: string,
    communicatedAt: string,
    externalDocumentReference?: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.client
      .post<ApiExamResult>(`/api/exam-results/${resultId}/communications`, {
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
      })
      .pipe(map(fromApiResult));
  }

  setExamResultRetention(command: SetResultRetention) {
    return this.client
      .put<ApiExamResult>(`/api/exam-results/${command.resultId}/retention`, {
        version: command.version,
        ...(command.periodStart ? { period_start: command.periodStart } : {}),
        ...(command.retainUntil ? { retain_until: command.retainUntil } : {}),
        legal_hold: command.legalHold,
        ...(command.holdReason ? { hold_reason: command.holdReason } : {}),
        ...(command.releaseReason ? { release_reason: command.releaseReason } : {}),
        ...(command.dayRevisions ? { day_revisions: command.dayRevisions } : {}),
      })
      .pipe(map(fromApiResult));
  }
}

function fromApiResult(value: ApiExamResult): ExamResult {
  const { _links, ...transportFields } = value;
  return {
    ...camelize(transportFields),
    exportsLinks: {
      machine: _links?.['machine_export']?.href ?? null,
      human: _links?.['human_export']?.href ?? null,
    },
  } as ExamResult;
}

function camelize<T>(value: T, preserveRecordKeys = false): Camelized<T> {
  if (Array.isArray(value)) {
    return value.map((item) => camelize(item, preserveRecordKeys)) as Camelized<T>;
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        preserveRecordKeys
          ? key
          : key.replace(/_([a-z])/g, (_match, letter: string) => letter.toUpperCase()),
        camelize(item, key === 'component_minima' || key === 'external_minima'),
      ]),
    ) as Camelized<T>;
  }
  return value as Camelized<T>;
}

type Camelized<T> = T extends readonly (infer Item)[]
  ? Camelized<Item>[]
  : T extends object
    ? { [Key in keyof T as CamelKey<Key>]: Camelized<T[Key]> }
    : T;

type CamelKey<Key> = Key extends string
  ? Key extends `_${infer Rest}`
    ? CamelKey<Rest>
    : Key extends `${infer Prefix}_${infer Letter}${infer Rest}`
      ? `${Prefix}${Capitalize<Letter>}${CamelKey<Rest>}`
      : Key
  : Key;
