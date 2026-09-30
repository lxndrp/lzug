import { examRoundFixture, masterDataFixture } from './fixtures';
import type { CandidateWorkspace, CommitteeWorkspace } from '../master-data/master-data.models';

export const candidateWorkspaceFixture: CandidateWorkspace = {
  candidates: masterDataFixture.candidates.map(({ candidate, roundCandidate }) => ({
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
  assignments: masterDataFixture.candidateAssignments.map((assignment) => ({
    id: assignment.id,
    candidateId: assignment.candidate_id,
    examRoundId: assignment.exam_round_id,
    assignedAt: assignment.assigned_at,
    endedAt: assignment.ended_at,
    changeReason: assignment.change_reason,
  })),
  examRounds: masterDataFixture.examRounds.map((round) => ({
    id: round.id,
    name: round.name,
    halfYearId: round.exam_half_year_id,
    committeeId: round.committee_id,
  })),
  committees: masterDataFixture.committees.map(({ id, name, occupation, ihk }) => ({
    id,
    name,
    occupation,
    ihk,
  })),
  activeRound: {
    id: examRoundFixture.id,
    name: examRoundFixture.name,
    halfYearId: examRoundFixture.exam_half_year_id,
    committeeId: examRoundFixture.committee_id,
    status: examRoundFixture.status,
  },
};

export const committeeWorkspaceFixture: CommitteeWorkspace = {
  committees: masterDataFixture.committees.map(({ id, name, occupation, ihk }) => ({
    id,
    name,
    occupation,
    ihk,
  })),
  members: masterDataFixture.members.map((member) => ({
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
  persons: masterDataFixture.persons.map((person) => ({
    id: person.id,
    firstName: person.first_name,
    lastName: person.last_name,
    email: person.email,
  })),
};
