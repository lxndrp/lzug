import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import type {
  ConfirmedPlanDayView as ApiConfirmedPlanDayView,
  ExamDayClosure as ApiExamDayClosure,
  ExamDayReopeningImpact as ApiExamDayReopeningImpact,
} from './execution.models';
import { ExamDayApiService } from './exam-day-api.service';
import { HttpExamDayAdapter } from './http-exam-day.adapter';
import type { ConfirmedPlanDayView } from '../exam-day/exam-day.models';

describe('HttpExamDayAdapter', () => {
  it('maps the API day view into a link-free feature model', async () => {
    const api = createApiMock();
    TestBed.configureTestingModule({
      providers: [HttpExamDayAdapter, { provide: ExamDayApiService, useValue: api }],
    });
    const adapter = TestBed.inject(HttpExamDayAdapter);

    const view = await firstValueFrom(adapter.getConfirmedPlanDay(7));

    expect(api.getConfirmedPlanDay).toHaveBeenCalledWith(7);
    expect(view).toEqual(featureView());
    expect(JSON.stringify(view)).not.toContain('_links');
    expect(JSON.stringify(view)).not.toContain('first_name');
  });

  it('maps transport-neutral commands to the existing API operation arguments', async () => {
    const api = createApiMock();
    TestBed.configureTestingModule({
      providers: [HttpExamDayAdapter, { provide: ExamDayApiService, useValue: api }],
    });
    const adapter = TestBed.inject(HttpExamDayAdapter);

    const attendance = {
      dayId: 7,
      entityId: 9,
      status: 'late' as const,
      arrivedAt: '2026-11-16T08:24:00Z',
      dayRevision: 4,
    };
    await firstValueFrom(adapter.saveCandidateAttendance(attendance));
    await firstValueFrom(adapter.saveMemberAttendance(attendance));
    await firstValueFrom(adapter.startExamSlot(7, 8, '2026-11-16T08:30:00Z', 4));
    await firstValueFrom(
      adapter.updateExamSlotStatus({
        dayId: 7,
        slotId: 8,
        status: 'completed',
        reason: 'validiert',
        dayRevision: 4,
        actualStartedAt: '2026-11-16T08:30:00Z',
        actualCompletedAt: '2026-11-16T09:30:00Z',
      }),
    );
    await firstValueFrom(
      adapter.closeExamDay({
        dayId: 7,
        revision: 4,
        closureType: 'exception',
        reason: 'Eine Rückmeldung fehlt',
        clarificationAttempts: 'Dreimal angefragt',
      }),
    );
    await firstValueFrom(
      adapter.previewExamDayReopening(7, [{ kind: 'exam_protocol', entityId: 41 }]),
    );
    await firstValueFrom(
      adapter.reopenExamDay({
        dayId: 7,
        revision: 4,
        occasion: 'Widerspruch',
        source: 'IHK-Schreiben',
        reason: 'Protokoll prüfen',
        scope: [{ kind: 'exam_protocol', entityId: 41 }],
      }),
    );

    expect(api.saveCandidateAttendance).toHaveBeenCalledWith(7, 9, 'late', attendance.arrivedAt, 4);
    expect(api.saveMemberAttendance).toHaveBeenCalledWith(7, 9, 'late', attendance.arrivedAt, 4);
    expect(api.startExamSlot).toHaveBeenCalledWith(7, 8, '2026-11-16T08:30:00Z', 4);
    expect(api.updateExamSlotStatus).toHaveBeenCalledWith(
      7,
      8,
      'completed',
      'validiert',
      4,
      '2026-11-16T08:30:00Z',
      '2026-11-16T09:30:00Z',
    );
    expect(api.closeExamDay).toHaveBeenCalledWith(
      7,
      4,
      'exception',
      'Eine Rückmeldung fehlt',
      'Dreimal angefragt',
    );
    expect(api.previewExamDayReopening).toHaveBeenCalledWith(7, [
      { kind: 'exam_protocol', entity_id: 41 },
    ]);
    expect(api.reopenExamDay).toHaveBeenCalledWith(
      7,
      4,
      'Widerspruch',
      'IHK-Schreiben',
      'Protokoll prüfen',
      [{ kind: 'exam_protocol', entity_id: 41 }],
    );
  });
});

function createApiMock() {
  return {
    getConfirmedPlanDay: vi.fn(() => of(apiView())),
    saveCandidateAttendance: vi.fn(() => of(apiView())),
    saveMemberAttendance: vi.fn(() => of(apiView())),
    startExamSlot: vi.fn(() => of(apiView())),
    updateExamSlotStatus: vi.fn(() => of(apiView())),
    closeExamDay: vi.fn(() => of(apiClosure())),
    previewExamDayReopening: vi.fn(() => of(apiImpact())),
    reopenExamDay: vi.fn(() => of(apiClosure())),
  };
}

