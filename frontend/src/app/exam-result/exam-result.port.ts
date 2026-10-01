import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  DetermineComponent,
  DetermineExamResult,
  ExamResult,
  RecordExternalResult,
  SaveIndividualAssessment,
  SetResultRetention,
} from './exam-result.models';

/** Reads and workflow commands required by the exam assessment/result feature. */
export interface ExamResultPort {
  get(dayId: number, slotId: number): Observable<ExamResult>;
  saveIndividualAssessment(command: SaveIndividualAssessment): Observable<ExamResult>;
  withdrawIndividualAssessment(
    resultId: number,
    version: number,
    assessmentId: number,
    reason: string,
    dayRevisions?: Record<string, number>,
  ): Observable<ExamResult>;
  discloseAssessments(
    resultId: number,
    version: number,
    componentKey: string,
    dayRevisions?: Record<string, number>,
  ): Observable<ExamResult>;
  determineComponent(command: DetermineComponent): Observable<ExamResult>;
  recordExternalResult(command: RecordExternalResult): Observable<ExamResult>;
  confirmExternalResult(
    resultId: number,
    version: number,
    externalResultId: number,
    dayRevisions?: Record<string, number>,
  ): Observable<ExamResult>;
  determineExamResult(command: DetermineExamResult): Observable<ExamResult>;
  confirmResultRecord(
    resultId: number,
    version: number,
    dayRevisions?: Record<string, number>,
  ): Observable<ExamResult>;
  openResultCorrection(
    resultId: number,
    version: number,
    reason: string,
    reopeningReference?: string,
    dayRevisions?: Record<string, number>,
  ): Observable<ExamResult>;
  communicateExamResult(
    resultId: number,
    version: number,
    method: string,
    communicatedAt: string,
    externalDocumentReference?: string,
    dayRevisions?: Record<string, number>,
  ): Observable<ExamResult>;
  setExamResultRetention(command: SetResultRetention): Observable<ExamResult>;
}

export const EXAM_RESULT_PORT = new InjectionToken<ExamResultPort>('EXAM_RESULT_PORT');
