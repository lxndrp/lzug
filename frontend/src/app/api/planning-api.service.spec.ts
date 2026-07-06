import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { PlanningApiService } from './planning-api.service';
import {
  assignmentsFixture,
  availabilitiesFixture,
  candidateDaysFixture,
  committeesFixture,
  examDaysFixture,
  examSlotsFixture,
  locationsFixture,
  membersFixture,
} from '../testing/fixtures';

describe('PlanningApiService', () => {
  let service: PlanningApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });

    service = TestBed.inject(PlanningApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('should map planning board responses into sorted day views', () => {
    let dayDates: string[] = [];
    let slotIds: number[] = [];

    service.getPlanningBoard().subscribe((board) => {
      dayDates = board.days.map((item) => item.day.date);
      slotIds = board.days[0].slots.map((slot) => slot.id);
      expect(board.days[0].location?.name).toBe('Bildungszentrum HafenCity');
      expect(board.days[0].assignments.length).toBe(2);
      expect(board.members.length).toBe(3);
    });

    http.expectOne('/api/exam-days?round_id=1').flush({ items: examDaysFixture, _links: {} });
    http.expectOne('/api/exam-slots').flush({ items: examSlotsFixture, _links: {} });
    http.expectOne('/api/exam-day-assignments').flush({ items: assignmentsFixture, _links: {} });
    http.expectOne('/api/members').flush({ items: membersFixture, _links: {} });
    http.expectOne('/api/locations').flush({ items: locationsFixture, _links: {} });
    http.expectOne('/api/candidate-exam-days?round_id=1').flush({
      items: candidateDaysFixture,
      _links: {},
    });
    http.expectOne('/api/member-availabilities?round_id=1').flush({
      items: availabilitiesFixture,
      _links: {},
    });

    expect(dayDates).toEqual(['2026-11-16', '2026-11-17']);
    expect(slotIds).toEqual([1, 2]);
  });

  it('should use the backend write endpoints for planning actions', () => {
    service.generateProposal().subscribe((result) => {
      expect(result.status).toBe('plan_proposed');
      expect(result.counts['planned_slots']).toBe(16);
    });

    const proposal = http.expectOne('/api/planning-proposals');
    expect(proposal.request.method).toBe('POST');
    expect(proposal.request.body).toEqual({ round_id: 1 });
    proposal.flush({
      status: 'plan_proposed',
      validation: { passed: true, messages: [] },
      counts: { planned_slots: 16 },
    });

    service.confirmPlan().subscribe((result) => {
      expect(result.status).toBe('plan_confirmed');
      expect(result.counts['confirmed_slots']).toBe(16);
    });

    const confirm = http.expectOne('/api/exam-rounds/1/confirm-plan');
    expect(confirm.request.method).toBe('POST');
    confirm.flush({
      status: 'plan_confirmed',
      counts: { confirmed_slots: 16 },
    });
  });

  it('should expose committee and member write operations', () => {
    service.createCommittee({ name: 'PA Neu', occupation: 'Fachinformatiker/in' }).subscribe();
    const committee = http.expectOne('/api/committees');
    expect(committee.request.method).toBe('POST');
    expect(committee.request.body).toEqual({
      name: 'PA Neu',
      occupation: 'Fachinformatiker/in',
    });
    committee.flush(committeesFixture[0]);

    service.updateMember(1, { is_active: 0 }).subscribe();
    const member = http.expectOne('/api/members/1');
    expect(member.request.method).toBe('PATCH');
    expect(member.request.body).toEqual({ is_active: 0 });
    member.flush({ ...membersFixture[0], is_active: 0 });
  });
});
