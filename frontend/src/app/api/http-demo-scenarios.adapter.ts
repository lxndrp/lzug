import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import type { DemoScenarioOverview as ApiDemoScenarioOverview } from './api.models';
import { RuntimeExperienceService } from '../runtime/runtime-experience.service';
import type { DemoScenariosPort } from '../demo-scenarios/application/demo-scenarios.port';
import type { DemoScenarioOverview } from '../demo-scenarios/demo-scenarios.models';

/** HTTP/OpenAPI adapter for the transport-neutral demo-scenarios port. */
@Injectable({ providedIn: 'root' })
export class HttpDemoScenariosAdapter implements DemoScenariosPort {
  private readonly runtime = inject(RuntimeExperienceService);

  getOverview() {
    return this.runtime.getDemoScenarios().pipe(map(fromApiOverview));
  }

  reset() {
    return this.runtime.resetDemoScenarios().pipe(map(() => undefined));
  }
}

function fromApiOverview(value: ApiDemoScenarioOverview): DemoScenarioOverview {
  return {
    createdAt: value.created_at,
    currentRole: value.current_role,
    demoMatrixVersion: value.demo_matrix_version,
    expiresAt: value.expires_at,
    locationContract: value.location_contract,
    mode: value.mode,
    notices: [...value.notices],
    preparedPlanChange: {
      assignmentId: value.prepared_plan_change.assignment_id,
      dayId: value.prepared_plan_change.day_id,
      reason: value.prepared_plan_change.reason,
      replacementMemberId: value.prepared_plan_change.replacement_member_id,
      roundId: value.prepared_plan_change.round_id,
      sourceLocationId: value.prepared_plan_change.source_location_id,
      targetLocationId: value.prepared_plan_change.target_location_id,
    },
    remainingSeconds: value.remaining_seconds,
    roles: value.roles.map((role) => ({
      displayName: role.display_name,
      name: role.name,
      task: role.task,
    })),
    scenarios: value.scenarios.map((scenario) => ({
      completedSteps: scenario.completed_steps,
      id: scenario.id,
      nextAction: scenario.next_action,
      nextRole: scenario.next_role,
      path: scenario.path,
      status: scenario.status,
      title: scenario.title,
      totalSteps: scenario.total_steps,
    })),
  };
}
