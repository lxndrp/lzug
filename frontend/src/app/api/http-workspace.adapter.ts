import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { PlanningApiService } from './planning-api.service';
import { withoutHttpLinks } from '../application/without-http-links';
import type { MasterData } from './api.models';
import type { ExamRound } from './planning.models';
import type { CandidateWorkspace, CommitteeWorkspace } from '../master-data/master-data.models';
import type { WorkspacePort } from '../shell/workspace.port';

@Injectable({ providedIn: 'root' })
export class HttpWorkspaceAdapter implements WorkspacePort {
  private readonly planningApi = inject(PlanningApiService);

  loadDashboard(roundId: number) {
    return this.planningApi.refreshDashboard(roundId).pipe(
      map(({ root, round, summary, board, masterData }) => {
        const workspaceRound = withoutHttpLinks(round);
        const workspaceMasterData = withoutHttpLinks(masterData);
        return {
          applicationVersion: root.version,
          round: workspaceRound,
          summary: withoutHttpLinks(summary),
          board: withoutHttpLinks(board),
          masterData: workspaceMasterData,
          candidateWorkspace: toCandidateWorkspace(workspaceMasterData, workspaceRound),
          committeeWorkspace: toCommitteeWorkspace(workspaceMasterData),
        };
      }),
    );
  }
}

function toCandidateWorkspace(source: MasterData, activeRound: ExamRound): CandidateWorkspace {
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
    assignments: source.candidateAssignments.map((assignment) => ({
      id: assignment.id,
      candidateId: assignment.candidate_id,
      examRoundId: assignment.exam_round_id,
      assignedAt: assignment.assigned_at,
      endedAt: assignment.ended_at,
      changeReason: assignment.change_reason,
    })),
    examRounds: source.examRounds.map((examRound) => ({
      id: examRound.id,
      name: examRound.name,
      halfYearId: examRound.exam_half_year_id,
      committeeId: examRound.committee_id,
    })),
    committees: source.committees.map((committee) => ({
      id: committee.id,
      name: committee.name,
    })),
    activeRound: {
      id: activeRound.id,
      name: activeRound.name,
      halfYearId: activeRound.exam_half_year_id,
      committeeId: activeRound.committee_id,
      status: activeRound.status,
    },
  };
}

function toCommitteeWorkspace(source: MasterData): CommitteeWorkspace {
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
    persons: source.persons.map((person) => ({
      id: person.id,
      firstName: person.first_name,
      lastName: person.last_name,
      email: person.email,
    })),
  };
}
