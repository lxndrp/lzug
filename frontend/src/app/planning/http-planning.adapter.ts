import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { PlanningApiService } from '../api/planning-api.service';
import { withoutHttpLinks } from '../application/without-http-links';
import type { PlanningPort } from './planning.port';

/** HTTP adapter for the planning workflow application boundary. */
@Injectable({ providedIn: 'root' })
export class HttpPlanningAdapter implements PlanningPort {
  private readonly api = inject(PlanningApiService);

  loadPlanning(roundId: number) {
    return this.api.loadPlanningFeature(roundId).pipe(
      map(({ round, summary, board }) => ({
        round: withoutHttpLinks(round),
        summary: withoutHttpLinks(summary),
        board: withoutHttpLinks(board),
      })),
    );
  }

  savePlanningSettings(...args: Parameters<PlanningPort['savePlanningSettings']>) {
    return this.api.savePlanningSettings(...args).pipe(map(withoutHttpLinks));
  }

  updateExamRound(...args: Parameters<PlanningPort['updateExamRound']>) {
    return this.api.updateExamRound(...args).pipe(map(withoutHttpLinks));
  }

  requestAvailabilities(...args: Parameters<PlanningPort['requestAvailabilities']>) {
    return this.api.requestAvailabilities(...args).pipe(map(withoutHttpLinks));
  }

  createCandidateExamDay(...args: Parameters<PlanningPort['createCandidateExamDay']>) {
    return this.api.createCandidateExamDay(...args).pipe(map(withoutHttpLinks));
  }

  generateCandidateExamDays(...args: Parameters<PlanningPort['generateCandidateExamDays']>) {
    return this.api.generateCandidateExamDays(...args).pipe(map(withoutHttpLinks));
  }

  updateCandidateExamDay(
    id: number,
    payload: Parameters<PlanningPort['updateCandidateExamDay']>[1],
  ) {
    return this.api.updateCandidateExamDay(id, payload).pipe(map(withoutHttpLinks));
  }

  saveMemberAvailability(...args: Parameters<PlanningPort['saveMemberAvailability']>) {
    return this.api.saveMemberAvailability(...args).pipe(map(withoutHttpLinks));
  }

  generateProposal(roundId: number) {
    return this.api.generateProposal(roundId).pipe(map(withoutHttpLinks));
  }

  confirmPlan(roundId: number) {
    return this.api.confirmPlan(roundId).pipe(map(withoutHttpLinks));
  }

  getPlanningProposal(roundId: number) {
    return this.api.getPlanningProposal(roundId).pipe(map(withoutHttpLinks));
  }

  savePlanningProposal(
    roundId: number,
    proposal: Parameters<PlanningPort['savePlanningProposal']>[1],
  ) {
    return this.api.savePlanningProposal(roundId, proposal).pipe(map(withoutHttpLinks));
  }
}
