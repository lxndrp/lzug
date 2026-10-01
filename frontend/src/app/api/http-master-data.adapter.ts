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

/** HTTP/OpenAPI adapter for candidate and committee-member application operations. */
@Injectable({ providedIn: 'root' })
export class HttpMasterDataAdapter implements MasterDataPort {
  private readonly api = inject(MasterDataApiService);

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