function apiView(): ApiConfirmedPlanDayView {
  return {
    plan: {
      id: 1,
      name: 'Winterplan',
      committee: { id: 2, name: 'Ausschuss' },
      exam_half_year: { id: 3, season: 'winter', year: 2026, status: 'active' },
    },
    day: {
      id: 7,
      date: '2026-11-16',
      revision: 4,
      closure_status: 'reopening',
      closure: apiClosure(),
      location: { id: 6, name: 'Zentrum', room: '101', city: 'Hamburg' },
      slots: [
        {
          id: 8,
          starts_at: '2026-11-16 08:30:00',
          ends_at: '2026-11-16 09:30:00',
          sequence_number: 1,
          slot_type: 'regular',
          actual_started_at: '2026-11-16T08:30:00Z',
          execution_status: 'running',
          status_changed_at: '2026-11-16T08:30:00Z',
          actual_completed_at: null,
          status_reason: null,
          candidate_attendance: { status: 'present', arrived_at: '2026-11-16T08:00:00Z' },
          candidate: {
            id: 9,
            first_name: 'Ada',
            last_name: 'Beispiel',
            ihk_exam_number: 'X-9',
          },
        },
      ],
      assignments: [
        {
          id: 10,
          assignment_role: 'examiner',
          day_part: 'morning',
          fallback_status: null,
          attendance: { status: 'present', arrived_at: null },
          member: {
            id: 11,
            first_name: 'Erika',
            last_name: 'Erste',
            representing_side: 'employer',
          },
        },
      ],
      status_summary: { open: 0, running: 1, completed: 0, cancelled: 0, needs_follow_up: 0 },
    },
    _links: {},
  };
}

function featureView(): ConfirmedPlanDayView {
  return {
    plan: {
      id: 1,
      name: 'Winterplan',
      committee: { id: 2, name: 'Ausschuss' },
      examHalfYear: { id: 3, season: 'winter', year: 2026, status: 'active' },
    },
    day: {
      id: 7,
      date: '2026-11-16',
      revision: 4,
      closureStatus: 'reopening',
      closure: featureClosure(),
      location: { id: 6, name: 'Zentrum', room: '101', city: 'Hamburg' },
      slots: [
        {
          id: 8,
          startsAt: '2026-11-16 08:30:00',
          endsAt: '2026-11-16 09:30:00',
          sequenceNumber: 1,
          slotType: 'regular',
          actualStartedAt: '2026-11-16T08:30:00Z',
          executionStatus: 'running',
          statusChangedAt: '2026-11-16T08:30:00Z',
          actualCompletedAt: null,
          statusReason: null,
          candidateAttendance: { status: 'present', arrivedAt: '2026-11-16T08:00:00Z' },
          candidate: { id: 9, firstName: 'Ada', lastName: 'Beispiel', examNumber: 'X-9' },
        },
      ],
      assignments: [
        {
          id: 10,
          assignmentRole: 'examiner',
          dayPart: 'morning',
          fallbackStatus: null,
          attendance: { status: 'present', arrivedAt: null },
          member: {
            id: 11,
            firstName: 'Erika',
            lastName: 'Erste',
            representingSide: 'employer',
          },
        },
      ],
      statusSummary: { open: 0, running: 1, completed: 0, cancelled: 0, needs_follow_up: 0 },
    },
  };
}

function apiClosure(): ApiExamDayClosure {
  return {
    exam_day_id: 7,
    revision: 4,
    status: 'reopening',
    legacy_status: null,
    evaluation: {
      items: [{ code: 'attendance', label: 'Anwesenheit erfasst', ok: true, details: {} }],
      warnings: [],
      regular_close_ready: true,
      exception_close_ready: false,
      exception_candidate: null,
      protocol_references: [{ exam_protocol_id: 41 }],
      result_references: [{ exam_result_id: 51 }],
    },
    active_reopening: { expanded_scope: ['exam_protocol:41', 'exam_result:51'] },
    history: [],
    tasks: [],
    permissions: { close: false, reopen: true, export: true },
    _links: {
      machine_export: { href: '/api/confirmed-plan-days/7/closure/export.json' },
      human_export: { href: '/api/confirmed-plan-days/7/closure/export.txt' },
    },
  };
}

function featureClosure() {
  return {
    dayId: 7,
    revision: 4,
    status: 'reopening' as const,
    legacyStatus: null,
    evaluation: {
      items: [{ code: 'attendance', label: 'Anwesenheit erfasst', ok: true, details: {} }],
      warnings: [],
      regularCloseReady: true,
      exceptionCloseReady: false,
      exceptionCandidate: null,
      protocolReferences: [{ protocolId: 41 }],
      resultReferences: [{ resultId: 51 }],
    },
    activeReopening: { expandedScope: ['exam_protocol:41', 'exam_result:51'] },
    history: [],
    tasks: [],
    permissions: { close: false, reopen: true, export: true },
    exportLinks: {
      machine: '/api/confirmed-plan-days/7/closure/export.json',
      human: '/api/confirmed-plan-days/7/closure/export.txt',
    },
  };
}

function apiImpact(): ApiExamDayReopeningImpact {
  return {
    exam_day_id: 7,
    revision: 4,
    requested_scope: ['exam_protocol:41'],
    expanded_scope: ['exam_protocol:41', 'exam_result:51'],
    impacts: { exam_protocol: [41], exam_result: [51] },
  };
}
