import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import type {
  ConfirmedPlan as ApiConfirmedPlan,
  ConfirmedPlanRevision as ApiConfirmedPlanRevision,
  EditablePlanningProposal as ApiEditableConfirmedPlan,
} from './api.models';
import { ConfirmedPlanApiService } from './confirmed-plan-api.service';
import { HttpConfirmedPlansAdapter } from './http-confirmed-plans.adapter';
import type {
  ConfirmedPlan,
  ConfirmedPlanRevision,
  EditableConfirmedPlan,
} from '../confirmed-plans/confirmed-plans.models';

describe('HttpConfirmedPlansAdapter', () => {
  it('maps confirmed-plan reads into feature models and omits transport-only fields', async () => {
    const api = {
      getConfirmedPlans: vi.fn(() => of([apiPlan()])),
      getEditableConfirmedPlan: vi.fn(() => of(apiEditablePlan())),
      saveEditableConfirmedPlan: vi.fn((_roundId: number, proposal: ApiEditableConfirmedPlan) =>
        of({ ...proposal, _links: { self: { href: '/saved' } } }),
      ),
      getConfirmedPlanRevisions: vi.fn(() => of([apiRevision()])),
    };
    TestBed.configureTestingModule({
      providers: [HttpConfirmedPlansAdapter, { provide: ConfirmedPlanApiService, useValue: api }],
    });

    const adapter = TestBed.inject(HttpConfirmedPlansAdapter);
    const plans = await firstValueFrom(adapter.list());
    const editable = await firstValueFrom(adapter.getEditable(1));
    const saved = await firstValueFrom(adapter.saveEditable(1, featureEditablePlan(), ' reason '));
    const revisions = await firstValueFrom(adapter.listRevisions(1));

    expect(plans).toEqual([featurePlan()]);
    expect(editable).toEqual(featureEditablePlan());
    expect(saved).toEqual(featureEditablePlan());
    expect(revisions).toEqual([featureRevision()]);
    expect(api.getEditableConfirmedPlan).toHaveBeenCalledWith(1);
    expect(api.saveEditableConfirmedPlan).toHaveBeenCalledWith(1, apiEditablePayload(), ' reason ');
    expect(api.getConfirmedPlanRevisions).toHaveBeenCalledWith(1);
  });
});

function apiPlan(): ApiConfirmedPlan {
  return {
    id: 1,
    name: 'Winterplan',
    committee: { id: 2, name: 'Ausschuss' },
    exam_half_year: { id: 3, season: 'winter', year: 2026, status: 'active' },
    days: [
      {
        id: 4,
        date: '2026-11-16',
        revision: 5,
        closure_status: 'open',
        location: { id: 6, name: 'Zentrum', room: '101', city: 'Teststadt' },
        slots: [
          {
            id: 7,
            starts_at: '08:30',
            ends_at: '09:30',
            sequence_number: 1,
            slot_type: 'regular',
            actual_started_at: null,
            execution_status: 'open',
            status_changed_at: '2026-11-16T08:00:00Z',
            actual_completed_at: null,
            status_reason: null,
            candidate_attendance: { status: 'open', arrived_at: null },
            candidate: {
              id: 8,
              first_name: 'Ada',
              last_name: 'Beispiel',
              ihk_exam_number: 'X-8',
            },
          },
        ],
        assignments: [
          {
            id: 9,
            assignment_role: 'examiner',
            day_part: 'morning',
            fallback_status: null,
            attendance: { status: 'present', arrived_at: '2026-11-16T08:00:00Z' },
            member: {
              id: 10,
              first_name: 'Erika',
              last_name: 'Erste',
              representing_side: 'employer',
            },
          },
        ],
        status_summary: { open: 1, running: 0, completed: 0, cancelled: 0, needs_follow_up: 0 },
      },
    ],
  };
}

