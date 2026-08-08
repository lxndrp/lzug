import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { forkJoin, map, of, switchMap } from 'rxjs';

import {
  ApiCollection,
  AttendanceStatus,
  ApiRoot,
  AvailabilityRequest,
  Candidate,
  CandidateCommitteeAssignment,
  CandidateDayGenerationResult,
  ConfirmedPlan,
  ConfirmedPlanDayView,
  CandidateExamDay,
  CandidateView,
  Committee,
  CommitteeMember,
  ExamRound,
  ExamRoundCreate,
  ExamRoundUpdate,
  ExamDay,
  ExamDayAssignment,
  ExamSlot,
  Location,
  MemberAvailability,
  PlanningBoard,
  PlanningResult,
  PlanningSettings,
  ExamHalfYear,
  Person,
  RoundCandidate,
  RoundSummary,
  SchedulingOverviewItem,
} from './api.models';
import { RoundContextService } from './round-context.service';

/**
 * Maps UI-oriented planning aggregates onto the JSON API.
 *
 * The service owns client-side joins only. Business validation and state
 * transitions remain server-side and are described by the OpenAPI contract.
 */
@Injectable({ providedIn: 'root' })
export class PlanningApiService {
  private readonly http = inject(HttpClient);
  private readonly roundContext = inject(RoundContextService);

  private get roundId(): number {
    return this.roundContext.roundId();
  }

  getRoot() {
    return this.http.get<ApiRoot>('/api');
  }

  getRoundSummary() {
    return this.http.get<RoundSummary>(`/api/round-summary?round_id=${this.roundId}`);
  }

  getExamRound() {
    return this.http.get<ExamRound>(`/api/exam-rounds/${this.roundId}`);
  }

  updateExamRound(payload: ExamRoundUpdate) {
    return this.http.patch<ExamRound>(`/api/exam-rounds/${this.roundId}`, payload);
  }

  requestAvailabilities(payload: AvailabilityRequest) {
    return this.updateExamRound(payload).pipe(
      switchMap(() =>
        this.http.post<ExamRound>(`/api/exam-rounds/${this.roundId}/request-availabilities`, {}),
      ),
    );
  }

  listExamHalfYears() {
    return this.list<ExamHalfYear>('/api/exam-half-years');
  }

  listExamRounds() {
    return this.list<ExamRound>('/api/exam-rounds');
  }

  getSchedulingOverview() {
    return this.list<SchedulingOverviewItem>('/api/scheduling-overview');
  }

  getConfirmedPlans() {
    return this.list<ConfirmedPlan>('/api/confirmed-plans');
  }

  getConfirmedPlanDay(dayId: number) {
    return this.http.get<ConfirmedPlanDayView>(`/api/confirmed-plan-days/${dayId}`);
  }

