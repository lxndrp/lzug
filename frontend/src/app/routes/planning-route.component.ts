import { Component, OnDestroy, computed, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';

import type {
  CandidateExamDay,
  EditablePlanningProposal,
  AvailabilityRequest,
  PlanningRoundUpdate,
} from '../planning/planning.models';
import { AuthService } from '../auth/auth.service';
import {
  AvailabilityPayload,
  CandidateExamDayPayload,
  PlanningComponent,
  PlanningSettingsPayload,
} from '../planning/planning.component';
import { PlanningWorkflowService } from '../planning/planning-workflow.service';

/** Route entry and command boundary for one round's scheduling workflow. */
@Component({
  imports: [PlanningComponent],
  template: `
    @if (workflow.snapshot(); as snapshot) {
      @if (workflow.loadError()) {
        <section role="alert">
          <p>
            Die Planungsdaten konnten nicht aktualisiert werden. Angezeigte Werte können veraltet
            sein.
          </p>
          <button type="button" (click)="reloadPlanning()">Erneut versuchen</button>
        </section>
      }
      <app-planning
        [round]="snapshot.round"
        [summary]="snapshot.summary"
        [board]="snapshot.board"
        [masterData]="snapshot.board"
        [actionBusy]="workflow.actionBusy() || workflow.loadError()"
        [workflowEffects]="workflow.viewEffects()"
        [candidateDayGenerationResult]="workflow.candidateDayGeneration()"
        [planningResult]="workflow.lastResult()"
        [availabilityOnly]="isDemoExaminer()"
        [ownMemberId]="auth.session()?.committee_member_id ?? null"
        [allowCandidateDayGeneration]="workflow.canGenerateCandidateDays()"
        [canCreateCandidateDay]="workflow.canCreateCandidateDay()"
        [canToggleCandidateDay]="workflow.canToggleCandidateDay()"
        [planningProposal]="workflow.proposal()"
        [proposalSaveAcknowledgement]="workflow.proposalSaveAcknowledgement()"
        [proposalReloadAcknowledgement]="workflow.proposalReloadAcknowledgement()"
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
        (workflowEffectsConsumed)="acknowledgeWorkflowEffects($event)"
        (confirmPlan)="requestPlanConfirmation()"
        (cancel)="cancel()"
      />
    } @else if (workflow.loading()) {
      <p role="status">Planungsdaten werden geladen.</p>
    } @else if (workflow.loadError()) {
      <section role="alert">
        <p>Die Planungsdaten konnten nicht geladen werden.</p>
        <button type="button" (click)="reloadPlanning()">Erneut versuchen</button>
      </section>
    }
  `,
})
export class PlanningRouteComponent implements OnDestroy {
  protected readonly workflow = inject(PlanningWorkflowService);
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private viewId = Symbol('planning-route-view');
  protected roundId: number | null = null;
  constructor() {
    this.route.data.pipe(takeUntilDestroyed()).subscribe((data) => {
      const resolvedRoundId = data['roundId'];
      const roundId = Number(resolvedRoundId);
      if (resolvedRoundId === null || !Number.isInteger(roundId) || roundId <= 0) {
        void this.router.navigateByUrl('/scheduling-overview', { replaceUrl: true });
        return;
      }
      this.roundId = roundId;
      this.activate(roundId);
    });
  }

  ngOnDestroy(): void {
    this.workflow.deactivateView(this.viewId);
  }

  protected readonly isDemoExaminer = computed(() => this.auth.session()?.demo_role === 'examiner');

  protected savePlanningSettings(payload: PlanningSettingsPayload): void {
    if (this.roundId !== null)
      this.workflow.savePlanningSettings(payload, this.roundId, this.viewId);
  }

  protected saveExamRound(payload: PlanningRoundUpdate): void {
    if (this.roundId !== null) this.workflow.saveExamRound(payload, this.roundId, this.viewId);
  }

  protected requestAvailabilities(payload: AvailabilityRequest): void {
    if (this.roundId !== null)
      this.workflow.requestAvailabilities(payload, this.roundId, this.viewId);
  }

  protected createCandidateDay(payload: CandidateExamDayPayload): void {
    if (this.roundId !== null) this.workflow.createCandidateDay(payload, this.roundId, this.viewId);
  }

  protected generateCandidateDays(payload: PlanningSettingsPayload): void {
    if (this.roundId !== null)
      this.workflow.generateCandidateDays(payload, this.roundId, this.viewId);
  }

  protected toggleCandidateDay(day: CandidateExamDay): void {
    if (this.roundId !== null) this.workflow.toggleCandidateDay(day, this.roundId, this.viewId);
  }

  protected saveAvailability(payload: AvailabilityPayload): void {
    if (this.roundId !== null) this.workflow.saveAvailability(payload, this.roundId, this.viewId);
  }

  protected generateProposal(): void {
    if (this.roundId !== null) this.workflow.generateProposal(this.roundId, this.viewId);
  }

  protected requestPlanConfirmation(): void {
    if (this.roundId !== null) this.workflow.requestPlanConfirmation(this.roundId, this.viewId);
  }

  protected loadPlanningProposal(): void {
    if (this.roundId !== null) this.workflow.loadPlanningProposal(this.roundId, this.viewId);
  }

  protected reloadPlanningProposal(): void {
    if (this.roundId !== null) this.workflow.reloadPlanningProposal(this.roundId, this.viewId);
  }

  protected savePlanningProposal(proposal: EditablePlanningProposal): void {
    if (this.roundId !== null)
      this.workflow.savePlanningProposal(proposal, this.roundId, this.viewId);
  }

  protected acknowledgeWorkflowEffects(throughVersion: number): void {
    this.workflow.acknowledgeViewEffects(this.viewId, throughVersion);
  }

  protected cancel(): void {
    void this.router.navigateByUrl('/scheduling-overview');
  }

  protected reloadPlanning(): void {
    if (this.roundId !== null) this.workflow.activateView(this.viewId, this.roundId);
  }

  private activate(roundId: number): void {
    // A new token for every route activation prevents a delayed result from a
    // previous A -> B -> A visit from being mistaken for the current A view.
    this.viewId = Symbol('planning-route-activation');
    this.workflow.activateView(this.viewId, roundId);
  }
}
