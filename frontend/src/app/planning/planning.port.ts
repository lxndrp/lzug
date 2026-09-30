import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  AvailabilityRequest,
  CandidateDayGenerationResult,
  CandidateExamDay,
  EditablePlanningProposal,
  ExamRound,
  ExamRoundUpdate,
  MemberAvailability,
  PlanningResult,
  PlanningSettings,
} from '../api/api.models';
import type { WithoutHttpLinks } from '../application/without-http-links';

/** Commands and proposal queries required by planning workflows. */
export interface PlanningPort {
  savePlanningSettings(
    payload: Omit<PlanningSettings, 'id' | 'exam_round_id' | 'updated_by_member_id'>,
    roundId: number,
  ): Observable<PlanningSettings>;
  updateExamRound(
    payload: ExamRoundUpdate,
    roundId: number,
  ): Observable<WithoutHttpLinks<ExamRound>>;
  requestAvailabilities(
    payload: AvailabilityRequest,
    roundId: number,
  ): Observable<WithoutHttpLinks<ExamRound>>;
  createCandidateExamDay(
    payload: Omit<CandidateExamDay, 'id' | 'exam_round_id'>,
    roundId: number,
  ): Observable<CandidateExamDay>;
  generateCandidateExamDays(
    roundId: number,
  ): Observable<WithoutHttpLinks<CandidateDayGenerationResult>>;
  updateCandidateExamDay(
    id: number,
    payload: Partial<Pick<CandidateExamDay, 'is_active'>>,
  ): Observable<CandidateExamDay>;
  saveMemberAvailability(
    payload: Pick<
      MemberAvailability,
      'committee_member_id' | 'candidate_exam_day_id' | 'availability'
    >,
    roundId: number,
  ): Observable<MemberAvailability>;
  generateProposal(): Observable<WithoutHttpLinks<PlanningResult>>;
  confirmPlan(): Observable<WithoutHttpLinks<PlanningResult>>;
  getPlanningProposal(): Observable<WithoutHttpLinks<EditablePlanningProposal>>;
  savePlanningProposal(
    proposal: EditablePlanningProposal,
  ): Observable<WithoutHttpLinks<EditablePlanningProposal>>;
}

export const PLANNING_PORT = new InjectionToken<PlanningPort>('PLANNING_PORT');
