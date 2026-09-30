import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { PlanningApiService } from '../../api/planning-api.service';
import { SchedulingOverviewPort } from '../application/scheduling-overview.port';

@Injectable({ providedIn: 'root' })
export class HttpSchedulingOverviewAdapter implements SchedulingOverviewPort {
  private readonly planningApi = inject(PlanningApiService);

  getOverview() {
    return this.planningApi.getSchedulingOverview().pipe(
      map((items) =>
        items.map((item) => ({
          id: item.id,
          name: item.name,
          status: item.status,
          statusGroup: item.status_group,
          committeeName: item.committee_name,
          examHalfYear: {
            season: item.exam_half_year.season,
            year: item.exam_half_year.year,
          },
          calendarWeekFrom: item.calendar_week_from,
          calendarWeekTo: item.calendar_week_to,
        })),
      ),
    );
  }
}
