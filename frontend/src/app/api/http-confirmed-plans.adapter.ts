import { Injectable, inject } from '@angular/core';
import { forkJoin, map } from 'rxjs';

import { ConfirmedPlanApiService } from './confirmed-plan-api.service';
import type {
  PlanningProposalResponse as ApiEditableConfirmedPlan,
  PlanningProposalWriteRequest,
} from './generated/types.gen';
import { MasterDataApiService } from './master-data-api.service';
import { PlanningApiService } from './planning-api.service';
import type { ConfirmedPlan as ApiConfirmedPlan } from './execution.models';
import type { ConfirmedPlanRevision as ApiConfirmedPlanRevision } from './planning.models';
import type { ConfirmedPlansPort } from '../confirmed-plans/confirmed-plans.port';
import type {
  ConfirmedPlan,
  ConfirmedPlanRevision,
  EditableConfirmedPlan,
} from '../confirmed-plans/confirmed-plans.models';

/** HTTP adapter for confirmed-plan application operations. */
@Injectable({ providedIn: 'root' })
export class HttpConfirmedPlansAdapter implements ConfirmedPlansPort {
  private readonly api = inject(ConfirmedPlanApiService);
  private readonly masterData = inject(MasterDataApiService);
  private readonly planning = inject(PlanningApiService);

  list() {
    return this.api.getConfirmedPlans().pipe(map((plans) => plans.map(fromApiConfirmedPlan)));
  }

  loadEditorReferences(roundId: number) {
    return forkJoin({
      candidates: this.masterData.getCandidateViews(roundId),
      members: this.masterData.getCommitteeMembers(),
      locations: this.planning.getLocations(),
    }).pipe(
      map(({ candidates, members, locations }) => ({
        candidates: candidates.flatMap(({ candidate, roundCandidate }) =>
          roundCandidate
            ? [
                {
                  roundCandidateId: roundCandidate.id,
                  firstName: candidate.first_name,
                  lastName: candidate.last_name,
                  examNumber: candidate.ihk_exam_number,
                },
              ]
            : [],
        ),
        members: members.map((member) => ({
          id: member.id,
          firstName: member.first_name,
          lastName: member.last_name,
        })),
        locations: locations.map((location) => ({
          id: location.id,
          name: location.name,
          room: location.room,
          city: location.city,
        })),
      })),
    );
  }

  getEditable(roundId: number) {
    return this.api.getEditableConfirmedPlan(roundId).pipe(map(fromApiEditableConfirmedPlan));
  }

  saveEditable(roundId: number, proposal: EditableConfirmedPlan, reason: string) {
    return this.api
      .saveEditableConfirmedPlan(roundId, toApiEditableConfirmedPlan(proposal), reason)
      .pipe(map(fromApiEditableConfirmedPlan));
  }

  listRevisions(roundId: number) {
    return this.api
      .getConfirmedPlanRevisions(roundId)
      .pipe(map((revisions) => revisions.map(fromApiConfirmedPlanRevision)));
  }
}

function fromApiConfirmedPlan(plan: ApiConfirmedPlan): ConfirmedPlan {
  return {
    id: plan.id,
    name: plan.name,
    committee: { id: plan.committee.id, name: plan.committee.name },
    examHalfYear: {
      id: plan.exam_half_year.id,
      season: plan.exam_half_year.season,
      year: plan.exam_half_year.year,
      status: plan.exam_half_year.status,
    },
    days: plan.days.map((day) => ({
      id: day.id,
      date: day.date,
      revision: day.revision,
      closureStatus: day.closure_status,
      location: day.location
        ? {
            id: day.location.id,
            name: day.location.name,
            room: day.location.room,
            city: day.location.city,
          }
        : null,
      slots: day.slots.map((slot) => ({
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
        candidateAttendance: {
          status: slot.candidate_attendance.status,
          arrivedAt: slot.candidate_attendance.arrived_at,
        },
        candidate: {
          id: slot.candidate.id,
          firstName: slot.candidate.first_name,
          lastName: slot.candidate.last_name,
          examNumber: slot.candidate.ihk_exam_number,
        },
      })),
      assignments: day.assignments.map((assignment) => ({
        id: assignment.id,
        assignmentRole: assignment.assignment_role,
        dayPart: assignment.day_part,
        fallbackStatus: assignment.fallback_status,
        attendance: {
          status: assignment.attendance.status,
          arrivedAt: assignment.attendance.arrived_at,
        },
        member: {
          id: assignment.member.id,
          firstName: assignment.member.first_name,
          lastName: assignment.member.last_name,
          representingSide: assignment.member.representing_side,
        },
      })),
      statusSummary: { ...day.status_summary },
    })),
  };
}

