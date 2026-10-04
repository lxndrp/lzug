import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  AvailabilityRequest,
  CandidateDayGenerationResult,
  CandidateExamDay,
  EditablePlanningProposal,
  PlanningMemberAvailability,
  PlanningResult,
  PlanningRound,
  PlanningRoundUpdate,
  PlanningSettings,
  PlanningSnapshot,
} from './planning.models';

/** Commands and proposal queries required by planning workflows. */
export interface PlanningPort {
  loadPlanning(roundId: number): Observable<PlanningSnapshot>;
  savePlanningSettings(
    payload: Omit<PlanningSettings, 'id' | 'exam_round_id' | 'updated_by_member_id'>,
    roundId: number,
  ): Observable<PlanningSettings>;
  updateExamRound(payload: PlanningRoundUpdate, roundId: number): Observable<PlanningRound>;
  requestAvailabilities(payload: AvailabilityRequest, roundId: number): Observable<PlanningRound>;
  createCandidateExamDay(
    payload: Omit<CandidateExamDay, 'id' | 'exam_round_id'>,
    roundId: number,
  ): Observable<CandidateExamDay>;
  generateCandidateExamDays(roundId: number): Observable<CandidateDayGenerationResult>;
  updateCandidateExamDay(
    id: number,
    payload: Partial<Pick<CandidateExamDay, 'is_active'>>,
    roundId: number,
  ): Observable<CandidateExamDay>;
  saveMemberAvailability(
    payload: Pick<
      PlanningMemberAvailability,
      'committee_member_id' | 'candidate_exam_day_id' | 'availability'
    >,
    roundId: number,
  ): Observable<PlanningMemberAvailability>;
  generateProposal(roundId: number): Observable<PlanningResult>;
  confirmPlan(roundId: number): Observable<PlanningResult>;
  getPlanningProposal(roundId: number): Observable<EditablePlanningProposal>;
  savePlanningProposal(
    roundId: number,
    proposal: EditablePlanningProposal,
  ): Observable<EditablePlanningProposal>;
}

export const PLANNING_PORT = new InjectionToken<PlanningPort>('PLANNING_PORT');
