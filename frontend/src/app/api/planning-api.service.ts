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
  ConfirmedPlanRevision,
  ConfirmedPlanDayView,
  ExamDayClosure,
  ExamDayReopeningImpact,
  ExamDayReopeningScope,
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
  EditablePlanningProposal,
  Person,
  RoundCandidate,
  RoundSummary,
  SchedulingOverviewItem,
  ExecutionStatus,
  NotificationChannels,
  NotificationItem,
  NotificationProblem,
  CalendarEvent,
  CalendarFeedActivation,
  CalendarStatus,
  AbsenceReport,
  ExamProtocol,
  ExamProtocolDeclaration,
  ExamProtocolEntryCategory,
  ExamResult,
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

  getEditableConfirmedPlan(roundId = this.roundId) {
    return this.http.get<EditablePlanningProposal>(`/api/exam-rounds/${roundId}/confirmed-plan`);
  }

  saveEditableConfirmedPlan(roundId: number, proposal: EditablePlanningProposal, reason: string) {
    return this.http.put<EditablePlanningProposal>(`/api/exam-rounds/${roundId}/confirmed-plan`, {
      ...proposal,
      reason: reason.trim(),
    });
  }

  getConfirmedPlanRevisions(roundId = this.roundId) {
    return this.list<ConfirmedPlanRevision>(`/api/exam-rounds/${roundId}/confirmed-plan/revisions`);
  }

  getConfirmedPlanDay(dayId: number) {
    return this.http.get<ConfirmedPlanDayView>(`/api/confirmed-plan-days/${dayId}`);
  }

  closeExamDay(
    dayId: number,
    revision: number,
    closureType: 'regular' | 'exception',
    reason: string,
    clarificationAttempts: string,
  ) {
    return this.http.post<ExamDayClosure>(`/api/confirmed-plan-days/${dayId}/closure`, {
      revision,
      closure_type: closureType,
      confirmed: true,
      ...(closureType === 'exception'
        ? { reason: reason.trim(), clarification_attempts: clarificationAttempts.trim() }
        : {}),
    });
  }

  previewExamDayReopening(dayId: number, scope: ExamDayReopeningScope[]) {
    return this.http.post<ExamDayReopeningImpact>(
      `/api/confirmed-plan-days/${dayId}/reopening-impact`,
      { scope },
    );
  }

  reopenExamDay(
    dayId: number,
    revision: number,
    occasion: string,
    source: string,
    reason: string,
    scope: ExamDayReopeningScope[],
  ) {
    return this.http.post<ExamDayClosure>(`/api/confirmed-plan-days/${dayId}/reopenings`, {
      revision,
      occasion: occasion.trim(),
      source: source.trim(),
      reason: reason.trim(),
      scope,
    });
  }

  getNotifications() {
    return this.list<NotificationItem>('/api/notifications');
  }

  getNotificationProblems() {
    return this.list<NotificationProblem>('/api/notification-problems');
  }

  getNotificationOverview() {
    return this.list<NotificationProblem>('/api/notification-overview');
  }

  getNotificationChannels() {
    return this.http.get<NotificationChannels>('/api/notification-channels');
  }

  getCalendarStatus() {
    return this.http.get<CalendarStatus>('/api/calendar');
  }

  getCalendarEvents() {
    return this.list<CalendarEvent>('/api/calendar/events');
  }

  activateCalendarFeed(rotate = false) {
    return this.http.post<CalendarFeedActivation>('/api/calendar/feed', { rotate });
  }

  revokeCalendarFeed() {
    return this.http.delete<CalendarStatus & { notice: string }>('/api/calendar/feed');
  }

  getAbsenceReports() {
    return this.list<AbsenceReport>('/api/absence-reports');
  }

  createAbsenceReport(
    examDayId: number,
    assignmentId: number,
    reason?: string,
    dayRevision?: number,
  ) {
    return this.http.post<AbsenceReport>('/api/absence-reports', {
      exam_day_id: examDayId,
      exam_day_assignment_id: assignmentId,
      ...(reason?.trim() ? { reason: reason.trim() } : {}),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  answerReplacement(responseId: number, response: 'available' | 'unavailable') {
    return this.http.patch<AbsenceReport>(`/api/replacement-responses/${responseId}`, {
      response,
    });
  }

  selectReplacement(reportId: number, memberId: number, version: number) {
    return this.http.post<AbsenceReport>(`/api/absence-reports/${reportId}/select-replacement`, {
      committee_member_id: memberId,
      version,
    });
  }

  registerPushSubscription(endpoint: string) {
    return this.http.post<{ id: number; active: boolean }>('/api/push-subscriptions', {
      endpoint,
    });
  }

  saveCandidateAttendance(
    dayId: number,
    slotId: number,
    status: AttendanceStatus,
    arrivedAt: string | null,
    dayRevision?: number,
  ) {
    return this.http.patch<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/slots/${slotId}/attendance`,
      { status, arrived_at: arrivedAt, ...(dayRevision ? { day_revision: dayRevision } : {}) },
    );
  }

  saveMemberAttendance(
    dayId: number,
    assignmentId: number,
    status: AttendanceStatus,
    arrivedAt: string | null,
    dayRevision?: number,
  ) {
    return this.http.patch<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/assignments/${assignmentId}/attendance`,
      { status, arrived_at: arrivedAt, ...(dayRevision ? { day_revision: dayRevision } : {}) },
    );
  }

  startExamSlot(
    dayId: number,
    slotId: number,
    actualStartedAt: string | null = null,
    dayRevision?: number,
  ) {
    return this.http.post<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/slots/${slotId}/start`,
      {
        ...(actualStartedAt ? { actual_started_at: actualStartedAt } : {}),
        ...(dayRevision ? { day_revision: dayRevision } : {}),
      },
    );
  }

  updateExamSlotStatus(
    dayId: number,
    slotId: number,
    status: ExecutionStatus,
    reason?: string,
    dayRevision?: number,
    actualStartedAt?: string | null,
    actualCompletedAt?: string | null,
  ) {
    return this.http.patch<ConfirmedPlanDayView>(
      `/api/confirmed-plan-days/${dayId}/slots/${slotId}/status`,
      {
        status,
        ...(reason ? { reason } : {}),
        ...(dayRevision ? { day_revision: dayRevision } : {}),
        ...(actualStartedAt !== undefined ? { actual_started_at: actualStartedAt } : {}),
        ...(actualCompletedAt !== undefined ? { actual_completed_at: actualCompletedAt } : {}),
      },
    );
  }

  getExamProtocol(dayId: number, slotId: number) {
    return this.http.get<ExamProtocol>(
      `/api/confirmed-plan-days/${dayId}/slots/${slotId}/protocol`,
    );
  }

  updateExamProtocol(
    protocolId: number,
    version: number,
    declaration: ExamProtocolDeclaration,
    entries: Array<{
      category: ExamProtocolEntryCategory;
      statement: string;
      occurred_from: string;
      occurred_to: string | null;
    }>,
    changeReason?: string,
    dayRevision?: number,
  ) {
    return this.http.patch<ExamProtocol>(`/api/exam-protocols/${protocolId}`, {
      version,
      declaration,
      entries,
      ...(changeReason?.trim() ? { change_reason: changeReason.trim() } : {}),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  submitExamProtocol(protocolId: number, version: number, dayRevision?: number) {
    return this.http.post<ExamProtocol>(`/api/exam-protocols/${protocolId}/submit`, {
      version,
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  respondToExamProtocol(
    protocolId: number,
    version: number,
    response: 'confirmed' | 'reservation',
    entryId?: number,
    statement?: string,
    dayRevision?: number,
  ) {
    return this.http.post<ExamProtocol>(`/api/exam-protocols/${protocolId}/responses`, {
      version,
      response,
      ...(entryId === undefined ? {} : { entry_id: entryId }),
      ...(statement?.trim() ? { statement: statement.trim() } : {}),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  requestExamProtocolCorrection(
    protocolId: number,
    version: number,
    reason: string,
    dayRevision?: number,
  ) {
    return this.http.post<ExamProtocol>(`/api/exam-protocols/${protocolId}/correction-requests`, {
      version,
      reason: reason.trim(),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  openExamProtocolCorrection(
    protocolId: number,
    version: number,
    correctionRequestId: number,
    reason: string,
    reopeningReference?: string,
    dayRevision?: number,
  ) {
    return this.http.post<ExamProtocol>(`/api/exam-protocols/${protocolId}/open-correction`, {
      version,
      correction_request_id: correctionRequestId,
      reason: reason.trim(),
      ...(reopeningReference?.trim() ? { reopening_reference: reopeningReference.trim() } : {}),
      ...(dayRevision ? { day_revision: dayRevision } : {}),
    });
  }

  getExamResult(dayId: number, slotId: number) {
    return this.http.get<ExamResult>(`/api/confirmed-plan-days/${dayId}/slots/${slotId}/result`);
  }

  saveIndividualAssessment(
    resultId: number,
    version: number,
    componentKey: string,
    criterionKey: string,
    rawPoints: string,
    rationale: string,
    submitted: boolean,
    changeReason?: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.http.post<ExamResult>(`/api/exam-results/${resultId}/individual-assessments`, {
      version,
      component_key: componentKey,
      criterion_key: criterionKey,
      raw_points: rawPoints,
      rationale: rationale.trim() || null,
      submitted,
      ...(changeReason?.trim() ? { change_reason: changeReason.trim() } : {}),
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  withdrawIndividualAssessment(
    resultId: number,
    version: number,
    assessmentId: number,
    reason: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.http.post<ExamResult>(
      `/api/exam-results/${resultId}/individual-assessments/${assessmentId}/withdraw`,
      { version, reason: reason.trim(), ...(dayRevisions ? { day_revisions: dayRevisions } : {}) },
    );
  }

  discloseAssessments(
    resultId: number,
    version: number,
    componentKey: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.http.post<ExamResult>(`/api/exam-results/${resultId}/disclosures`, {
      version,
      component_key: componentKey,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  determineComponent(
    resultId: number,
    version: number,
    componentKey: string,
    points: string,
    rationale: string,
    participants: number[],
    dissent: Array<{ member_id: number; statement: string }>,
    dayRevisions?: Record<string, number>,
  ) {
    return this.http.post<ExamResult>(`/api/exam-results/${resultId}/committee-assessments`, {
      version,
      component_key: componentKey,
      points,
      rationale: rationale.trim() || null,
      participant_member_ids: participants,
      vote: { yes: participants, no: [], abstain: [] },
      dissent,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  recordExternalResult(
    resultId: number,
    version: number,
    payload: {
      area_key: string;
      points: string;
      grade?: string;
      professional_status: string;
      determining_authority: string;
      source_reference: string;
      correction_reason?: string;
    },
    dayRevisions?: Record<string, number>,
  ) {
    return this.http.post<ExamResult>(`/api/exam-results/${resultId}/external-results`, {
      version,
      ...payload,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  confirmExternalResult(
    resultId: number,
    version: number,
    externalResultId: number,
    dayRevisions?: Record<string, number>,
  ) {
    return this.http.post<ExamResult>(
      `/api/exam-results/${resultId}/external-results/${externalResultId}/confirm`,
      { version, ...(dayRevisions ? { day_revisions: dayRevisions } : {}) },
    );
  }

  determineExamResult(
    resultId: number,
    version: number,
    participants: number[],
    dissent: Array<{ member_id: number; statement: string }>,
    dayRevisions?: Record<string, number>,
  ) {
    return this.http.post<ExamResult>(`/api/exam-results/${resultId}/determine`, {
      version,
      participant_member_ids: participants,
      vote: { yes: participants, no: [], abstain: [] },
      dissent,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  confirmResultRecord(resultId: number, version: number, dayRevisions?: Record<string, number>) {
    return this.http.post<ExamResult>(`/api/exam-results/${resultId}/record-confirmations`, {
      version,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  openResultCorrection(
    resultId: number,
    version: number,
    reason: string,
    reopeningReference?: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.http.post<ExamResult>(`/api/exam-results/${resultId}/corrections`, {
      version,
      reason: reason.trim(),
      ...(reopeningReference?.trim() ? { reopening_reference: reopeningReference.trim() } : {}),
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  communicateExamResult(
    resultId: number,
    version: number,
    method: string,
    communicatedAt: string,
    externalDocumentReference?: string,
    dayRevisions?: Record<string, number>,
  ) {
    return this.http.post<ExamResult>(`/api/exam-results/${resultId}/communications`, {
      version,
      method: method.trim(),
      communicated_at: new Date(communicatedAt).toISOString(),
      ...(externalDocumentReference?.trim()
        ? {
            external_document_status: 'extern dokumentiert',
            external_document_reference: externalDocumentReference.trim(),
          }
        : {}),
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
  }

  setExamResultRetention(
    resultId: number,
    version: number,
    payload: {
      period_start?: string;
      retain_until?: string;
      legal_hold: boolean;
      hold_reason?: string;
      release_reason?: string;
    },
    dayRevisions?: Record<string, number>,
  ) {
    return this.http.put<ExamResult>(`/api/exam-results/${resultId}/retention`, {
      version,
      ...payload,
      ...(dayRevisions ? { day_revisions: dayRevisions } : {}),
    });
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

  updateCommittee(id: number, payload: Partial<Pick<Committee, 'name' | 'occupation' | 'ihk'>>) {
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

  savePlanningSettings(
    payload: Omit<PlanningSettings, 'id' | 'exam_round_id' | 'updated_by_member_id'>,
  ) {
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

  getPlanningProposal() {
    return this.http.get<EditablePlanningProposal>(
      `/api/exam-rounds/${this.roundId}/planning-proposal`,
    );
  }

  savePlanningProposal(proposal: EditablePlanningProposal) {
    return this.http.put<EditablePlanningProposal>(
      `/api/exam-rounds/${this.roundId}/planning-proposal`,
      proposal,
    );
  }

  confirmPlan() {
    return this.http.post<PlanningResult>(`/api/exam-rounds/${this.roundId}/confirm-plan`, {});
  }

  private list<T>(url: string) {
    return this.http.get<ApiCollection<T>>(url).pipe(map((collection) => collection.items));
  }
}
