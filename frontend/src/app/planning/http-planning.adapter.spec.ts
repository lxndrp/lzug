import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import type {
  PlanningProposalResponse,
  PlanningProposalResultResponse,
} from '../api/generated/types.gen';
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
    const sendAvailabilityRequests = vi.fn(() =>
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
        { provide: PlanningApiService, useValue: { sendAvailabilityRequests } },
      ],
    });

    const result = await firstValueFrom(
      TestBed.inject(HttpPlanningAdapter).sendAvailabilityRequests(8),
    );

    expect(sendAvailabilityRequests).toHaveBeenCalledWith(8);
    expect(result).toEqual({
      id: 8,
      name: 'Sommer 2027',
      status: 'availability_requested',
    });
  });

  it('projects generated proposal responses to feature-owned editable data', async () => {
    const proposal = {
      round_id: 8,
      revision: 3,
      exam_days: [
        {
          candidate_exam_day_id: 11,
          id: 12,
          date: '2027-05-03',
          room_id: 4,
          location_id: 6,
          status: 'proposed',
          _links: { self: { href: '/api/exam-days/12' } },
          slots: [
            {
              round_candidate_id: 9,
              id: 14,
              slot_type: 'regular',
              starts_at: '09:00',
              ends_at: '10:00',
              sequence_number: 1,
              status: 'proposed',
              _links: { self: { href: '/api/slots/14' } },
            },
          ],
          assignments: [
            {
              committee_member_id: 3,
              id: 15,
              assignment_role: 'examiner',
              day_part: 'morning',
              fallback_status: null,
              _links: { self: { href: '/api/assignments/15' } },
            },
          ],
        },
      ],
      _links: { self: { href: '/api/exam-rounds/8/planning-proposal' } },
    } satisfies PlanningProposalResponse;
    const getPlanningProposal = vi.fn(() => of(proposal));
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
      exam_days: [
        {
          candidate_exam_day_id: 11,
          id: 12,
          date: '2027-05-03',
          room_id: 4,
          location_id: 6,
          status: 'proposed',
          slots: [
            {
              round_candidate_id: 9,
              id: 14,
              slot_type: 'regular',
              starts_at: '09:00',
              ends_at: '10:00',
              sequence_number: 1,
              status: 'proposed',
            },
          ],
          assignments: [
            {
              committee_member_id: 3,
              id: 15,
              assignment_role: 'examiner',
              day_part: 'morning',
              fallback_status: null,
            },
          ],
        },
      ],
    });
  });

  it('projects generated proposal result fields and checks open validation details', async () => {
    const generatedResult = {
      round_id: 8,
      revision: 3,
      status: 'plan_proposed',
      counts: { proposals: 1 },
      exam_days: [],
      validation: { passed: true, messages: ['Prüfungsplan ist vollständig.'] },
      conflicts: [
        {
          date: '2027-05-03',
          day_part: 'morning',
          reservation: 'confirmed',
          message: 'Mitglied ist bereits eingeplant.',
        },
      ],
      notification_warning: 'Eine Benachrichtigung steht noch aus.',
      calendar_warning: 'Ein Kalendereintrag konnte nicht aktualisiert werden.',
      _links: { self: { href: '/api/planning-proposals' } },
    } satisfies PlanningProposalResultResponse;
    const generateProposal = vi.fn(() => of(generatedResult));
    TestBed.configureTestingModule({
      providers: [
        HttpPlanningAdapter,
        { provide: PlanningApiService, useValue: { generateProposal } },
      ],
    });

    const result = await firstValueFrom(TestBed.inject(HttpPlanningAdapter).generateProposal(8));

    expect(result).toEqual({
      status: 'plan_proposed',
      counts: { proposals: 1 },
      validation: { passed: true, messages: ['Prüfungsplan ist vollständig.'] },
      conflicts: [
        {
          date: '2027-05-03',
          day_part: 'morning',
          reservation: 'confirmed',
          message: 'Mitglied ist bereits eingeplant.',
        },
      ],
      notification_warning: 'Eine Benachrichtigung steht noch aus.',
      calendar_warning: 'Ein Kalendereintrag konnte nicht aktualisiert werden.',
    });
  });
});
