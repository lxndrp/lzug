import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  CloseExamDayCommand,
  ConfirmedPlanDayView,
  ExamDayClosure,
  ExamDayReopeningImpact,
  ExamDayReopeningScope,
  ReopenExamDayCommand,
  SaveAttendanceCommand,
  UpdateExecutionStatusCommand,
} from './exam-day.models';

/** Application boundary for examination-day reads and commands. */
export interface ExamDayPort {
  getConfirmedPlanDay(dayId: number): Observable<ConfirmedPlanDayView>;
  saveCandidateAttendance(command: SaveAttendanceCommand): Observable<ConfirmedPlanDayView>;
  saveMemberAttendance(command: SaveAttendanceCommand): Observable<ConfirmedPlanDayView>;
  startExamSlot(
    dayId: number,
    slotId: number,
    actualStartedAt: string | null,
    dayRevision?: number,
  ): Observable<ConfirmedPlanDayView>;
  updateExamSlotStatus(command: UpdateExecutionStatusCommand): Observable<ConfirmedPlanDayView>;
  closeExamDay(command: CloseExamDayCommand): Observable<ExamDayClosure>;
  previewExamDayReopening(
    dayId: number,
    scope: ExamDayReopeningScope[],
  ): Observable<ExamDayReopeningImpact>;
  reopenExamDay(command: ReopenExamDayCommand): Observable<ExamDayClosure>;
}

export const EXAM_DAY_PORT = new InjectionToken<ExamDayPort>('EXAM_DAY_PORT');
