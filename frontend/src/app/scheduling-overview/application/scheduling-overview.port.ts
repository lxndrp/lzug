import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import { SchedulingOverviewItem } from '../scheduling-overview.models';

export interface SchedulingOverviewPort {
  getOverview(): Observable<readonly SchedulingOverviewItem[]>;
}

export const SCHEDULING_OVERVIEW_PORT = new InjectionToken<SchedulingOverviewPort>(
  'SCHEDULING_OVERVIEW_PORT',
);
