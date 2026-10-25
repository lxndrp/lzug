import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import type {
  PlanningProposalResponse,
  PlanningProposalResultResponse,
} from '../api/generated/types.gen';
import { PlanningApiService } from '../api/planning-api.service';
import { planningBoardFixture } from '../testing/fixtures';
import { HttpPlanningAdapter } from './http-planning.adapter';

describe('HttpPlanningAdapter', () => {
  it('projects nested HAL links out of planning feature data', async () => {
    const boardWithLinks = {
      ...planningBoardFixture,
      candidates: planningBoardFixture.candidates.map((view, index) =>
        index === 0
          ? {
              ...view,
              candidate: { ...view.candidate, _links: { self: { href: '/candidate' } } },
              ...(view.roundCandidate
                ? {
                    roundCandidate: {
                      ...view.roundCandidate,
                      _links: { self: { href: '/round-candidate' } },
                    },
                  }
                : {}),
            }
          : view,
      ),
      locations: planningBoardFixture.locations.map((location) => ({
        ...location,
        _links: { self: { href: `/locations/${location.id}` } },
      })),
      days: planningBoardFixture.days.map((view) => ({
        ...view,
        ...(view.location
          ? { location: { ...view.location, _links: { self: { href: '/day-location' } } } }
          : {}),
      })),
    };
    const loadPlanningFeature = vi.fn(() =>
      of({
        round: {
          id: 8,
          exam_half_year_id: 7,
          name: 'Sommer 2027',
          committee_id: 3,
          status: 'availability_requested',
          availability_deadline: null,
          availability_reminder_at: null,
          _links: { self: { href: '/rounds/8' } },
        },
        summary: {
          round: {
            id: 8,
            name: 'Sommer 2027',
            status: 'availability_requested',
            committee_name: 'IHK',
          },
          counts: { candidates: 2, mep_count: 1, required_exam_slots: 3 },
          settings: null,
          availability: [],
          _links: { self: { href: '/summary' } },
        },
        board: boardWithLinks,
      }),
    );
    TestBed.configureTestingModule({
      providers: [
        HttpPlanningAdapter,
        { provide: PlanningApiService, useValue: { loadPlanningFeature } },
      ],
    });

    const result = await firstValueFrom(TestBed.inject(HttpPlanningAdapter).loadPlanning(8));

    expect(result.round).not.toHaveProperty('_links');
    expect(result.summary).not.toHaveProperty('_links');
    expect(result.board).toEqual(planningBoardFixture);
    expect(result.board.candidates[0].roundCandidate).not.toHaveProperty('_links');
  });

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

  it('accepts the backend confirm response without a validation object', async () => {
    const confirmPlan = vi.fn(() =>
      of({
        round_id: 8,
        revision: 4,
        status: 'plan_confirmed',
        counts: { confirmed_exam_days: 1, confirmed_slots: 1 },
        exam_days: [],
      }),
    );
    TestBed.configureTestingModule({
      providers: [HttpPlanningAdapter, { provide: PlanningApiService, useValue: { confirmPlan } }],
    });

    const result = await firstValueFrom(TestBed.inject(HttpPlanningAdapter).confirmPlan(8));

    expect(result).toEqual({
      status: 'plan_confirmed',
      counts: { confirmed_exam_days: 1, confirmed_slots: 1 },
    });
  });

  it('preserves backend calendar and notification warnings after confirmation', async () => {
    const confirmPlan = vi.fn(() =>
      of({
        status: 'plan_confirmed',
        counts: { confirmed_exam_days: 1, confirmed_slots: 1 },
        calendar_warning: 'Kalender konnten nicht vollständig vorbereitet werden.',
        notification_warning: 'Eine Benachrichtigung steht noch aus.',
      }),
    );
    TestBed.configureTestingModule({
      providers: [HttpPlanningAdapter, { provide: PlanningApiService, useValue: { confirmPlan } }],
    });

    const result = await firstValueFrom(TestBed.inject(HttpPlanningAdapter).confirmPlan(8));

    expect(result).toEqual({
      status: 'plan_confirmed',
      counts: { confirmed_exam_days: 1, confirmed_slots: 1 },
      calendar_warning: 'Kalender konnten nicht vollständig vorbereitet werden.',
      notification_warning: 'Eine Benachrichtigung steht noch aus.',
    });
  });

  it('rejects a generated proposal response without validation', async () => {
    const generateProposal = vi.fn(() =>
      of({
        round_id: 8,
        revision: 4,
        status: 'plan_proposed',
        counts: { proposals: 1 },
        exam_days: [],
      }),
    );
    TestBed.configureTestingModule({
      providers: [
        HttpPlanningAdapter,
        { provide: PlanningApiService, useValue: { generateProposal } },
      ],
    });

    await expect(
      firstValueFrom(TestBed.inject(HttpPlanningAdapter).generateProposal(8)),
    ).rejects.toThrow('Expected validation to be an object');
  });

  it('rejects a generated proposal response with malformed validation', async () => {
    const generateProposal = vi.fn(() =>
      of({
        round_id: 8,
        revision: 4,
        status: 'plan_proposed',
        counts: { proposals: 1 },
        exam_days: [],
        validation: { passed: true },
      }),
    );
    TestBed.configureTestingModule({
      providers: [
        HttpPlanningAdapter,
        { provide: PlanningApiService, useValue: { generateProposal } },
      ],
    });

    await expect(
      firstValueFrom(TestBed.inject(HttpPlanningAdapter).generateProposal(8)),
    ).rejects.toThrow('Expected validation.messages to be an array');
  });

  it('rejects malformed validation in a confirm response', async () => {
    const confirmPlan = vi.fn(() =>
      of({
        round_id: 8,
        revision: 4,
        status: 'plan_confirmed',
        counts: { confirmed_exam_days: 1, confirmed_slots: 1 },
        exam_days: [],
        validation: { passed: true },
      }),
    );
    TestBed.configureTestingModule({
      providers: [HttpPlanningAdapter, { provide: PlanningApiService, useValue: { confirmPlan } }],
    });

    await expect(
      firstValueFrom(TestBed.inject(HttpPlanningAdapter).confirmPlan(8)),
    ).rejects.toThrow('Expected validation.messages to be an array');
  });

  it('rejects confirm responses with an unsupported status', async () => {
    const confirmPlan = vi.fn(() =>
      of({ status: 'plan_proposed', counts: { confirmed_exam_days: 1, confirmed_slots: 1 } }),
    );
    TestBed.configureTestingModule({
      providers: [HttpPlanningAdapter, { provide: PlanningApiService, useValue: { confirmPlan } }],
    });

    await expect(
      firstValueFrom(TestBed.inject(HttpPlanningAdapter).confirmPlan(8)),
    ).rejects.toThrow('Unsupported confirm plan status: plan_proposed');
  });

  it('rejects confirm responses with malformed counts', async () => {
    const confirmPlan = vi.fn(() =>
      of({ status: 'plan_confirmed', counts: { confirmed_exam_days: '1', confirmed_slots: 1 } }),
    );
    TestBed.configureTestingModule({
      providers: [HttpPlanningAdapter, { provide: PlanningApiService, useValue: { confirmPlan } }],
    });

    await expect(
      firstValueFrom(TestBed.inject(HttpPlanningAdapter).confirmPlan(8)),
    ).rejects.toThrow('Expected confirm plan counts.confirmed_exam_days to be a number');
  });

  it('preserves nullable location and room identifiers from proposal responses', async () => {
    const proposal = {
      round_id: 8,
      revision: 3,
      exam_days: [
        {
          candidate_exam_day_id: 11,
          id: 12,
          date: '2027-05-03',
          room_id: null,
          location_id: null,
          status: 'proposed',
          slots: [],
          assignments: [],
        },
      ],
    } satisfies PlanningProposalResponse;
    const getPlanningProposal = vi.fn(() => of(proposal));
    TestBed.configureTestingModule({
      providers: [
        HttpPlanningAdapter,
        { provide: PlanningApiService, useValue: { getPlanningProposal } },
      ],
    });

    const result = await firstValueFrom(TestBed.inject(HttpPlanningAdapter).getPlanningProposal(8));

    expect(result.exam_days[0]).toMatchObject({ location_id: null, room_id: null });
  });
});
