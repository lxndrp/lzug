import { Component, OnDestroy, computed, inject } from '@angular/core';
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
      [actionBusy]="workflow.actionBusy()"
      [workflowEffect]="workflow.viewEffect()"
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
export class PlanningRouteComponent implements OnDestroy {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  protected readonly workflow = inject(PlanningWorkflowService);
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly viewId = Symbol('planning-route-view');
  constructor() {
    this.workflow.activateView(this.viewId);
  }

  ngOnDestroy(): void {
    this.workflow.deactivateView(this.viewId);
  }

  protected readonly isDemoExaminer = computed(() => this.auth.session()?.demo_role === 'examiner');

  protected savePlanningSettings(payload: PlanningSettingsPayload): void {
    this.workflow.savePlanningSettings(payload, this.viewId);
  }

  protected saveExamRound(payload: ExamRoundUpdate): void {
    this.workflow.saveExamRound(payload, this.viewId);
  }

  protected requestAvailabilities(payload: AvailabilityRequest): void {
    this.workflow.requestAvailabilities(payload, this.viewId);
  }

  protected createCandidateDay(payload: CandidateExamDayPayload): void {
    this.workflow.createCandidateDay(payload, this.viewId);
  }

  protected generateCandidateDays(payload: PlanningSettingsPayload): void {
    this.workflow.generateCandidateDays(payload, this.viewId);
  }

  protected toggleCandidateDay(day: CandidateExamDay): void {
    this.workflow.toggleCandidateDay(day, this.viewId);
  }

  protected saveAvailability(payload: AvailabilityPayload): void {
    this.workflow.saveAvailability(payload, this.viewId);
  }

  protected generateProposal(): void {
    this.workflow.generateProposal(this.viewId);
  }

  protected requestPlanConfirmation(): void {
    this.workflow.requestPlanConfirmation(this.viewId);
  }

  protected loadPlanningProposal(): void {
    this.workflow.loadPlanningProposal(this.viewId);
  }

  protected reloadPlanningProposal(): void {
    this.workflow.reloadPlanningProposal(this.viewId);
  }

  protected savePlanningProposal(proposal: EditablePlanningProposal): void {
    this.workflow.savePlanningProposal(proposal, this.viewId);
  }

  protected cancel(): void {
    void this.router.navigateByUrl('/scheduling-overview');
  }
}
