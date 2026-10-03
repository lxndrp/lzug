import { forkJoin, map, of, switchMap } from 'rxjs';

import type { ApiRoot } from './common.models';
import type {
  CandidateDayGenerationResult,
  CandidateExamDay,
  EditablePlanningProposal,
  ExamDay,
  ExamDayAssignment,
  ExamRound,
  ExamSlot,
  AvailabilityRequest,
  MemberAvailability,
  PlanningBoard,
  PlanningResult,
  PlanningSettings,
  RoundSummary,
} from './planning.models';
import type { CommitteeMember, Location } from './master-data.models';
import type { SchedulingOverviewItem } from './execution.models';
import type { PlanningProposalWriteRequest, PlanningRoundRequest } from './generated/types.gen';
import type { ExamRoundUpdate } from './generated/types.gen';
import { Injectable, inject } from '@angular/core';

import { ApiClient } from './api-client.service';
import { RoundContextService } from './round-context.service';

import { MasterDataApiService } from './master-data-api.service';

/**
 * Planning read models and state transitions for the selected examination round.
 *
 * Domain-specific execution, personal-data, lifecycle, master-data, and venue
 * operations live in their respective API clients.
 */

@Injectable({ providedIn: 'root' })
export class PlanningApiService {
  private readonly client = inject(ApiClient);
  private readonly roundContext = inject(RoundContextService);

  private get roundId(): number {
    return this.roundContext.roundId();
  }

  private readonly masterData = inject(MasterDataApiService);

  getRoot() {
    return this.client.get<ApiRoot>('/api');
  }

  getRoundSummary(roundId = this.roundId) {
    return this.client.get<RoundSummary>(`/api/round-summary?round_id=${roundId}`);
  }

  getExamRound(roundId = this.roundId) {
    return this.client.get<ExamRound>(`/api/exam-rounds/${roundId}`);
  }

  updateExamRound(payload: ExamRoundUpdate, roundId = this.roundId) {
    return this.client.patch<ExamRound>(`/api/exam-rounds/${roundId}`, payload);
  }

  requestAvailabilities(payload: AvailabilityRequest, roundId = this.roundId) {
    return this.updateExamRound(payload, roundId).pipe(
      switchMap(() =>
        this.client.post<ExamRound>(`/api/exam-rounds/${roundId}/request-availabilities`, {}),
      ),
    );
  }

  getSchedulingOverview() {
    return this.client.list<SchedulingOverviewItem>('/api/scheduling-overview');
  }

  getLocations() {
    return this.client.list<Location>('/api/locations');
  }

  getPlanningBoard(roundId = this.roundId) {
    return forkJoin({
      days: this.client.list<ExamDay>(`/api/exam-days?round_id=${roundId}`),
      slots: this.client.list<ExamSlot>('/api/exam-slots'),
      assignments: this.client.list<ExamDayAssignment>('/api/exam-day-assignments'),
      members: this.client.list<CommitteeMember>('/api/members'),
      locations: this.client.list<Location>('/api/locations'),
      candidates: this.masterData.getCandidateViews(roundId),
      candidateDays: this.client.list<CandidateExamDay>(
        `/api/candidate-exam-days?round_id=${roundId}`,
      ),
      availabilities: this.client.list<MemberAvailability>(
        `/api/member-availabilities?round_id=${roundId}`,
      ),
    }).pipe(
      map(
        ({
          days,
          slots,
          assignments,
          members,
          locations,
          candidates,
          candidateDays,
          availabilities,
        }) => {
          const sortedDays = [...days].sort((a, b) => a.date.localeCompare(b.date));
          const board: PlanningBoard = {
            members,
            locations,
            candidates,
            candidateDays,
            availabilities,
            days: sortedDays.map((day) => ({
              day,
              location: locations.find((location) => location.id === day.location_id),
              slots: slots
                .filter((slot) => slot.exam_day_id === day.id)
                .sort((a, b) => a.sequence_number - b.sequence_number),
              assignments: assignments.filter((assignment) => assignment.exam_day_id === day.id),
            })),
          };
          return board;
        },
      ),
    );
  }

