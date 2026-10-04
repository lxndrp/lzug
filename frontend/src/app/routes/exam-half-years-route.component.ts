import { Component, computed, effect, inject } from '@angular/core';

import { AuthService } from '../auth/auth.service';
import { RoundContextService } from '../api/round-context.service';
import { ExamHalfYearsComponent } from '../exam-half-years/exam-half-years.component';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import type {
  CandidateAssignment,
  CandidateOption,
  CommitteeOption,
} from '../exam-half-years/exam-half-years.models';

/** Route entry for selecting and maintaining the examination context. */
@Component({
  imports: [ExamHalfYearsComponent],
  template: `
    <app-exam-half-years
      [committees]="committees()"
      [candidates]="candidates()"
      [candidateAssignments]="candidateAssignments()"
      [activeRoundId]="roundContext.roundId()"
      [readOnly]="readOnly()"
      (roundSelected)="selectExamRound($event)"
    />
  `,
})
export class ExamHalfYearsRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  protected readonly roundContext = inject(RoundContextService);
  private readonly auth = inject(AuthService);
  protected readonly readOnly = computed(
    () =>
      this.auth.session()?.demo_role !== undefined && !this.auth.hasCapability('exam-round:close'),
  );
  protected readonly committees = computed<CommitteeOption[]>(
    () => this.workspace.masterData()?.committees.map(({ id, name }) => ({ id, name })) ?? [],
  );
  protected readonly candidateReferences = computed(() => {
    const selectedRoundId = this.roundContext.roundId();
    const masterData =
      this.workspace.round()?.id === selectedRoundId ? this.workspace.masterData() : null;
    if (masterData) {
      return {
        roundId: selectedRoundId,
        candidates: masterData.candidates,
        candidateAssignments: masterData.candidateAssignments,
      };
    }

    const targeted = this.workspace.candidateReferenceSnapshot();
    return targeted?.roundId === selectedRoundId ? targeted : null;
  });
  protected readonly candidates = computed<CandidateOption[]>(
    () =>
      this.candidateReferences()?.candidates.map(({ candidate }) => ({
        id: candidate.id,
        firstName: candidate.first_name,
        lastName: candidate.last_name,
      })) ?? [],
  );
  protected readonly candidateAssignments = computed<CandidateAssignment[]>(
    () =>
      this.candidateReferences()?.candidateAssignments.map((assignment) => ({
        halfYearId: assignment.exam_half_year_id,
        candidateId: assignment.candidate_id,
        endedAt: assignment.ended_at,
      })) ?? [],
  );

  constructor() {
    effect(() => {
      if (this.auth.state() !== 'authenticated') return;
      const selectedRoundId = this.roundContext.roundId();
      if (this.workspace.round()?.id === selectedRoundId) return;

      this.workspace.refreshCandidateReferences(selectedRoundId);
    });
  }

  protected selectExamRound(id: number): void {
    this.workspace.selectExamRound(id);
  }
}
