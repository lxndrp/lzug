import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import { PlanningApiService } from '../api/planning-api.service';
import { HttpPlanningAdapter } from './http-planning.adapter';

describe('HttpPlanningAdapter', () => {
  it('keeps round identity explicit and removes HAL links from results', async () => {
    const requestAvailabilities = vi.fn(() =>
      of({
        id: 8,
        name: 'Sommer 2027',
        status: 'availability_requested',
        _links: { self: { href: '/api/exam-rounds/8' } },
      }),
    );
    TestBed.configureTestingModule({
      providers: [
        HttpPlanningAdapter,
        { provide: PlanningApiService, useValue: { requestAvailabilities } },
      ],
    });

    const result = await firstValueFrom(
      TestBed.inject(HttpPlanningAdapter).requestAvailabilities(
        {
          name: 'Sommer 2027',
          availability_deadline: null,
          availability_reminder_at: null,
        },
        8,
      ),
    );

    expect(requestAvailabilities).toHaveBeenCalledWith(
      {
        name: 'Sommer 2027',
        availability_deadline: null,
        availability_reminder_at: null,
      },
      8,
    );
    expect(result).toEqual({
      id: 8,
      name: 'Sommer 2027',
      status: 'availability_requested',
    });
  });

  it('removes transport links recursively from editable proposals', async () => {
    const getPlanningProposal = vi.fn(() =>
      of({
        round_id: 8,
        revision: 3,
        exam_days: [
          {
            id: 12,
            date: '2027-05-03',
            slots: [{ id: 14, starts_at: '09:00', _links: { self: { href: '/api/slots/14' } } }],
          },
        ],
        _links: { self: { href: '/api/exam-rounds/8/planning-proposal' } },
      }),
    );
    TestBed.configureTestingModule({
      providers: [
        HttpPlanningAdapter,
        { provide: PlanningApiService, useValue: { getPlanningProposal } },
      ],
    });

    const result = await firstValueFrom(TestBed.inject(HttpPlanningAdapter).getPlanningProposal());

    expect(result).toEqual({
      round_id: 8,
      revision: 3,
      exam_days: [{ id: 12, date: '2027-05-03', slots: [{ id: 14, starts_at: '09:00' }] }],
    });
  });
});
