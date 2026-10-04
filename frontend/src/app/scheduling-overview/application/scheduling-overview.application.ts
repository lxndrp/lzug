import { Injectable, inject } from '@angular/core';
import { PlanningWriteEventsService } from '../../application/planning-write-events.service';

import { SCHEDULING_OVERVIEW_PORT } from './scheduling-overview.port';

/** Application operation for reading the cross-round scheduling overview. */
@Injectable({ providedIn: 'root' })
export class SchedulingOverviewApplication {
  private readonly port = inject(SCHEDULING_OVERVIEW_PORT);
  private readonly writeEvents = inject(PlanningWriteEventsService);

  readonly planningWritesCommitted$ = this.writeEvents.committed$;

  getOverview() {
    return this.port.getOverview();
  }
}
