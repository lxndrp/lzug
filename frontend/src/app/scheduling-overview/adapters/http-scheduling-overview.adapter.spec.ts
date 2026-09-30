import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import { PlanningApiService } from '../../api/planning-api.service';
import { SchedulingOverviewItem as ApiSchedulingOverviewItem } from '../../api/execution.models';
import { HttpSchedulingOverviewAdapter } from './http-scheduling-overview.adapter';

describe('HttpSchedulingOverviewAdapter', () => {
  it('maps the API transport model to the feature contract', async () => {
    const getSchedulingOverview = vi.fn(() => of([apiItem()]));
    TestBed.configureTestingModule({
      providers: [
        HttpSchedulingOverviewAdapter,
        { provide: PlanningApiService, useValue: { getSchedulingOverview } },
      ],
    });

    const adapter = TestBed.inject(HttpSchedulingOverviewAdapter);
    await expect(firstValueFrom(adapter.getOverview())).resolves.toEqual([
      {
        id: 7,
        name: 'Prüfungsrunde',
        status: 'draft',
        statusGroup: 'draft',
        committeeName: 'Prüfungsausschuss Beispielstadt',
        examHalfYear: { season: 'winter', year: 2026 },
        calendarWeekFrom: '2026-W47',
        calendarWeekTo: '2026-W49',
      },
    ]);
    expect(getSchedulingOverview).toHaveBeenCalledOnce();
  });
});

function apiItem(): ApiSchedulingOverviewItem {
  return {
    id: 7,
    name: 'Prüfungsrunde',
    status: 'draft',
    status_group: 'draft',
    committee_name: 'Prüfungsausschuss Beispielstadt',
    exam_half_year: { id: 2, season: 'winter', year: 2026, status: 'active' },
    calendar_week_from: '2026-W47',
    calendar_week_to: '2026-W49',
    can_continue: true,
    _links: { self: { href: '/api/scheduling-overview/7' } },
  };
}