function apiEditablePlan(): ApiEditableConfirmedPlan {
  return {
    round_id: 1,
    revision: 2,
    exam_days: [
      {
        candidate_exam_day_id: 3,
        id: 4,
        date: '2026-11-16',
        room_id: 6,
        location_id: 6,
        status: 'confirmed',
        slots: [
          {
            round_candidate_id: 8,
            id: 7,
            slot_type: 'mep',
            starts_at: '08:30',
            ends_at: '09:30',
            sequence_number: 1,
            status: 'confirmed',
          },
        ],
        assignments: [
          {
            committee_member_id: 10,
            id: 9,
            assignment_role: 'examiner',
            day_part: 'morning',
            fallback_status: null,
          },
        ],
      },
    ],
    _links: { self: { href: '/api/editable' } },
  };
}

function apiEditablePayload(): ApiEditableConfirmedPlan {
  const { _links, ...payload } = apiEditablePlan();
  void _links;
  return payload;
}

function featurePlan(): ConfirmedPlan {
  return {
    id: 1,
    name: 'Winterplan',
    committee: { id: 2, name: 'Ausschuss' },
    examHalfYear: { id: 3, season: 'winter', year: 2026, status: 'active' },
    days: [
      {
        id: 4,
        date: '2026-11-16',
        revision: 5,
        closureStatus: 'open',
        location: { id: 6, name: 'Zentrum', room: '101', city: 'Teststadt' },
        slots: [
          {
            id: 7,
            startsAt: '08:30',
            endsAt: '09:30',
            sequenceNumber: 1,
            slotType: 'regular',
            actualStartedAt: null,
            executionStatus: 'open',
            statusChangedAt: '2026-11-16T08:00:00Z',
            actualCompletedAt: null,
            statusReason: null,
            candidateAttendance: { status: 'open', arrivedAt: null },
            candidate: { id: 8, firstName: 'Ada', lastName: 'Beispiel', examNumber: 'X-8' },
          },
        ],
        assignments: [
          {
            id: 9,
            assignmentRole: 'examiner',
            dayPart: 'morning',
            fallbackStatus: null,
            attendance: { status: 'present', arrivedAt: '2026-11-16T08:00:00Z' },
            member: { id: 10, firstName: 'Erika', lastName: 'Erste', representingSide: 'employer' },
          },
        ],
        statusSummary: { open: 1, running: 0, completed: 0, cancelled: 0, needs_follow_up: 0 },
      },
    ],
  };
}

function featureEditablePlan(): EditableConfirmedPlan {
  return {
    roundId: 1,
    revision: 2,
    days: [
      {
        candidateDayId: 3,
        id: 4,
        date: '2026-11-16',
        roomId: 6,
        locationId: 6,
        status: 'confirmed',
        slots: [
          {
            roundCandidateId: 8,
            id: 7,
            slotType: 'mep',
            startsAt: '08:30',
            endsAt: '09:30',
            sequenceNumber: 1,
            status: 'confirmed',
          },
        ],
        assignments: [
          {
            committeeMemberId: 10,
            id: 9,
            assignmentRole: 'examiner',
            dayPart: 'morning',
            fallbackStatus: null,
          },
        ],
      },
    ],
  };
}

function apiRevision(): ApiConfirmedPlanRevision {
  const proposal = apiEditablePlan();
  return {
    id: 11,
    previous_revision: 1,
    resulting_revision: 2,
    reason: 'Korrektur',
    actor_member_id: 10,
    created_at: '2026-11-15T12:00:00Z',
    before: { ...proposal, revision: 1 },
    after: proposal,
  };
}

function featureRevision(): ConfirmedPlanRevision {
  return {
    id: 11,
    previousRevision: 1,
    resultingRevision: 2,
    reason: 'Korrektur',
    actorMemberId: 10,
    createdAt: '2026-11-15T12:00:00Z',
    before: { ...featureEditablePlan(), revision: 1 },
    after: featureEditablePlan(),
  };
}
