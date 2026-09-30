import { Injectable, inject } from '@angular/core';

import { SCHEDULING_OVERVIEW_PORT } from './scheduling-overview.port';

/** Application operation for reading the cross-round scheduling overview. */
@Injectable({ providedIn: 'root' })
export class SchedulingOverviewApplication {
  private readonly port = inject(SCHEDULING_OVERVIEW_PORT);

  getOverview() {
    return this.port.getOverview();
  }
}