function fromApiEditableConfirmedPlan(proposal: ApiEditableConfirmedPlan): EditableConfirmedPlan {
  return {
    roundId: proposal.round_id,
    revision: proposal.revision,
    days: proposal.exam_days.map((day) => ({
      candidateDayId: day.candidate_exam_day_id,
      id: day.id ?? null,
      date: requiredString(day.date, 'confirmed plan day date'),
      ...(day.room_id === undefined || day.room_id === null ? {} : { roomId: day.room_id }),
      locationId: requiredNumber(day.location_id, 'confirmed plan day location_id'),
      status: requiredString(day.status, 'confirmed plan day status'),
      slots: day.slots.map((slot) => ({
        roundCandidateId: slot.round_candidate_id,
        id: slot.id ?? null,
        slotType: oneOf(slot.slot_type, ['regular', 'mep'], 'confirmed plan slot_type'),
        startsAt: requiredString(slot.starts_at, 'confirmed plan slot starts_at'),
        endsAt: requiredString(slot.ends_at, 'confirmed plan slot ends_at'),
        sequenceNumber: requiredNumber(slot.sequence_number, 'confirmed plan slot sequence_number'),
        status: requiredString(slot.status, 'confirmed plan slot status'),
      })),
      assignments: day.assignments.map((assignment) => ({
        committeeMemberId: assignment.committee_member_id,
        id: assignment.id ?? null,
        assignmentRole: oneOf(
          assignment.assignment_role,
          ['examiner', 'fallback'],
          'confirmed plan assignment_role',
        ),
        dayPart: oneOf(
          assignment.day_part,
          ['morning', 'afternoon', 'full_day'],
          'confirmed plan assignment day_part',
        ),
        fallbackStatus: assignment.fallback_status ?? null,
      })),
    })),
  };
}

function toApiEditableConfirmedPlan(proposal: EditableConfirmedPlan): PlanningProposalWriteRequest {
  return {
    round_id: proposal.roundId,
    revision: proposal.revision,
    exam_days: proposal.days.map((day) => ({
      candidate_exam_day_id: day.candidateDayId,
      id: day.id,
      date: day.date,
      ...(day.roomId === undefined ? {} : { room_id: day.roomId }),
      location_id: day.locationId,
      status: day.status,
      slots: day.slots.map((slot) => ({
        round_candidate_id: slot.roundCandidateId,
        id: slot.id,
        slot_type: slot.slotType,
        starts_at: slot.startsAt,
        ends_at: slot.endsAt,
        sequence_number: slot.sequenceNumber,
        status: slot.status,
      })),
      assignments: day.assignments.map((assignment) => ({
        committee_member_id: assignment.committeeMemberId,
        id: assignment.id,
        assignment_role: assignment.assignmentRole,
        day_part: assignment.dayPart,
        fallback_status: assignment.fallbackStatus,
      })),
    })),
  } satisfies PlanningProposalWriteRequest;
}

function oneOf<const T extends readonly string[]>(
  value: string,
  options: T,
  field: string,
): T[number] {
  const match = options.find((option) => option === value);
  if (match !== undefined) return match;
  throw new Error(`Unsupported ${field}: ${value}`);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value === 'string') return value;
  throw new Error(`Expected ${field} to be a string`);
}

function requiredNumber(value: unknown, field: string): number {
  if (typeof value === 'number') return value;
  throw new Error(`Expected ${field} to be a number`);
}

function fromApiConfirmedPlanRevision(revision: ApiConfirmedPlanRevision): ConfirmedPlanRevision {
  return {
    id: revision.id,
    previousRevision: revision.previous_revision,
    resultingRevision: revision.resulting_revision,
    reason: revision.reason,
    actorMemberId: revision.actor_member_id,
    createdAt: revision.created_at,
    before: fromApiEditableConfirmedPlan(revision.before),
    after: fromApiEditableConfirmedPlan(revision.after),
  };
}
