/** Feature-owned views and commands for candidate and committee-member administration. */
export type Candidate = {
  id: number;
  firstName: string;
  lastName: string;
  examNumber: string;
  specialization: string;
  trainingCompany: string;
};

export type CandidateRound = {
  attemptNumber: number;
  requiresMep: boolean;
};

export type CandidateView = {
  candidate: Candidate;
  roundCandidate?: CandidateRound;
};

export type CandidateAssignment = {
  id: number;
  candidateId: number;
  examRoundId: number;
  assignedAt: string;
  endedAt: string | null;
  changeReason: string | null;
};

export type CandidateExamRound = {
  id: number;
  name: string;
  halfYearId: number;
  committeeId: number;
};

export type CandidateCommittee = { id: number; name: string };

export type CandidateWorkspace = {
  candidates: CandidateView[];
  assignments: CandidateAssignment[];
  examRounds: CandidateExamRound[];
  committees: CandidateCommittee[];
  activeRound: (CandidateExamRound & { status: string }) | null;
};

export type Committee = { id: number; name: string; occupation: string; ihk: string };

export type CommitteeMember = {
  id: number;
  personId: number;
  committeeId: number;
  firstName: string;
  lastName: string;
  memberStatus: string;
  committeeRole: string;
  representingSide: string;
  email: string;
  emailVerifiedAt: string | null;
  mobile: string | null;
  isActive: boolean;
};

export type CommitteePerson = {
  id: number;
  firstName: string;
  lastName: string;
  email: string;
};

export type CommitteeWorkspace = {
  committees: Committee[];
  members: CommitteeMember[];
  persons: CommitteePerson[];
};

export type CandidateCommand = {
  firstName: string;
  lastName: string;
  examNumber: string;
  specialization: string;
  trainingCompany: string;
  attemptNumber?: number;
  requiresMep?: boolean;
  examRoundId?: number | null;
  assignmentChangeReason?: string | null;
};

export type CandidateUpdate = { id: number; payload: CandidateCommand };

export type CommitteeMemberCommand = {
  committeeId: number;
  memberStatus: string;
  committeeRole: string;
  representingSide: string;
  isActive: boolean;
  personId?: number;
  firstName?: string;
  lastName?: string;
  email?: string;
  mobile?: string | null;
};

export type CommitteeMemberUpdate = { isActive: boolean };
