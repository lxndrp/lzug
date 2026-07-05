import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { forkJoin, map, of, switchMap } from 'rxjs';

import {
  ApiCollection,
  ApiRoot,
  CandidateExamDay,
  Committee,
  CommitteeMember,
  ExamDay,
  ExamDayAssignment,
  ExamSlot,
  Location,
  MasterData,
  MemberAvailability,
  PlanningBoard,
  PlanningResult,
  RoundSummary,
} from './api.models';

@Injectable({ providedIn: 'root' })
export class PlanningApiService {
  private readonly http = inject(HttpClient);
  private readonly roundId = 1;

  getRoot() {
    return this.http.get<ApiRoot>('/api');
  }

  getRoundSummary() {
    return this.http.get<RoundSummary>(`/api/round-summary?round_id=${this.roundId}`);
  }

  getPlanningBoard() {
    return forkJoin({
      days: this.list<ExamDay>(`/api/exam-days?round_id=${this.roundId}`),
      slots: this.list<ExamSlot>('/api/exam-slots'),
      assignments: this.list<ExamDayAssignment>('/api/exam-day-assignments'),
      members: this.list<CommitteeMember>('/api/members'),
      locations: this.list<Location>('/api/locations'),
      candidateDays: this.list<CandidateExamDay>(
        `/api/candidate-exam-days?round_id=${this.roundId}`,
      ),
      availabilities: this.list<MemberAvailability>(
        `/api/member-availabilities?round_id=${this.roundId}`,
      ),
    }).pipe(
      map(
        ({ days, slots, assignments, members, locations, candidateDays, availabilities }) => {
          const sortedDays = [...days].sort((a, b) => a.date.localeCompare(b.date));
          const board: PlanningBoard = {
            members,
            locations,
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
      members: this.list<CommitteeMember>('/api/members'),
    });
  }

  refreshDashboard() {
    return this.getRoot().pipe(
      switchMap((root) =>
        forkJoin({
          root: of(root),
          summary: this.getRoundSummary(),
          board: this.getPlanningBoard(),
          masterData: this.getMasterData(),
        }),
      ),
      map(({ root, summary, board, masterData }) => ({
        root,
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

  createMember(payload: Omit<CommitteeMember, 'id' | 'email_verified_at'>) {
    return this.http.post<CommitteeMember>('/api/members', payload);
  }

  updateMember(id: number, payload: Partial<Omit<CommitteeMember, 'id'>>) {
    return this.http.patch<CommitteeMember>(`/api/members/${id}`, payload);
  }

  generateProposal() {
    return this.http.post<PlanningResult>('/api/planning-proposals', { round_id: this.roundId });
  }

  confirmPlan() {
    return this.http.post<PlanningResult>(
      `/api/exam-rounds/${this.roundId}/confirm-plan`,
      {},
    );
  }

  private list<T>(url: string) {
    return this.http.get<ApiCollection<T>>(url).pipe(map((collection) => collection.items));
  }
}
