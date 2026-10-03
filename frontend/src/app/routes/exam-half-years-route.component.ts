import { Component, computed, inject } from '@angular/core';

import { AuthService } from '../auth/auth.service';
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
      [activeRoundId]="workspace.round()?.id || null"
      [readOnly]="readOnly()"
      (roundSelected)="selectExamRound($event)"
    />
  `,
})
export class ExamHalfYearsRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  private readonly auth = inject(AuthService);
  protected readonly readOnly = computed(
    () =>
      this.auth.session()?.demo_role !== undefined && !this.auth.hasCapability('exam-round:close'),
  );
  protected readonly committees = computed<CommitteeOption[]>(
    () => this.workspace.masterData()?.committees.map(({ id, name }) => ({ id, name })) ?? [],
  );
  protected readonly candidates = computed<CandidateOption[]>(
    () =>
      this.workspace.masterData()?.candidates.map(({ candidate }) => ({
        id: candidate.id,
        firstName: candidate.first_name,
        lastName: candidate.last_name,
      })) ?? [],
  );
  protected readonly candidateAssignments = computed<CandidateAssignment[]>(
    () =>
      this.workspace.masterData()?.candidateAssignments.map((assignment) => ({
        halfYearId: assignment.exam_half_year_id,
        candidateId: assignment.candidate_id,
        endedAt: assignment.ended_at,
      })) ?? [],
  );

  protected selectExamRound(id: number): void {
    this.workspace.selectExamRound(id);
  }
}
