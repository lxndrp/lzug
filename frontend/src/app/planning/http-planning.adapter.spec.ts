import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import { PlanningApiService } from '../api/planning-api.service';
import { HttpPlanningAdapter } from './http-planning.adapter';

describe('HttpPlanningAdapter', () => {
  it('removes transport links from all resource write results', async () => {
    const linked = { id: 3, _links: { self: { href: '/api/resource/3' } } };
    const planningApi = {
      savePlanningSettings: vi.fn(() => of(linked)),
      createCandidateExamDay: vi.fn(() => of(linked)),
      updateCandidateExamDay: vi.fn(() => of(linked)),
      saveMemberAvailability: vi.fn(() => of(linked)),
    };
    TestBed.configureTestingModule({
      providers: [HttpPlanningAdapter, { provide: PlanningApiService, useValue: planningApi }],
    });
    const adapter = TestBed.inject(HttpPlanningAdapter);

    const results = await Promise.all([
      firstValueFrom(
        adapter.savePlanningSettings(
          {
            calendar_week_from: '2027-W18',
            calendar_week_to: '2027-W20',
            exams_per_day: 3,
            max_exam_days_per_week: 2,
          },
          8,
        ),
      ),
      firstValueFrom(adapter.createCandidateExamDay({ date: '2027-05-03', is_active: 1 }, 8)),
      firstValueFrom(adapter.updateCandidateExamDay(3, { is_active: 1 })),
      firstValueFrom(
        adapter.saveMemberAvailability(
          { committee_member_id: 1, candidate_exam_day_id: 3, availability: 'morning' },
          8,
        ),
      ),
    ]);

    expect(results).toEqual([{ id: 3 }, { id: 3 }, { id: 3 }, { id: 3 }]);
  });

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

    const result = await firstValueFrom(TestBed.inject(HttpPlanningAdapter).getPlanningProposal(8));

    expect(result).toEqual({
      round_id: 8,
      revision: 3,
      exam_days: [{ id: 12, date: '2027-05-03', slots: [{ id: 14, starts_at: '09:00' }] }],
    });
  });
});
