import { Component, inject } from '@angular/core';
import { Router } from '@angular/router';

import { RoundContextService } from '../api/round-context.service';
import type { AppView } from '../app-view';
import { DashboardComponent } from '../dashboard/dashboard.component';
import { PlanningWorkflowService } from '../planning/planning-workflow.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Route entry for the selected examination round's dashboard. */
@Component({
  imports: [DashboardComponent],
  template: `
    <app-dashboard
      [summary]="workspace.summary()"
      [round]="workspace.round()"
      [board]="workspace.board()"
      [planningResult]="planning.lastResult()"
      [loading]="workspace.loading()"
      [actionBusy]="workspace.actionBusy()"
      (openView)="openView($event)"
    />
  `,
})
export class DashboardRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  protected readonly planning = inject(PlanningWorkflowService);
  private readonly roundContext = inject(RoundContextService);
  private readonly router = inject(Router);

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