  saveCandidateAttendance(
    dayId: number,
    slotId: number,
    status: AttendanceStatus,
    arrivedAt: string | null,
  ) {
    return this.http.patch<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/slots/${slotId}/attendance`,
      { status, arrived_at: arrivedAt },
    );
  }

  saveMemberAttendance(
    dayId: number,
    assignmentId: number,
    status: AttendanceStatus,
    arrivedAt: string | null,
  ) {
    return this.http.patch<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/assignments/${assignmentId}/attendance`,
      { status, arrived_at: arrivedAt },
    );
  }

  startExamSlot(dayId: number, slotId: number, actualStartedAt: string | null = null) {
    return this.http.post<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/slots/${slotId}/start`,
      actualStartedAt ? { actual_started_at: actualStartedAt } : {},
    );
  }

  createExamHalfYear(payload: Pick<ExamHalfYear, 'season' | 'year' | 'status'>) {
    return this.http.post<ExamHalfYear>('/api/exam-half-years', payload);
  }

  updateExamHalfYear(
    id: number,
    payload: Partial<Pick<ExamHalfYear, 'season' | 'year' | 'status'>>,
  ) {
    return this.http.patch<ExamHalfYear>(`/api/exam-half-years/${id}`, payload);
  }

  createExamRound(payload: ExamRoundCreate) {
    return this.http.post<ExamRound>('/api/exam-rounds', payload);
  }

  /**
   * Load and deterministically join the collections used by planning views.
   *
   * Slots and assignments are deliberately fetched as full collections and
   * filtered locally because their current endpoints are not round-scoped.
   */
  getPlanningBoard() {
    return forkJoin({
      days: this.list<ExamDay>(`/api/exam-days?round_id=${this.roundId}`),
      slots: this.list<ExamSlot>('/api/exam-slots'),
      assignments: this.list<ExamDayAssignment>('/api/exam-day-assignments'),
      members: this.list<CommitteeMember>('/api/members'),
      locations: this.list<Location>('/api/locations'),
      candidates: this.getCandidateViews(),
      candidateDays: this.list<CandidateExamDay>(
        `/api/candidate-exam-days?round_id=${this.roundId}`,
      ),
      availabilities: this.list<MemberAvailability>(
        `/api/member-availabilities?round_id=${this.roundId}`,
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

  getMasterData() {
    return forkJoin({
      committees: this.list<Committee>('/api/committees'),
      examHalfYears: this.list<ExamHalfYear>('/api/exam-half-years'),
      persons: this.list<Person>('/api/persons'),
      members: this.list<CommitteeMember>('/api/members'),
      candidates: this.getCandidateViews(),
      examRounds: this.list<ExamRound>('/api/exam-rounds'),
      candidateAssignments: this.list<CandidateCommitteeAssignment>(
        '/api/candidate-committee-assignments',
      ),
      locations: this.list<Location>('/api/locations'),
    });
  }

  /**
   * Attach active-round data to each global candidate without hiding candidates
   * that have not yet been added to the selected round.
   */
  getCandidateViews() {
    return forkJoin({
      candidates: this.list<Candidate>('/api/candidates'),
      roundCandidates: this.list<RoundCandidate>(
        `/api/round-candidates?round_id=${this.roundId}&is_active=1`,
      ),
    }).pipe(
      map(({ candidates, roundCandidates }) =>
        candidates.map((candidate): CandidateView => ({
          candidate,
          roundCandidate: roundCandidates.find((item) => item.candidate_id === candidate.id),
        })),
      ),
    );
  }

  /**
   * Refresh the dashboard's coherent read model for the current round.
   *
   * Independent reads run concurrently; the aggregate is emitted only after
   * all sources complete successfully.
   */
  refreshDashboard() {
    return this.getRoot().pipe(
      switchMap((root) =>
        forkJoin({
          root: of(root),
          round: this.getExamRound(),
          summary: this.getRoundSummary(),
          board: this.getPlanningBoard(),
          masterData: this.getMasterData(),
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

  createCommittee(payload: Pick<Committee, 'name' | 'occupation'>) {
    return this.http.post<Committee>('/api/committees', payload);
  }

  updateCommittee(id: number, payload: Partial<Pick<Committee, 'name' | 'occupation'>>) {
    return this.http.patch<Committee>(`/api/committees/${id}`, payload);
  }

  createMember(payload: Partial<Omit<CommitteeMember, 'id' | 'email_verified_at'>>) {
    return this.http.post<CommitteeMember>('/api/members', payload);
  }

  updateMember(id: number, payload: Partial<Omit<CommitteeMember, 'id'>>) {
    return this.http.patch<CommitteeMember>(`/api/members/${id}`, payload);
  }

  createCandidate(
    payload: Omit<Candidate, 'id'> & {
      attempt_number: number;
      requires_mep: number;
      exam_round_id?: number;
    },
  ) {
    return this.http.post<Candidate>('/api/candidates', {
      ...payload,
      exam_round_id: payload.exam_round_id ?? this.roundId,
    });
  }

  updateCandidate(
    id: number,
    payload: Omit<Candidate, 'id'> & {
      attempt_number: number;
      requires_mep: number;
      exam_round_id?: number;
      assignment_change_reason?: string;
    },
  ) {
    return this.http.patch<Candidate>(`/api/candidates/${id}`, {
      ...payload,
      exam_round_id: payload.exam_round_id ?? this.roundId,
    });
  }

  deleteCandidate(id: number) {
    return this.http.delete<void>(`/api/candidates/${id}`);
  }

  createLocation(payload: Omit<Location, 'id'>) {
    return this.http.post<Location>('/api/locations', payload);
  }

  updateLocation(id: number, payload: Partial<Omit<Location, 'id'>>) {
    return this.http.patch<Location>(`/api/locations/${id}`, payload);
  }

  deleteLocation(id: number) {
    return this.http.delete<void>(`/api/locations/${id}`);
  }

  savePlanningSettings(payload: Omit<PlanningSettings, 'id' | 'exam_round_id'>) {
    return this.http.post<PlanningSettings>('/api/planning-settings', {
      ...payload,
      exam_round_id: this.roundId,
    });
  }

  createCandidateExamDay(payload: Omit<CandidateExamDay, 'id' | 'exam_round_id'>) {
    return this.http.post<CandidateExamDay>('/api/candidate-exam-days', {
      ...payload,
      exam_round_id: this.roundId,
    });
  }

  generateCandidateExamDays() {
    return this.http.post<CandidateDayGenerationResult>('/api/candidate-exam-days/generate', {
      round_id: this.roundId,
    });
  }

  updateCandidateExamDay(id: number, payload: Partial<Pick<CandidateExamDay, 'is_active'>>) {
    return this.http.patch<CandidateExamDay>(`/api/candidate-exam-days/${id}`, payload);
  }

  /** Persist an availability value in the round selected at request time. */
  saveMemberAvailability(
    payload: Pick<
      MemberAvailability,
      'committee_member_id' | 'candidate_exam_day_id' | 'availability'
    >,
  ) {
    return this.http.post<MemberAvailability>('/api/member-availabilities', {
      ...payload,
      exam_round_id: this.roundId,
    });
  }

  generateProposal() {
    return this.http.post<PlanningResult>('/api/planning-proposals', { round_id: this.roundId });
  }

  confirmPlan() {
    return this.http.post<PlanningResult>(`/api/exam-rounds/${this.roundId}/confirm-plan`, {});
  }

  private list<T>(url: string) {
    return this.http.get<ApiCollection<T>>(url).pipe(map((collection) => collection.items));
  }
}
