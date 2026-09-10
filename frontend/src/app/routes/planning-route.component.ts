import { Component, ViewChild, computed, inject } from '@angular/core';
import { Router } from '@angular/router';

import type {
  AvailabilityRequest,
  CandidateExamDay,
  EditablePlanningProposal,
  ExamRoundUpdate,
} from '../api/api.models';
import { AuthService } from '../auth/auth.service';
import {
  AvailabilityPayload,
  CandidateExamDayPayload,
  PlanningComponent,
  PlanningSettingsPayload,
} from '../planning/planning.component';
import { PlanningWorkflowService } from '../planning/planning-workflow.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Route entry and command boundary for one round's scheduling workflow. */
@Component({
  imports: [PlanningComponent],
  template: `
    <app-planning
      [round]="workspace.round()"
      [summary]="workspace.summary()"
      [board]="workspace.board()"
      [masterData]="workspace.masterData()"
      [actionBusy]="workspace.actionBusy()"
      [candidateDayGenerationResult]="workflow.candidateDayGeneration()"
      [planningResult]="workflow.lastResult()"
      [availabilityOnly]="isDemoExaminer()"
      [ownMemberId]="auth.session()?.committee_member_id ?? null"
      [allowCandidateDayGeneration]="workflow.canGenerateCandidateDays()"
      [canCreateCandidateDay]="workflow.canCreateCandidateDay()"
      [canToggleCandidateDay]="workflow.canToggleCandidateDay()"
      [planningProposal]="workflow.proposal()"
      [proposalEditorState]="workflow.editorState()"
      [proposalEditorError]="workflow.editorError()"
      [proposalEditorViolations]="workflow.editorViolations()"
      (saveSettings)="savePlanningSettings($event)"
      (saveRound)="saveExamRound($event)"
      (requestAvailabilities)="requestAvailabilities($event)"
      (createCandidateDay)="createCandidateDay($event)"
      (generateCandidateDays)="generateCandidateDays($event)"
      (toggleCandidateDay)="toggleCandidateDay($event)"
      (saveAvailability)="saveAvailability($event)"
      (generateProposal)="generateProposal()"
      (loadPlanningProposal)="loadPlanningProposal()"
      (reloadPlanningProposal)="reloadPlanningProposal()"
      (savePlanningProposal)="savePlanningProposal($event)"
      (confirmPlan)="requestPlanConfirmation()"
      (cancel)="cancel()"
    />
  `,
})
export class PlanningRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  protected readonly workflow = inject(PlanningWorkflowService);
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  @ViewChild(PlanningComponent) private component?: PlanningComponent;
  protected readonly isDemoExaminer = computed(() => this.auth.session()?.demo_role === 'examiner');

  protected savePlanningSettings(payload: PlanningSettingsPayload): void {
    this.workflow.savePlanningSettings(payload);
  }

  protected saveExamRound(payload: ExamRoundUpdate): void {
    this.workflow.saveExamRound(payload);
  }

  protected requestAvailabilities(payload: AvailabilityRequest): void {
    this.workflow.requestAvailabilities(payload);
  }

  protected createCandidateDay(payload: CandidateExamDayPayload): void {
    this.workflow.connect(this.component);
    this.workflow.createCandidateDay(payload);
  }

  protected generateCandidateDays(payload: PlanningSettingsPayload): void {
    this.workflow.generateCandidateDays(payload);
  }

  protected toggleCandidateDay(day: CandidateExamDay): void {
    this.workflow.toggleCandidateDay(day);
  }

  protected saveAvailability(payload: AvailabilityPayload): void {
    this.workflow.connect(this.component);
    this.workflow.saveAvailability(payload);
  }

  protected generateProposal(): void {
    this.workflow.generateProposal();
  }

  protected requestPlanConfirmation(): void {
    this.workflow.connect(this.component);
    this.workflow.requestPlanConfirmation();
  }

  protected loadPlanningProposal(): void {
    this.workflow.connect(this.component);
    this.workflow.loadPlanningProposal();
  }

  protected reloadPlanningProposal(): void {
    this.workflow.connect(this.component);
    this.workflow.reloadPlanningProposal();
  }

  protected savePlanningProposal(proposal: EditablePlanningProposal): void {
    this.workflow.connect(this.component);
    this.workflow.savePlanningProposal(proposal);
  }

  protected cancel(): void {
    void this.router.navigateByUrl('/scheduling-overview');
  }
}
