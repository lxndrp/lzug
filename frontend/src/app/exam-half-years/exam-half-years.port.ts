import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  CreateExamRound,
  ExamHalfYear,
  ExamRound,
  LifecycleExport,
  LifecycleExportFormat,
  RoundCandidateTerminalStatus,
  RoundLifecycle,
  RoundReopening,
} from './exam-half-years.models';

/** Examination-context operations required by the half-year feature. */
export interface ExamHalfYearsPort {
  listHalfYears(): Observable<ExamHalfYear[]>;
  listRounds(): Observable<ExamRound[]>;
  createRound(payload: CreateExamRound): Observable<ExamRound>;
  getRoundLifecycle(roundId: number): Observable<RoundLifecycle>;
  closeRound(roundId: number, revision: number): Observable<RoundLifecycle>;
  cancelRound(roundId: number, revision: number, reason: string): Observable<RoundLifecycle>;
  reopenRound(roundId: number, payload: RoundReopening): Observable<RoundLifecycle>;
  deleteEmptyRound(roundId: number): Observable<void>;
  setCandidateTerminalStatus(
    roundId: number,
    roundCandidateId: number,
    payload: RoundCandidateTerminalStatus,
  ): Observable<RoundLifecycle>;
  documentIhkStatus(
    roundId: number,
    resultId: number,
    documentStatus: string,
    documentReference: string,
  ): Observable<RoundLifecycle>;
  exportLifecycle(roundId: number, format: LifecycleExportFormat): Observable<LifecycleExport>;
}

export const EXAM_HALF_YEARS_PORT = new InjectionToken<ExamHalfYearsPort>('EXAM_HALF_YEARS_PORT');
