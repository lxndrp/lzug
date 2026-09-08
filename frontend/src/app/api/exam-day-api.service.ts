import type {
  AttendanceStatus,
  ConfirmedPlanDayView,
  ExamDayClosure,
  ExamDayReopeningImpact,
  ExamDayReopeningScope,
  ExecutionStatus,
} from './execution.models';
import { Injectable, inject } from '@angular/core';

import { ApiClient } from './api-client.service';

/** Examination-day execution, attendance, closure, and reopening operations. */

@Injectable({ providedIn: 'root' })
export class ExamDayApiService {
  private readonly client = inject(ApiClient);
  getConfirmedPlanDay(dayId: number) {
    return this.client.get<ConfirmedPlanDayView>(`/api/confirmed-plan-days/${dayId}`);
  }

  closeExamDay(
    dayId: number,
    revision: number,
    closureType: 'regular' | 'exception',
    reason: string,
    clarificationAttempts: string,
  ) {
    return this.client.post<ExamDayClosure>(`/api/confirmed-plan-days/${dayId}/closure`, {
      revision,
      closure_type: closureType,
      confirmed: true,
      ...(closureType === 'exception'
        ? { reason: reason.trim(), clarification_attempts: clarificationAttempts.trim() }
        : {}),
    });
  }

  previewExamDayReopening(dayId: number, scope: ExamDayReopeningScope[]) {
    return this.client.post<ExamDayReopeningImpact>(
      `/api/confirmed-plan-days/${dayId}/reopening-impact`,
      { scope },
    );
  }

  reopenExamDay(
    dayId: number,
    revision: number,
    occasion: string,
    source: string,
    reason: string,
    scope: ExamDayReopeningScope[],
  ) {
    return this.client.post<ExamDayClosure>(`/api/confirmed-plan-days/${dayId}/reopenings`, {
      revision,
      occasion: occasion.trim(),
      source: source.trim(),
      reason: reason.trim(),
      scope,
    });
  }

  saveCandidateAttendance(
    dayId: number,
    slotId: number,
    status: AttendanceStatus,
    arrivedAt: string | null,
    dayRevision?: number,
  ) {
    return this.client.patch<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/slots/${slotId}/attendance`,
      { status, arrived_at: arrivedAt, ...(dayRevision ? { day_revision: dayRevision } : {}) },
    );
  }

  saveMemberAttendance(
    dayId: number,
    assignmentId: number,
    status: AttendanceStatus,
    arrivedAt: string | null,
    dayRevision?: number,
  ) {
    return this.client.patch<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/assignments/${assignmentId}/attendance`,
      { status, arrived_at: arrivedAt, ...(dayRevision ? { day_revision: dayRevision } : {}) },
    );
  }

  startExamSlot(
    dayId: number,
    slotId: number,
    actualStartedAt: string | null = null,
    dayRevision?: number,
  ) {
    return this.client.post<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/slots/${slotId}/start`,
      {
        ...(actualStartedAt ? { actual_started_at: actualStartedAt } : {}),
        ...(dayRevision ? { day_revision: dayRevision } : {}),
      },
    );
  }

  updateExamSlotStatus(
    dayId: number,
    slotId: number,
    status: ExecutionStatus,
    reason?: string,
    dayRevision?: number,
    actualStartedAt?: string | null,
    actualCompletedAt?: string | null,
  ) {
    return this.client.patch<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/slots/${slotId}/status`,
      {
        status,
        ...(reason ? { reason } : {}),
        ...(dayRevision ? { day_revision: dayRevision } : {}),
        ...(actualStartedAt !== undefined ? { actual_started_at: actualStartedAt } : {}),
        ...(actualCompletedAt !== undefined ? { actual_completed_at: actualCompletedAt } : {}),
      },
    );
  }
}
