import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { PlanningApiService } from '../api/planning-api.service';
import { withoutHttpLinks } from '../application/without-http-links';
import type { PlanningPort } from './planning.port';

/** HTTP adapter for the planning workflow application boundary. */
@Injectable({ providedIn: 'root' })
export class HttpPlanningAdapter implements PlanningPort {
  private readonly api = inject(PlanningApiService);

  savePlanningSettings(...args: Parameters<PlanningPort['savePlanningSettings']>) {
    return this.api.savePlanningSettings(...args);
  }

  updateExamRound(...args: Parameters<PlanningPort['updateExamRound']>) {
    return this.api.updateExamRound(...args).pipe(map(withoutHttpLinks));
  }

  requestAvailabilities(...args: Parameters<PlanningPort['requestAvailabilities']>) {
    return this.api.requestAvailabilities(...args).pipe(map(withoutHttpLinks));
  }

  createCandidateExamDay(...args: Parameters<PlanningPort['createCandidateExamDay']>) {
    return this.api.createCandidateExamDay(...args);
  }

  generateCandidateExamDays(...args: Parameters<PlanningPort['generateCandidateExamDays']>) {
    return this.api.generateCandidateExamDays(...args).pipe(map(withoutHttpLinks));
  }

  updateCandidateExamDay(...args: Parameters<PlanningPort['updateCandidateExamDay']>) {
    return this.api.updateCandidateExamDay(...args);
  }

  saveMemberAvailability(...args: Parameters<PlanningPort['saveMemberAvailability']>) {
    return this.api.saveMemberAvailability(...args);
  }

  generateProposal() {
    return this.api.generateProposal().pipe(map(withoutHttpLinks));
  }

  confirmPlan() {
    return this.api.confirmPlan().pipe(map(withoutHttpLinks));
  }

  getPlanningProposal() {
    return this.api.getPlanningProposal().pipe(map(withoutHttpLinks));
  }

  savePlanningProposal(proposal: Parameters<PlanningPort['savePlanningProposal']>[0]) {
    return this.api.savePlanningProposal(proposal).pipe(map(withoutHttpLinks));
  }
}
