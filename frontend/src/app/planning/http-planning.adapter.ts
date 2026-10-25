import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import type {
  PlanningProposalResponse,
  PlanningProposalResultResponse,
} from '../api/generated/types.gen';
import { PlanningApiService } from '../api/planning-api.service';
import type { EditablePlanningProposal, PlanningResult } from './planning.models';
import type { PlanningPort } from './planning.port';

/** HTTP adapter for the planning workflow application boundary. */
@Injectable({ providedIn: 'root' })
export class HttpPlanningAdapter implements PlanningPort {
  private readonly api = inject(PlanningApiService);

  loadPlanning(roundId: number) {
    return this.api.loadPlanningFeature(roundId).pipe(
      map(({ round, summary, board }) => {
        const { _links: roundLinks, ...roundProjection } = round;
        const { _links: summaryLinks, ...summaryProjection } = summary;
        void roundLinks;
        void summaryLinks;
        return { round: roundProjection, summary: summaryProjection, board };
      }),
    );
  }

  savePlanningSettings(...args: Parameters<PlanningPort['savePlanningSettings']>) {
    return this.api.savePlanningSettings(...args).pipe(map(withoutRootLinks));
  }

  updateExamRound(...args: Parameters<PlanningPort['updateExamRound']>) {
    return this.api.updateExamRound(...args).pipe(
      map(({ _links, ...round }) => {
        void _links;
        return round;
      }),
    );
  }

  sendAvailabilityRequests(roundId: number) {
    return this.api.sendAvailabilityRequests(roundId).pipe(
      map(({ _links, ...round }) => {
        void _links;
        return round;
      }),
    );
  }

  createCandidateExamDay(...args: Parameters<PlanningPort['createCandidateExamDay']>) {
    return this.api.createCandidateExamDay(...args).pipe(map(withoutRootLinks));
  }

  generateCandidateExamDays(...args: Parameters<PlanningPort['generateCandidateExamDays']>) {
    return this.api.generateCandidateExamDays(...args).pipe(
      map((result) => ({
        ...withoutRootLinks(result),
        created_days: result.created_days.map(withoutRootLinks),
      })),
    );
  }

  updateCandidateExamDay(
    id: number,
    payload: Parameters<PlanningPort['updateCandidateExamDay']>[1],
  ) {
    return this.api.updateCandidateExamDay(id, payload).pipe(map(withoutRootLinks));
  }

  saveMemberAvailability(...args: Parameters<PlanningPort['saveMemberAvailability']>) {
    return this.api.saveMemberAvailability(...args).pipe(map(withoutRootLinks));
  }

  generateProposal(roundId: number) {
    return this.api.generateProposal(roundId).pipe(map((value) => toPlanningResult(value)));
  }

  confirmPlan(roundId: number) {
    return this.api.confirmPlan(roundId).pipe(map((value) => toPlanningResult(value, true)));
  }

  getPlanningProposal(roundId: number) {
    return this.api.getPlanningProposal(roundId).pipe(map(toEditableProposal));
  }

  savePlanningProposal(
    roundId: number,
    proposal: Parameters<PlanningPort['savePlanningProposal']>[1],
  ) {
    return this.api.savePlanningProposal(roundId, proposal).pipe(map(toEditableProposal));
  }
}

function toPlanningResult(
  value: PlanningProposalResultResponse,
  allowMissingValidation = false,
): PlanningResult {
  const validationValue = value['validation'];
  const validation =
    allowMissingValidation && validationValue === undefined
      ? undefined
      : record(validationValue, 'validation');
  const validationResult =
    validation && typeof validation['passed'] === 'boolean' && Array.isArray(validation['messages'])
      ? {
          passed: validation['passed'],
          messages: validation['messages'].map((message) =>
            requiredString(message, 'validation message'),
          ),
        }
      : undefined;
  const conflicts = Array.isArray(value['conflicts'])
    ? value['conflicts'].map((item) => {
        const conflict = record(item, 'conflict');
        return {
          date: requiredString(conflict['date'], 'conflict.date'),
          day_part: requiredString(conflict['day_part'], 'conflict.day_part'),
          reservation: requiredString(conflict['reservation'], 'conflict.reservation'),
          message: requiredString(conflict['message'], 'conflict.message'),
        };
      })
    : undefined;
  return {
    status: value.status,
    counts: value.counts,
    ...(validationResult ? { validation: validationResult } : {}),
    ...(conflicts ? { conflicts } : {}),
    ...(typeof value['notification_warning'] === 'string'
      ? { notification_warning: value['notification_warning'] }
      : {}),
    ...(typeof value['calendar_warning'] === 'string'
      ? { calendar_warning: value['calendar_warning'] }
      : {}),
  };
}

function toEditableProposal(value: PlanningProposalResponse): EditablePlanningProposal {
  return {
    round_id: value.round_id,
    revision: value.revision,
    exam_days: value.exam_days.map((day) => ({
      candidate_exam_day_id: day.candidate_exam_day_id,
      id: day.id ?? null,
      date: requiredString(day.date, 'proposal day date'),
      room_id: day.room_id ?? undefined,
      location_id: requiredNumber(day.location_id, 'proposal day location_id'),
      status: requiredString(day.status, 'proposal day status'),
      slots: day.slots.map((slot) => ({
        round_candidate_id: slot.round_candidate_id,
        id: slot.id ?? null,
        slot_type: oneOf(slot.slot_type, ['regular', 'mep'], 'proposal slot_type'),
        starts_at: requiredString(slot.starts_at, 'proposal slot starts_at'),
        ends_at: requiredString(slot.ends_at, 'proposal slot ends_at'),
        sequence_number: requiredNumber(slot.sequence_number, 'proposal slot sequence_number'),
        status: requiredString(slot.status, 'proposal slot status'),
      })),
      assignments: day.assignments.map((assignment) => ({
        committee_member_id: assignment.committee_member_id,
        id: assignment.id ?? null,
        assignment_role: oneOf(
          assignment.assignment_role,
          ['examiner', 'fallback'],
          'proposal assignment_role',
        ),
        day_part: oneOf(
          assignment.day_part,
          ['morning', 'afternoon', 'full_day'],
          'proposal assignment day_part',
        ),
        fallback_status: assignment.fallback_status ?? null,
      })),
    })),
  };
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

function record(value: unknown, field: string): Record<string, unknown> {
  if (isRecord(value)) return value;
  throw new Error(`Expected ${field} to be an object`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value === 'string') return value;
  throw new Error(`Expected ${field} to be a string`);
}

function requiredNumber(value: unknown, field: string): number {
  if (typeof value === 'number') return value;
  throw new Error(`Expected ${field} to be a number`);
}

function withoutRootLinks<T extends object>(resource: T): T {
  const projection = { ...resource };
  Reflect.deleteProperty(projection, '_links');
  return projection;
}
