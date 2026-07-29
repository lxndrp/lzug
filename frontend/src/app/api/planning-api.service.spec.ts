import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { PlanningApiService } from './planning-api.service';
import {
  assignmentsFixture,
  availabilitiesFixture,
  candidateDaysFixture,
  candidateAssignmentsFixture,
  candidatesFixture,
  committeesFixture,
  examDaysFixture,
  examRoundFixture,
  examRoundsFixture,
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
      expect(board.days[0].location?.name).toBe('Prüfungszentrum Alpha (Test)');
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
    http.expectOne('/api/round-candidates?round_id=1&is_active=1').flush({
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

  it('should expose exam-half-year and committee-round operations', () => {
    service.listExamHalfYears().subscribe();
    const halfYears = http.expectOne('/api/exam-half-years');
    expect(halfYears.request.method).toBe('GET');
    halfYears.flush({ items: [], _links: {} });

    service.createExamHalfYear({ season: 'summer', year: 2027, status: 'draft' }).subscribe();
    const createHalfYear = http.expectOne('/api/exam-half-years');
    expect(createHalfYear.request.method).toBe('POST');
    expect(createHalfYear.request.body).toEqual({ season: 'summer', year: 2027, status: 'draft' });
    createHalfYear.flush({ id: 2, season: 'summer', year: 2027, status: 'draft' });

    service
      .createExamRound({
        exam_half_year_id: 2,
        committee_id: 1,
        name: 'Sommer 2027 · Prüfungsausschuss Teststadt 1',
        created_by_member_id: 1,
      })
      .subscribe();
    const createRound = http.expectOne('/api/exam-rounds');
    expect(createRound.request.method).toBe('POST');
    expect(createRound.request.body.exam_half_year_id).toBe(2);
    createRound.flush({ ...examRoundFixture, id: 2, exam_half_year_id: 2 });
  });

  it('should load the scheduling overview collection', () => {
    service.getSchedulingOverview().subscribe((items) => {
      expect(items[0].status_group).toBe('coordination');
      expect(items[0].can_continue).toBe(true);
    });
    const request = http.expectOne('/api/scheduling-overview');
    expect(request.request.method).toBe('GET');
    request.flush({
      items: [
        {
          id: 1,
          name: 'Winter 2026/27',
          status: 'availability_requested',
          status_group: 'coordination',
          committee_name: 'Prüfungsausschuss Teststadt 1',
          exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
          calendar_week_from: '2026-W47',
          calendar_week_to: '2026-W49',
          can_continue: true,
          _links: {},
        },
      ],
      _links: {},
    });
  });

  it('should load the confirmed-plan calendar collection', () => {
    service.getConfirmedPlans().subscribe((plans) => expect(plans).toEqual([]));
    const request = http.expectOne('/api/confirmed-plans');
    expect(request.request.method).toBe('GET');
    request.flush({ items: [], _links: {} });
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
      expect(items[1].candidate.last_name).toBe('Beta');
      expect(items[1].roundCandidate?.attempt_number).toBe(2);
      expect(items[1].roundCandidate?.requires_mep).toBe(1);
    });

    http.expectOne('/api/candidates').flush({ items: candidatesFixture, _links: {} });
    http.expectOne('/api/round-candidates?round_id=1&is_active=1').flush({
      items: roundCandidatesFixture,
      _links: {},
    });
  });

  it('should expose candidate write operations', () => {
    service
      .createCandidate({
        first_name: 'Prüfling',
        last_name: 'Gamma',
        ihk_exam_number: 'TEST-2026-0003',
        specialization: 'data_and_process_analysis',
        training_company: 'Testbetrieb Gamma',
        attempt_number: 1,
        requires_mep: 0,
      })
      .subscribe();

    const create = http.expectOne('/api/candidates');
    expect(create.request.method).toBe('POST');
    expect(create.request.body).toEqual({
      first_name: 'Prüfling',
      last_name: 'Gamma',
      ihk_exam_number: 'TEST-2026-0003',
      specialization: 'data_and_process_analysis',
      training_company: 'Testbetrieb Gamma',
      attempt_number: 1,
      requires_mep: 0,
      exam_round_id: 1,
    });
    create.flush(candidatesFixture[0]);

    service
      .updateCandidate(1, {
        first_name: 'Prüfling',
        last_name: 'Alpha',
        ihk_exam_number: 'TEST-2026-0001',
        specialization: 'application_development',
        training_company: 'Testbetrieb Alpha',
        attempt_number: 2,
        requires_mep: 1,
      })
      .subscribe();
    const update = http.expectOne('/api/candidates/1');
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({
      first_name: 'Prüfling',
      last_name: 'Alpha',
      ihk_exam_number: 'TEST-2026-0001',
      specialization: 'application_development',
      training_company: 'Testbetrieb Alpha',
      attempt_number: 2,
      requires_mep: 1,
      exam_round_id: 1,
    });
    update.flush(candidatesFixture[0]);

    service
      .updateCandidate(1, {
        first_name: 'Prüfling',
        last_name: 'Alpha',
        ihk_exam_number: 'TEST-2026-0001',
        specialization: 'application_development',
        training_company: 'Testbetrieb Alpha',
        attempt_number: 2,
        requires_mep: 1,
        exam_round_id: 2,
        assignment_change_reason: 'Wechsel in den zweiten Ausschuss',
      })
      .subscribe();
    const transfer = http.expectOne('/api/candidates/1');
    expect(transfer.request.body.exam_round_id).toBe(2);
    expect(transfer.request.body.assignment_change_reason).toBe('Wechsel in den zweiten Ausschuss');
    transfer.flush(candidatesFixture[0]);

    service.deleteCandidate(1).subscribe();
    const remove = http.expectOne('/api/candidates/1');
    expect(remove.request.method).toBe('DELETE');
    remove.flush({});
  });

  it('should load assignment history with master data', () => {
    service.getMasterData().subscribe((masterData) => {
      expect(masterData.examHalfYears).toEqual([
        { id: 1, season: 'winter', year: 2026, status: 'active' },
      ]);
      expect(masterData.examRounds).toEqual(examRoundsFixture);
      expect(masterData.candidateAssignments).toEqual(candidateAssignmentsFixture);
    });

    http.expectOne('/api/committees').flush({ items: committeesFixture, _links: {} });
    http.expectOne('/api/exam-half-years').flush({
      items: [{ id: 1, season: 'winter', year: 2026, status: 'active' }],
      _links: {},
    });
    http.expectOne('/api/persons').flush({ items: [], _links: {} });
    http.expectOne('/api/members').flush({ items: membersFixture, _links: {} });
    http.expectOne('/api/candidates').flush({ items: candidatesFixture, _links: {} });
    http.expectOne('/api/round-candidates?round_id=1&is_active=1').flush({
      items: roundCandidatesFixture,
      _links: {},
    });
    http.expectOne('/api/exam-rounds').flush({ items: examRoundsFixture, _links: {} });
    http.expectOne('/api/candidate-committee-assignments').flush({
      items: candidateAssignmentsFixture,
      _links: {},
    });
    http.expectOne('/api/locations').flush({ items: locationsFixture, _links: {} });
  });

  it('should expose location write operations', () => {
    service
      .createLocation({
        committee_id: 1,
        name: 'Prüfungszentrum Service (Test)',
        street: 'Testweg 20',
        postal_code: '00000',
        city: 'Teststadt',
        room: 'Testraum S-01',
        is_active: 1,
      })
      .subscribe();

    const request = http.expectOne('/api/locations');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      committee_id: 1,
      name: 'Prüfungszentrum Service (Test)',
      street: 'Testweg 20',
      postal_code: '00000',
      city: 'Teststadt',
      room: 'Testraum S-01',
      is_active: 1,
    });
    request.flush(locationsFixture[0]);

    service.updateLocation(1, { is_active: 0 }).subscribe();
    const update = http.expectOne('/api/locations/1');
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({ is_active: 0 });
    update.flush({ ...locationsFixture[0], is_active: 0 });

    service
      .updateLocation(1, { name: 'Prüfungszentrum Service Neu (Test)', room: 'S-02' })
      .subscribe();
    const edit = http.expectOne('/api/locations/1');
    expect(edit.request.method).toBe('PATCH');
    expect(edit.request.body).toEqual({
      name: 'Prüfungszentrum Service Neu (Test)',
      room: 'S-02',
    });
    edit.flush({
      ...locationsFixture[0],
      name: 'Prüfungszentrum Service Neu (Test)',
      room: 'S-02',
    });

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
        exclude_public_holidays: 1,
        holiday_subdivision_code: 'DE-NW',
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
      exclude_public_holidays: 1,
      holiday_subdivision_code: 'DE-NW',
      default_location_id: 1,
      updated_by_member_id: 1,
    });
    request.flush({});
  });

  it('should update exam round metadata for the active round', () => {
    service
      .updateExamRound({
        name: 'Sommer 2027',
        availability_deadline: '2027-04-15 18:00:00',
        availability_reminder_at: '2027-04-08 09:00:00',
      })
      .subscribe();

    const request = http.expectOne('/api/exam-rounds/1');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body.name).toBe('Sommer 2027');
    request.flush({ ...examRoundFixture, name: 'Sommer 2027' });
  });

  it('should expose possible day and availability write operations', () => {
    service.generateCandidateExamDays().subscribe();
    const generateDays = http.expectOne('/api/candidate-exam-days/generate');
    expect(generateDays.request.method).toBe('POST');
    expect(generateDays.request.body).toEqual({ round_id: 1 });
    generateDays.flush({
      round_id: 1,
      calendar_week_from: '2026-W47',
      calendar_week_to: '2026-W49',
      exclude_public_holidays: 1,
      holiday_subdivision_code: 'DE-NW',
      created_days: [],
      skipped_existing: [],
      excluded_holidays: [],
      counts: { calculated_weekdays: 15, created: 0, existing: 15, excluded_holidays: 0 },
    });

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
