import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import type {
  PlanningProposalResponse,
  PlanningProposalResultResponse,
  PlanningProposalWriteRequest,
} from '../api/generated/types.gen';
import type { PlanningBoard as ApiPlanningBoard } from '../api/planning.models';
import { PlanningApiService } from '../api/planning-api.service';
import type {
  EditablePlanningProposal,
  PlanningBoard,
  PlanningLocation,
  PlanningResult,
  PlanningSnapshot,
} from './planning.models';
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
        return {
          round: roundProjection,
          summary: summaryProjection,
          board: toPlanningBoard(board),
        } satisfies PlanningSnapshot;
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
    return this.api.confirmPlan(roundId).pipe(map(toConfirmedPlanningResult));
  }

  getPlanningProposal(roundId: number) {
    return this.api.getPlanningProposal(roundId).pipe(map(toEditableProposal));
  }

  savePlanningProposal(
    roundId: number,
    proposal: Parameters<PlanningPort['savePlanningProposal']>[1],
  ) {
    const request = {
      round_id: proposal.round_id,
      revision: proposal.revision,
      exam_days: proposal.exam_days,
    } satisfies PlanningProposalWriteRequest;
    return this.api.savePlanningProposal(roundId, request).pipe(map(toEditableProposal));
  }
}

function toPlanningResult(value: PlanningProposalResultResponse): PlanningResult {
  const validationResult = toValidationResult(value['validation'], false);
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

function toConfirmedPlanningResult(value: unknown): PlanningResult {
  const response = record(value, 'confirm plan response');
  const status = requiredString(response['status'], 'confirm plan status');
  if (status !== 'plan_confirmed') {
    throw new Error(`Unsupported confirm plan status: ${status}`);
  }
  const counts = numberRecord(response['counts'], 'confirm plan counts');
  requiredNumber(counts['confirmed_exam_days'], 'confirm plan counts.confirmed_exam_days');
  requiredNumber(counts['confirmed_slots'], 'confirm plan counts.confirmed_slots');
  const validation = toValidationResult(response['validation'], true);
  const calendarWarning = optionalString(
    response['calendar_warning'],
    'confirm plan calendar_warning',
  );
  const notificationWarning = optionalString(
    response['notification_warning'],
    'confirm plan notification_warning',
  );
  return {
    status,
    counts,
    ...(validation ? { validation } : {}),
    ...(calendarWarning ? { calendar_warning: calendarWarning } : {}),
    ...(notificationWarning ? { notification_warning: notificationWarning } : {}),
  };
}

function toValidationResult(value: unknown, allowMissing: boolean): PlanningResult['validation'] {
  if (value === undefined && allowMissing) return undefined;
  const validation = record(value, 'validation');
  if (typeof validation['passed'] !== 'boolean') {
    throw new Error('Expected validation.passed to be a boolean');
  }
  if (!Array.isArray(validation['messages'])) {
    throw new Error('Expected validation.messages to be an array');
  }
  return {
    passed: validation['passed'],
    messages: validation['messages'].map((message) =>
      requiredString(message, 'validation message'),
    ),
  };
}

function numberRecord(value: unknown, field: string): Record<string, number> {
  const source = record(value, field);
  return Object.fromEntries(
    Object.entries(source).map(([key, item]) => [key, requiredNumber(item, `${field}.${key}`)]),
  );
}

function toPlanningBoard(board: ApiPlanningBoard): PlanningBoard {
  return {
    ...board,
    days: board.days.map((view) => ({
      ...view,
      ...(view.location ? { location: toPlanningLocation(view.location) } : {}),
    })),
    candidates: board.candidates.map(({ candidate, roundCandidate }) => ({
      candidate: projectCandidate(candidate),
      ...(roundCandidate
        ? {
            roundCandidate: {
              id: roundCandidate.id,
              candidate_id: roundCandidate.candidate_id,
              exam_round_id: roundCandidate.exam_round_id,
              attempt_number: roundCandidate.attempt_number,
              requires_mep: roundCandidate.requires_mep,
              is_active: roundCandidate.is_active,
              ...(roundCandidate.terminal_status !== undefined
                ? { terminal_status: roundCandidate.terminal_status }
                : {}),
              ...(roundCandidate.terminal_reason !== undefined
                ? { terminal_reason: roundCandidate.terminal_reason }
                : {}),
              ...(roundCandidate.effective_new_round_id !== undefined
                ? { effective_new_round_id: roundCandidate.effective_new_round_id }
                : {}),
              ...(roundCandidate.postponed_until !== undefined
                ? { postponed_until: roundCandidate.postponed_until }
                : {}),
              ...(roundCandidate.ihk_decision_reference !== undefined
                ? { ihk_decision_reference: roundCandidate.ihk_decision_reference }
                : {}),
              ...(roundCandidate.terminal_at !== undefined
                ? { terminal_at: roundCandidate.terminal_at }
                : {}),
              ...(roundCandidate.created_at !== undefined
                ? { created_at: roundCandidate.created_at }
                : {}),
              ...(roundCandidate.updated_at !== undefined
                ? { updated_at: roundCandidate.updated_at }
                : {}),
            },
          }
        : {}),
    })),
    locations: board.locations.map(toPlanningLocation),
  };
}

function projectCandidate(candidate: ApiPlanningBoard['candidates'][number]['candidate']) {
  return {
    id: candidate.id,
    first_name: candidate.first_name,
    last_name: candidate.last_name,
    ihk_exam_number: candidate.ihk_exam_number,
    specialization: candidate.specialization,
    training_company: candidate.training_company,
    ...(candidate.created_at !== undefined ? { created_at: candidate.created_at } : {}),
    ...(candidate.updated_at !== undefined ? { updated_at: candidate.updated_at } : {}),
  };
}

function toPlanningLocation(location: ApiPlanningBoard['locations'][number]): PlanningLocation {
  return {
    id: location.id,
    ...(location.committee_id !== undefined ? { committee_id: location.committee_id } : {}),
    name: location.name,
    ...(location.street !== undefined ? { street: location.street } : {}),
    ...(location.postal_code !== undefined ? { postal_code: location.postal_code } : {}),
    room: location.room,
    city: location.city,
    ...(location.is_active !== undefined ? { is_active: location.is_active } : {}),
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
      ...(day.room_id !== undefined ? { room_id: day.room_id } : {}),
      location_id: day.location_id ?? null,
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

function optionalString(value: unknown, field: string): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== 'string') throw new Error(`Expected ${field} to be a string`);
  return value;
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
