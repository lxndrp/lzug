import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import type {
  Candidate as ApiCandidate,
  CommitteeMember as ApiCommitteeMember,
} from './api.models';
import { MasterDataApiService } from './master-data-api.service';
import type {
  Candidate,
  CandidateCommand,
  CandidateUpdate,
  CommitteeMember,
  CommitteeMemberCommand,
  CommitteeMemberUpdate,
} from '../master-data/master-data.models';
import type { MasterDataPort } from '../master-data/master-data.port';
import type { CandidateWorkspace, CommitteeWorkspace } from '../master-data/master-data.models';
import type { MasterData } from './master-data.models';
import type { ExamRound as ApiExamRound } from './planning.models';
import { PlanningApiService } from './planning-api.service';
import { forkJoin } from 'rxjs';

/** HTTP/OpenAPI adapter for candidate and committee-member application operations. */
@Injectable({ providedIn: 'root' })
export class HttpMasterDataAdapter implements MasterDataPort {
  private readonly api = inject(MasterDataApiService);
  private readonly planning = inject(PlanningApiService);

  loadCandidateWorkspace(roundId: number) {
    return forkJoin({
      candidates: this.api.getCandidateViews(roundId),
      assignments: this.api.getCandidateAssignments(),
      examRounds: this.api.getExamRounds(),
      committees: this.api.getCommittees(),
      activeRound: this.planning.getExamRound(roundId),
    }).pipe(map((data) => toCandidateWorkspace(data)));
  }

  loadCommitteeWorkspace() {
    return forkJoin({
      committees: this.api.getCommittees(),
      members: this.api.getCommitteeMembers(),
      persons: this.api.getPersons(),
    }).pipe(map(toCommitteeWorkspace));
  }

  createCandidate(payload: CandidateCommand) {
    return this.api.createCandidate(toApiCandidateCommand(payload)).pipe(map(fromApiCandidate));
  }

  updateCandidate(update: CandidateUpdate) {
    return this.api
      .updateCandidate(update.id, toApiCandidateCommand(update.payload))
      .pipe(map(fromApiCandidate));
  }

  deleteCandidate(id: number) {
    return this.api.deleteCandidate(id);
  }

  createCommitteeMember(payload: CommitteeMemberCommand) {
    return this.api
      .createMember({
        committee_id: payload.committeeId,
        committee_role: payload.committeeRole,
        email: payload.email,
        first_name: payload.firstName,
        is_active: payload.isActive ? 1 : 0,
        last_name: payload.lastName,
        member_status: payload.memberStatus,
        mobile: payload.mobile,
        person_id: payload.personId,
        representing_side: payload.representingSide,
      })
      .pipe(map(fromApiCommitteeMember));
  }

  updateCommitteeMember(id: number, update: CommitteeMemberUpdate) {
    return this.api
      .updateMember(id, { is_active: update.isActive ? 1 : 0 })
      .pipe(map(fromApiCommitteeMember));
  }
}

function toCandidateWorkspace(source: {
  candidates: MasterData['candidates'];
  assignments: MasterData['candidateAssignments'];
  examRounds: MasterData['examRounds'];
  committees: MasterData['committees'];
  activeRound: ApiExamRound;
}): CandidateWorkspace {
  return {
    candidates: source.candidates.map(({ candidate, roundCandidate }) => ({
      candidate: {
        id: candidate.id,
        firstName: candidate.first_name,
        lastName: candidate.last_name,
        examNumber: candidate.ihk_exam_number,
        specialization: candidate.specialization,
        trainingCompany: candidate.training_company,
      },
      ...(roundCandidate
        ? {
            roundCandidate: {
              attemptNumber: roundCandidate.attempt_number,
              requiresMep: Boolean(roundCandidate.requires_mep),
            },
          }
        : {}),
    })),
    assignments: source.assignments.map((item) => ({
      id: item.id,
      candidateId: item.candidate_id,
      examRoundId: item.exam_round_id,
      assignedAt: item.assigned_at,
      endedAt: item.ended_at,
      changeReason: item.change_reason,
    })),
    examRounds: source.examRounds.map((item) => ({
      id: item.id,
      name: item.name,
      halfYearId: item.exam_half_year_id,
      committeeId: item.committee_id,
    })),
    committees: source.committees.map(({ id, name }) => ({ id, name })),
    activeRound: {
      id: source.activeRound.id,
      name: source.activeRound.name,
      halfYearId: source.activeRound.exam_half_year_id,
      committeeId: source.activeRound.committee_id,
      status: source.activeRound.status,
    },
  };
}

function toCommitteeWorkspace(source: {
  committees: MasterData['committees'];
  members: MasterData['members'];
  persons: MasterData['persons'];
}): CommitteeWorkspace {
  return {
    committees: source.committees.map(({ id, name, occupation, ihk }) => ({
      id,
      name,
      occupation,
      ihk,
    })),
    members: source.members.map((member) => ({
      id: member.id,
      personId: member.person_id,
      committeeId: member.committee_id,
      firstName: member.first_name,
      lastName: member.last_name,
      memberStatus: member.member_status,
      committeeRole: member.committee_role,
      representingSide: member.representing_side,
      email: member.email,
      emailVerifiedAt: member.email_verified_at ?? null,
      mobile: member.mobile,
      isActive: Boolean(member.is_active),
    })),
    persons: source.persons.map(({ id, first_name, last_name, email }) => ({
      id,
      firstName: first_name,
      lastName: last_name,
      email,
    })),
  };
}

function toApiCandidateCommand(payload: CandidateCommand) {
  return {
    attempt_number: payload.attemptNumber,
    assignment_change_reason: payload.assignmentChangeReason,
    exam_round_id: payload.examRoundId,
    first_name: payload.firstName,
    ihk_exam_number: payload.examNumber,
    last_name: payload.lastName,
    requires_mep: payload.requiresMep === undefined ? undefined : Number(payload.requiresMep),
    specialization: payload.specialization,
    training_company: payload.trainingCompany,
  };
}

function fromApiCandidate(value: ApiCandidate): Candidate {
  return {
    id: value.id,
    firstName: value.first_name,
    lastName: value.last_name,
    examNumber: value.ihk_exam_number,
    specialization: value.specialization,
    trainingCompany: value.training_company,
  };
}

function fromApiCommitteeMember(value: ApiCommitteeMember): CommitteeMember {
  return {
    id: value.id,
    personId: value.person_id,
    committeeId: value.committee_id,
    firstName: value.first_name,
    lastName: value.last_name,
    memberStatus: value.member_status,
    committeeRole: value.committee_role,
    representingSide: value.representing_side,
    email: value.email,
    emailVerifiedAt: value.email_verified_at ?? null,
    mobile: value.mobile,
    isActive: Boolean(value.is_active),
  };
}
