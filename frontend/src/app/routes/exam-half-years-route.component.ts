import { Component, computed, inject } from '@angular/core';

import { AuthService } from '../auth/auth.service';
import { ExamHalfYearsComponent } from '../exam-half-years/exam-half-years.component';
import { PlanningWorkflowService } from '../planning/planning-workflow.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Route entry for selecting and maintaining the examination context. */
@Component({
  imports: [ExamHalfYearsComponent],
  template: `
    <app-exam-half-years
      [committees]="workspace.masterData()?.committees || []"
      [candidates]="workspace.masterData()?.candidates || []"
      [candidateAssignments]="workspace.masterData()?.candidateAssignments || []"
      [activeRoundId]="workspace.round()?.id || null"
      [readOnly]="readOnly()"
      (roundSelected)="selectExamRound($event)"
    />
  `,
})
export class ExamHalfYearsRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  private readonly auth = inject(AuthService);
  private readonly planning = inject(PlanningWorkflowService);
  protected readonly readOnly = computed(
    () =>
      this.auth.session()?.demo_role !== undefined && !this.auth.hasCapability('exam-round:close'),
  );

  protected selectExamRound(id: number): void {
    this.planning.resetForRoundChange();
    this.workspace.selectExamRound(id);
  }
}