  /** Load only the dashboard projection, independently from master-data administration. */
  loadDashboardProjection(roundId = this.roundId) {
    return this.getRoot().pipe(
      switchMap((root) =>
        forkJoin({
          round: this.getExamRound(roundId),
          summary: this.getRoundSummary(roundId),
          board: this.getPlanningBoard(roundId),
        }).pipe(map((projection) => ({ root, ...projection }))),
      ),
    );
  }

  /** Load only the small context labels and application version required by the shell. */
  loadShellContext(roundId = this.roundId) {
    return this.getRoot().pipe(
      switchMap((root) =>
        forkJoin({
          round: this.getExamRound(roundId),
          summary: this.getRoundSummary(roundId),
          halfYears: this.masterData.getExamHalfYears(),
        }).pipe(
          map(({ round, summary, halfYears }) => ({
            root,
            round,
            summary,
            halfYear: halfYears.find((item) => item.id === round.exam_half_year_id)!,
          })),
        ),
      ),
    );
  }

  /** Transitional aggregate retained for planning consumers not yet migrated. */
  refreshDashboard(roundId = this.roundId) {
    return this.getRoot().pipe(
      switchMap((root) =>
        forkJoin({
          root: of(root),
          round: this.getExamRound(roundId),
          summary: this.getRoundSummary(roundId),
          board: this.getPlanningBoard(roundId),
          masterData: this.masterData.getMasterData(),
        }),
      ),
      map(({ root, round, summary, board, masterData }) => ({
        root,
        round,
        summary,
        board,
        masterData,
      })),
    );
  }

  savePlanningSettings(
    payload: Omit<PlanningSettings, 'id' | 'exam_round_id' | 'updated_by_member_id'>,
    roundId = this.roundId,
  ) {
    return this.client.post<PlanningSettings>('/api/planning-settings', {
      ...payload,
      exam_round_id: roundId,
    });
  }

  createCandidateExamDay(
    payload: Omit<CandidateExamDay, 'id' | 'exam_round_id'>,
    roundId = this.roundId,
  ) {
    return this.client.post<CandidateExamDay>('/api/candidate-exam-days', {
      ...payload,
      exam_round_id: roundId,
    });
  }

  generateCandidateExamDays(roundId = this.roundId) {
    return this.client.post<CandidateDayGenerationResult>('/api/candidate-exam-days/generate', {
      round_id: roundId,
    } satisfies PlanningRoundRequest);
  }

  updateCandidateExamDay(id: number, payload: Partial<Pick<CandidateExamDay, 'is_active'>>) {
    return this.client.patch<CandidateExamDay>(`/api/candidate-exam-days/${id}`, payload);
  }

  /** Persist an availability value in the round selected at request time. */

  saveMemberAvailability(
    payload: Pick<
      MemberAvailability,
      'committee_member_id' | 'candidate_exam_day_id' | 'availability'
    >,
    roundId = this.roundId,
  ) {
    return this.client.post<MemberAvailability>('/api/member-availabilities', {
      ...payload,
      exam_round_id: roundId,
    });
  }

  generateProposal() {
    return this.client.post<PlanningResult>('/api/planning-proposals', {
      round_id: this.roundId,
    } satisfies PlanningRoundRequest);
  }

  getPlanningProposal() {
    return this.client.get<EditablePlanningProposal>(
      `/api/exam-rounds/${this.roundId}/planning-proposal`,
    );
  }

  savePlanningProposal(proposal: EditablePlanningProposal) {
    const request: PlanningProposalWriteRequest = proposal;
    return this.client.put<EditablePlanningProposal>(
      `/api/exam-rounds/${this.roundId}/planning-proposal`,
      request,
    );
  }

  confirmPlan() {
    return this.client.post<PlanningResult>(`/api/exam-rounds/${this.roundId}/confirm-plan`, {});
  }
}
