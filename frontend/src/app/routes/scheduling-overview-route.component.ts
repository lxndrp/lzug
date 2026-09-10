import { Component, inject } from '@angular/core';
import { Router } from '@angular/router';

import { PlanningWorkflowService } from '../planning/planning-workflow.service';
import {
  SchedulingOverviewAction,
  SchedulingOverviewComponent,
} from '../scheduling-overview/scheduling-overview.component';

/** Route entry for the cross-round scheduling overview. */
@Component({
  imports: [SchedulingOverviewComponent],
  template: `<app-scheduling-overview (openRound)="openRound($event)" />`,
})
export class SchedulingOverviewRouteComponent {
  private readonly planning = inject(PlanningWorkflowService);
  private readonly router = inject(Router);

  protected openRound(action: SchedulingOverviewAction): void {
    this.planning.resetForRoundChange();
    const area = action.target === 'confirmed-plan' ? 'confirmed-plans' : 'scheduling-overview';
    void this.router.navigateByUrl(`/${area}/${action.id}`);
  }
}
