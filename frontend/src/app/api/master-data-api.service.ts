import { forkJoin, map } from 'rxjs';

import type {
  Candidate,
  CandidateCommitteeAssignment,
  CandidateCreateCommand,
  CandidateUpdateCommand,
  CandidateView,
  Committee,
  CommitteeMember,
  ExamVenue,
  Location,
  Person,
  RoundCandidate,
} from './master-data.models';
import type {
  CandidateCreate,
  CandidateUpdate as TransportCandidateUpdate,
  CommitteeUpdate,
  MembershipCreate,
  MembershipUpdate,
} from './generated/types.gen';
import type { ExamHalfYear, ExamRound } from './planning.models';
import { Injectable, inject } from '@angular/core';

import { ApiClient } from './api-client.service';
import { RoundContextService } from './round-context.service';

/** Committee, candidate, and cross-feature reference-data ownership. */

@Injectable({ providedIn: 'root' })
export class MasterDataApiService {
  private readonly client = inject(ApiClient);
  private readonly roundContext = inject(RoundContextService);

  private get roundId(): number {
    return this.roundContext.roundId();
  }

  getMasterData() {
    return forkJoin({
      committees: this.client.list<Committee>('/api/committees'),
      examHalfYears: this.client.list<ExamHalfYear>('/api/exam-half-years'),
      persons: this.client.list<Person>('/api/persons'),
      members: this.client.list<CommitteeMember>('/api/members'),
      candidates: this.getCandidateViews(),
      examRounds: this.client.list<ExamRound>('/api/exam-rounds'),
      candidateAssignments: this.client.list<CandidateCommitteeAssignment>(
        '/api/candidate-committee-assignments',
      ),
      locations: this.client.list<Location>('/api/locations'),
      examVenueCollection: this.client.collection<ExamVenue>('/api/exam-venues'),
    }).pipe(
      map(({ examVenueCollection, ...masterData }) => ({
        ...masterData,
        examVenues: examVenueCollection.items,
        examVenuesCanCreate: Boolean(examVenueCollection._links['create']),
      })),
    );
  }

  /**
   * Attach active-round data to each global candidate without hiding candidates
   * that have not yet been added to the selected round.
   */

  getCandidateViews(roundId = this.roundId) {
    return forkJoin({
      candidates: this.client.list<Candidate>('/api/candidates'),
      roundCandidates: this.client.list<RoundCandidate>(
        `/api/round-candidates?round_id=${roundId}&is_active=1`,
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

  updateCommittee(id: number, payload: CommitteeUpdate) {
    return this.client.patch<Committee>(`/api/committees/${id}`, payload);
  }

  createMember(payload: MembershipCreate) {
    return this.client.post<CommitteeMember>('/api/members', payload);
  }

  updateMember(id: number, payload: MembershipUpdate) {
    return this.client.patch<CommitteeMember>(`/api/members/${id}`, payload);
  }

  createCandidate(payload: CandidateCreateCommand) {
    const request = {
      attempt_number: payload.attempt_number,
      exam_round_id: payload.exam_round_id ?? this.roundId,
      first_name: payload.first_name,
      ihk_exam_number: payload.ihk_exam_number,
      last_name: payload.last_name,
      requires_mep: payload.requires_mep,
      specialization: payload.specialization,
      training_company: payload.training_company,
    } satisfies CandidateCreate;
    return this.client.post<Candidate>('/api/candidates', request);
  }

  updateCandidate(id: number, payload: CandidateUpdateCommand) {
    const request = {
      ...payload,
      exam_round_id: payload.exam_round_id ?? this.roundId,
    } satisfies TransportCandidateUpdate;
    return this.client.patch<Candidate>(`/api/candidates/${id}`, request);
  }

  deleteCandidate(id: number) {
    return this.client.delete<void>(`/api/candidates/${id}`);
  }
}
