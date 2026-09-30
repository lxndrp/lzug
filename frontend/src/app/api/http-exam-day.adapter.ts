import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import type {
  Attendance as ApiAttendance,
  ConfirmedPlanDayView as ApiConfirmedPlanDayView,
  ExamDayClosure as ApiExamDayClosure,
  ExamDayReopeningImpact as ApiExamDayReopeningImpact,
} from './execution.models';
import { ExamDayApiService } from './exam-day-api.service';
import type { ExamDayPort } from '../exam-day/exam-day.port';
import type {
  Attendance,
  CloseExamDayCommand,
  ConfirmedPlanDayView,
  ExamDayClosure,
  ExamDayReopeningImpact,
  ExamDayReopeningScope,
  ReopenExamDayCommand,
  SaveAttendanceCommand,
  UpdateExecutionStatusCommand,
} from '../exam-day/exam-day.models';

/** Maps transport-neutral examination-day operations to the existing HTTP/OpenAPI API. */
@Injectable({ providedIn: 'root' })
export class HttpExamDayAdapter implements ExamDayPort {
  private readonly api = inject(ExamDayApiService);

  getConfirmedPlanDay(dayId: number) {
    return this.api.getConfirmedPlanDay(dayId).pipe(map(fromApiView));
  }

  saveCandidateAttendance(command: SaveAttendanceCommand) {
    return this.api
      .saveCandidateAttendance(
        command.dayId,
        command.entityId,
        command.status,
        command.arrivedAt,
        command.dayRevision,
      )
      .pipe(map(fromApiView));
  }

  saveMemberAttendance(command: SaveAttendanceCommand) {
    return this.api
      .saveMemberAttendance(
        command.dayId,
        command.entityId,
        command.status,
        command.arrivedAt,
        command.dayRevision,
      )
      .pipe(map(fromApiView));
  }

  startExamSlot(
    dayId: number,
    slotId: number,
    actualStartedAt: string | null,
    dayRevision?: number,
  ) {
    return this.api
      .startExamSlot(dayId, slotId, actualStartedAt, dayRevision)
      .pipe(map(fromApiView));
  }

  updateExamSlotStatus(command: UpdateExecutionStatusCommand) {
    return this.api
      .updateExamSlotStatus(
        command.dayId,
        command.slotId,
        command.status,
        command.reason,
        command.dayRevision,
        command.actualStartedAt,
        command.actualCompletedAt,
      )
      .pipe(map(fromApiView));
  }

  closeExamDay(command: CloseExamDayCommand) {
    return this.api
      .closeExamDay(
        command.dayId,
        command.revision,
        command.closureType,
        command.reason,
        command.clarificationAttempts,
      )
      .pipe(map(fromApiClosure));
  }

  previewExamDayReopening(dayId: number, scope: ExamDayReopeningScope[]) {
    return this.api
      .previewExamDayReopening(
        dayId,
        scope.map(({ kind, entityId }) => ({ kind, entity_id: entityId })),
      )
      .pipe(map(fromApiImpact));
  }

  reopenExamDay(command: ReopenExamDayCommand) {
    return this.api
      .reopenExamDay(
        command.dayId,
        command.revision,
        command.occasion,
        command.source,
        command.reason,
        command.scope.map(({ kind, entityId }) => ({ kind, entity_id: entityId })),
      )
      .pipe(map(fromApiClosure));
  }
}

function fromApiView(view: ApiConfirmedPlanDayView): ConfirmedPlanDayView {
  return {
    plan: {
      id: view.plan.id,
      name: view.plan.name,
      committee: { id: view.plan.committee.id, name: view.plan.committee.name },
      examHalfYear: {
        id: view.plan.exam_half_year.id,
        season: view.plan.exam_half_year.season,
        year: view.plan.exam_half_year.year,
        status: view.plan.exam_half_year.status,
      },
    },
    day: {
      id: view.day.id,
      date: view.day.date,
      revision: view.day.revision,
      closureStatus: view.day.closure_status,
      closure: fromApiClosure(view.day.closure),
      location: view.day.location
        ? {
            id: view.day.location.id,
            name: view.day.location.name,
            room: view.day.location.room,
            city: view.day.location.city,
          }
        : null,
      slots: view.day.slots.map((slot) => ({
        id: slot.id,
        startsAt: slot.starts_at,
        endsAt: slot.ends_at,
        sequenceNumber: slot.sequence_number,
        slotType: slot.slot_type,
        actualStartedAt: slot.actual_started_at,
        executionStatus: slot.execution_status,
        statusChangedAt: slot.status_changed_at,
        actualCompletedAt: slot.actual_completed_at,
        statusReason: slot.status_reason,
        candidateAttendance: fromApiAttendance(slot.candidate_attendance),
        candidate: {
          id: slot.candidate.id,
          firstName: slot.candidate.first_name,
          lastName: slot.candidate.last_name,
          examNumber: slot.candidate.ihk_exam_number,
        },
      })),
      assignments: view.day.assignments.map((assignment) => ({
        id: assignment.id,
        assignmentRole: assignment.assignment_role,
        dayPart: assignment.day_part,
        fallbackStatus: assignment.fallback_status,
        attendance: fromApiAttendance(assignment.attendance),
        member: {
          id: assignment.member.id,
          firstName: assignment.member.first_name,
          lastName: assignment.member.last_name,
          representingSide: assignment.member.representing_side,
        },
      })),
      statusSummary: { ...view.day.status_summary },
    },
  };
}

function fromApiAttendance(attendance: ApiAttendance): Attendance {
  return { status: attendance.status, arrivedAt: attendance.arrived_at };
}

function fromApiClosure(closure: ApiExamDayClosure): ExamDayClosure {
  return {
    dayId: closure.exam_day_id,
    revision: closure.revision,
    status: closure.status,
    legacyStatus: closure.legacy_status,
    evaluation: {
      items: closure.evaluation.items.map((item) => ({
        code: item.code,
        label: item.label,
        ok: item.ok,
        details: item.details,
      })),
      warnings: closure.evaluation.warnings,
      regularCloseReady: closure.evaluation.regular_close_ready,
      exceptionCloseReady: closure.evaluation.exception_close_ready,
      exceptionCandidate: closure.evaluation.exception_candidate,
      protocolReferences: closure.evaluation.protocol_references.map((reference) => ({
        ...(typeof reference['exam_protocol_id'] === 'number'
          ? { protocolId: reference['exam_protocol_id'] }
          : {}),
      })),
      resultReferences: closure.evaluation.result_references.map((reference) => ({
        ...(typeof reference['exam_result_id'] === 'number'
          ? { resultId: reference['exam_result_id'] }
          : {}),
      })),
    },
    activeReopening: closure.active_reopening
      ? {
          ...(Array.isArray(closure.active_reopening['expanded_scope'])
            ? { expandedScope: closure.active_reopening['expanded_scope'] as string[] }
            : {}),
        }
      : null,
    history: closure.history,
    tasks: closure.tasks,
    permissions: { ...closure.permissions },
    exportLinks: {
      machine: closure._links['machine_export'].href,
      human: closure._links['human_export'].href,
    },
  };
}

function fromApiImpact(impact: ApiExamDayReopeningImpact): ExamDayReopeningImpact {
  return {
    dayId: impact.exam_day_id,
    revision: impact.revision,
    requestedScope: [...impact.requested_scope],
    expandedScope: [...impact.expanded_scope],
    impacts: { ...impact.impacts },
  };
}
