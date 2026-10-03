import { Component, inject } from '@angular/core';
import { Router } from '@angular/router';

import { RoundContextService } from '../api/round-context.service';
import type { AppView } from '../app-view';
import { DashboardComponent } from '../dashboard/dashboard.component';
import { DashboardProjectionService } from '../dashboard/dashboard-projection.service';
import { PlanningWorkflowService } from '../planning/planning-workflow.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Route entry for the selected examination round's dashboard. */
@Component({
  imports: [DashboardComponent],
  template: `
    <app-dashboard
      [summary]="dashboard.projection()?.summary ?? null"
      [round]="dashboard.projection()?.round ?? null"
      [board]="dashboard.projection()?.board ?? null"
      [planningResult]="planning.lastResult()"
      [loading]="dashboard.loading()"
      [error]="dashboard.error()"
      [locationRefreshError]="dashboard.locationRefreshError()"
      [candidateRefreshLoading]="dashboard.candidateRefreshLoading()"
      [candidateRefreshError]="dashboard.candidateRefreshError()"
      [committeeRefreshLoading]="dashboard.committeeRefreshLoading()"
      [committeeRefreshError]="dashboard.committeeRefreshError()"
      [actionBusy]="workspace.actionBusy()"
      (openView)="openView($event)"
      (retry)="dashboard.refresh()"
    />
  `,
})
export class DashboardRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  protected readonly dashboard = inject(DashboardProjectionService);
  protected readonly planning = inject(PlanningWorkflowService);
  private readonly roundContext = inject(RoundContextService);
  private readonly router = inject(Router);

  constructor() {
    this.dashboard.refresh();
  }

  protected openView(view: AppView): void {
    const paths: Record<AppView, string> = {
      dashboard: '/dashboard',
      'scheduling-overview': '/scheduling-overview',
      'confirmed-plans': '/confirmed-plans',
      'exam-day': '/confirmed-plans',
      candidates: '/candidates',
      committee: '/committee',
      planning: `/scheduling-overview/${this.roundContext.roundId()}`,
      locations: '/locations',
      'exam-half-years': '/exam-half-years',
      notifications: '/notifications',
      'absence-reports': '/absence-reports',
      'demo-scenarios': '/demo-scenarios',
      about: '/about',
    };
    void this.router.navigateByUrl(paths[view]);
  }
}
