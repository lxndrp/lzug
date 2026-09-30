import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import { PlanningApiService } from './planning-api.service';
import { HttpWorkspaceAdapter } from './http-workspace.adapter';

describe('HttpWorkspaceAdapter', () => {
  it('maps the API root to application data and removes HAL links throughout the snapshot', async () => {
    const refreshDashboard = vi.fn(() =>
      of({
        root: { version: '1.2.3', _links: { self: { href: '/api' } } },
        round: { id: 7, _links: { self: { href: '/api/exam-rounds/7' } } },
        summary: { _links: { self: { href: '/api/round-summary' } } },
        board: {
          days: [{ day: { id: 4, _links: { self: { href: '/api/exam-days/4' } } } }],
        },
        masterData: { committees: [{ id: 3, _links: { self: { href: '/api/committees/3' } } }] },
      }),
    );

    TestBed.configureTestingModule({
      providers: [
        HttpWorkspaceAdapter,
        { provide: PlanningApiService, useValue: { refreshDashboard } },
      ],
    });

    const snapshot = await firstValueFrom(TestBed.inject(HttpWorkspaceAdapter).loadDashboard(7));

    expect(refreshDashboard).toHaveBeenCalledWith(7);
    expect(snapshot).toEqual({
      applicationVersion: '1.2.3',
      round: { id: 7 },
      summary: {},
      board: { days: [{ day: { id: 4 } }] },
      masterData: { committees: [{ id: 3 }] },
    });
  });
});
