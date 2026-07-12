import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { PlanningApiService } from './planning-api.service';
import {
  assignmentsFixture,
  availabilitiesFixture,
  candidateDaysFixture,
  candidatesFixture,
  committeesFixture,
  examDaysFixture,
  examSlotsFixture,
  locationsFixture,
  membersFixture,
  roundCandidatesFixture,
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
      expect(board.candidates.length).toBe(2);
    });

    http.expectOne('/api/exam-days?round_id=1').flush({ items: examDaysFixture, _links: {} });
    http.expectOne('/api/exam-slots').flush({ items: examSlotsFixture, _links: {} });
    http.expectOne('/api/exam-day-assignments').flush({ items: assignmentsFixture, _links: {} });
    http.expectOne('/api/members').flush({ items: membersFixture, _links: {} });
    http.expectOne('/api/locations').flush({ items: locationsFixture, _links: {} });
    http.expectOne('/api/candidates').flush({ items: candidatesFixture, _links: {} });
    http.expectOne('/api/round-candidates?round_id=1').flush({
      items: roundCandidatesFixture,
      _links: {},
    });
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

  it('should combine candidates with their round metadata', () => {
    service.getCandidateViews().subscribe((items) => {
      expect(items.length).toBe(2);
      expect(items[1].candidate.last_name).toBe('Weber');
      expect(items[1].roundCandidate?.attempt_number).toBe(2);
      expect(items[1].roundCandidate?.requires_mep).toBe(1);
    });

    http.expectOne('/api/candidates').flush({ items: candidatesFixture, _links: {} });
    http.expectOne('/api/round-candidates?round_id=1').flush({
      items: roundCandidatesFixture,
      _links: {},
    });
  });

  it('should expose candidate write operations', () => {
    service
      .createCandidate({
        first_name: 'Mara',
        last_name: 'Schulz',
        ihk_exam_number: 'FI-2026-1081',
        specialization: 'data_and_process_analysis',
        training_company: 'Datenspur Analytics GmbH',
        attempt_number: 1,
        requires_mep: 0,
      })
      .subscribe();

    const create = http.expectOne('/api/candidates');
    expect(create.request.method).toBe('POST');
    expect(create.request.body).toEqual({
      first_name: 'Mara',
      last_name: 'Schulz',
      ihk_exam_number: 'FI-2026-1081',
      specialization: 'data_and_process_analysis',
      training_company: 'Datenspur Analytics GmbH',
      attempt_number: 1,
      requires_mep: 0,
      exam_round_id: 1,
    });
    create.flush(candidatesFixture[0]);

    service.deleteCandidate(1).subscribe();
    const remove = http.expectOne('/api/candidates/1');
    expect(remove.request.method).toBe('DELETE');
    remove.flush({});
  });

  it('should expose location write operations', () => {
    service
      .createLocation({
        committee_id: 1,
        name: 'IHK Campus',
        street: 'Prüfungsweg 2',
        postal_code: '20457',
        city: 'Hamburg',
        room: 'A 1.01',
        is_active: 1,
      })
      .subscribe();

    const request = http.expectOne('/api/locations');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      committee_id: 1,
      name: 'IHK Campus',
      street: 'Prüfungsweg 2',
      postal_code: '20457',
      city: 'Hamburg',
      room: 'A 1.01',
      is_active: 1,
    });
    request.flush(locationsFixture[0]);

    service.deleteLocation(1).subscribe();
    const remove = http.expectOne('/api/locations/1');
    expect(remove.request.method).toBe('DELETE');
    remove.flush({});
  });

  it('should save planning settings for the active round', () => {
    service
      .savePlanningSettings({
        calendar_week_from: '2026-W47',
        calendar_week_to: '2026-W49',
        exams_per_day: 6,
        max_exam_days_per_week: 3,
        lunch_break_enabled: 1,
        default_location_id: 1,
        updated_by_member_id: 1,
      })
      .subscribe();

    const request = http.expectOne('/api/planning-settings');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      exam_round_id: 1,
      calendar_week_from: '2026-W47',
      calendar_week_to: '2026-W49',
      exams_per_day: 6,
      max_exam_days_per_week: 3,
      lunch_break_enabled: 1,
      default_location_id: 1,
      updated_by_member_id: 1,
    });
    request.flush({});
  });

  it('should expose possible day and availability write operations', () => {
    service.createCandidateExamDay({ date: '2026-11-18', is_active: 1 }).subscribe();
    const createDay = http.expectOne('/api/candidate-exam-days');
    expect(createDay.request.method).toBe('POST');
    expect(createDay.request.body).toEqual({
      exam_round_id: 1,
      date: '2026-11-18',
      is_active: 1,
    });
    createDay.flush({ id: 3, exam_round_id: 1, date: '2026-11-18', is_active: 1 });

    service.updateCandidateExamDay(2, { is_active: 1 }).subscribe();
    const candidateDay = http.expectOne('/api/candidate-exam-days/2');
    expect(candidateDay.request.method).toBe('PATCH');
    expect(candidateDay.request.body).toEqual({ is_active: 1 });
    candidateDay.flush({ ...candidateDaysFixture[1], is_active: 1 });

    service
      .saveMemberAvailability({
        committee_member_id: 1,
        candidate_exam_day_id: 2,
        availability: 'morning',
      })
      .subscribe();
    const availability = http.expectOne('/api/member-availabilities');
    expect(availability.request.method).toBe('POST');
    expect(availability.request.body).toEqual({
      exam_round_id: 1,
      committee_member_id: 1,
      candidate_exam_day_id: 2,
      availability: 'morning',
    });
    availability.flush({
      id: 3,
      exam_round_id: 1,
      committee_member_id: 1,
      candidate_exam_day_id: 2,
      availability: 'morning',
    });
  });
});
