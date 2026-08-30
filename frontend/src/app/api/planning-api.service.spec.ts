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

    const editable = {
      round_id: 1,
      revision: 3,
      exam_days: [],
      _links: {},
    };
    service.getPlanningProposal().subscribe((result) => expect(result.revision).toBe(3));
    const getEditable = http.expectOne('/api/exam-rounds/1/planning-proposal');
    expect(getEditable.request.method).toBe('GET');
    getEditable.flush(editable);

    service.savePlanningProposal(editable).subscribe((result) => expect(result.revision).toBe(4));
    const saveEditable = http.expectOne('/api/exam-rounds/1/planning-proposal');
    expect(saveEditable.request.method).toBe('PUT');
    expect(saveEditable.request.body).toEqual(editable);
    saveEditable.flush({ ...editable, revision: 4 });

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

    service.updateExamHalfYear(2, { season: 'winter', year: 2028 }).subscribe();
    const updateHalfYear = http.expectOne('/api/exam-half-years/2');
    expect(updateHalfYear.request.method).toBe('PATCH');
    expect(updateHalfYear.request.body).toEqual({ season: 'winter', year: 2028 });
    updateHalfYear.flush({ id: 2, season: 'winter', year: 2028, status: 'draft' });

    service
      .createExamRound({
        exam_half_year_id: 2,
        committee_id: 1,
        name: 'Sommer 2027 · Prüfungsausschuss Teststadt 1',
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

  it('should use the revisioned confirmed-plan endpoints', () => {
    service.getEditableConfirmedPlan(2).subscribe((plan) => expect(plan.revision).toBe(4));
    const read = http.expectOne('/api/exam-rounds/2/confirmed-plan');
    expect(read.request.method).toBe('GET');
    read.flush({ round_id: 2, revision: 4, exam_days: [], _links: {} });

    service
      .saveEditableConfirmedPlan(
        2,
        { round_id: 2, revision: 4, exam_days: [], _links: {} },
        'Korrektur',
      )
      .subscribe();
    const save = http.expectOne('/api/exam-rounds/2/confirmed-plan');
    expect(save.request.method).toBe('PUT');
    expect(save.request.body).toEqual({
      round_id: 2,
      revision: 4,
      exam_days: [],
      _links: {},
      reason: 'Korrektur',
    });
    save.flush({ round_id: 2, revision: 5, exam_days: [], _links: {} });

    service.getConfirmedPlanRevisions(2).subscribe((revisions) => expect(revisions).toEqual([]));
    const history = http.expectOne('/api/exam-rounds/2/confirmed-plan/revisions');
    expect(history.request.method).toBe('GET');
    history.flush({ items: [], _links: {} });
  });

  it('should use the channel-neutral notification endpoints', () => {
    service.getNotifications().subscribe((items) => expect(items[0].id).toBe(7));
    const notifications = http.expectOne('/api/notifications');
    expect(notifications.request.method).toBe('GET');
    notifications.flush({
      items: [
        {
          id: 7,
          event_type: 'plan_confirmed',
          title: 'Prüfungsplan bestätigt',
          message: 'Ihre Termine sind verfügbar.',
          action_path: '/confirmed-plans/1',
          created_at: '2026-10-01T10:00:00+00:00',
        },
      ],
      _links: {},
    });

    service.getNotificationOverview().subscribe((items) => expect(items).toEqual([]));
    const overview = http.expectOne('/api/notification-overview');
    expect(overview.request.method).toBe('GET');
    overview.flush({ items: [], _links: {} });

    service.registerPushSubscription('https://push.example.invalid/one').subscribe();
    const registration = http.expectOne('/api/push-subscriptions');
    expect(registration.request.method).toBe('POST');
    expect(registration.request.body).toEqual({ endpoint: 'https://push.example.invalid/one' });
    registration.flush({ id: 1, active: true });
  });

  it('should expose the personal calendar feed endpoints', () => {
    service.getCalendarStatus().subscribe((status) => expect(status.active).toBe(true));
    const status = http.expectOne('/api/calendar');
    expect(status.request.method).toBe('GET');
    status.flush({
      active: true,
      activated_at: '2026-10-01T10:00:00+00:00',
      revoked_at: null,
      time_zone: 'Europe/Berlin',
      _links: {},
    });

    service.getCalendarEvents().subscribe((events) => expect(events).toEqual([]));
    const events = http.expectOne('/api/calendar/events');
    expect(events.request.method).toBe('GET');
    events.flush({ items: [], _links: {} });

    service.activateCalendarFeed(true).subscribe((result) => expect(result.active).toBe(true));
    const activate = http.expectOne('/api/calendar/feed');
    expect(activate.request.method).toBe('POST');
    expect(activate.request.body).toEqual({ rotate: true });
    activate.flush({
      active: true,
      activated_at: '2026-10-01T10:00:00+00:00',
      revoked_at: null,
      time_zone: 'Europe/Berlin',
      feed_url: '/api/calendar/feed/token.ics',
      notice: 'only now',
      _links: {},
    });

    service.revokeCalendarFeed().subscribe((result) => expect(result.active).toBe(false));
    const revoke = http.expectOne('/api/calendar/feed');
    expect(revoke.request.method).toBe('DELETE');
    revoke.flush({
      active: false,
      activated_at: '2026-10-01T10:00:00+00:00',
      revoked_at: '2026-10-01T11:00:00+00:00',
      time_zone: 'Europe/Berlin',
      notice: 'revoked',
      _links: {},
    });
  });

  it('should expose committee member write operations', () => {
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

  it('should save round metadata before requesting availabilities', () => {
    const payload = {
      name: 'Winter 2026/27',
      availability_deadline: '2026-10-15 18:00:00',
      availability_reminder_at: '2026-10-08 09:00:00',
    };
    service.requestAvailabilities(payload).subscribe();

    const update = http.expectOne('/api/exam-rounds/1');
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual(payload);
    update.flush(examRoundFixture);

    const request = http.expectOne('/api/exam-rounds/1/request-availabilities');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({});
    request.flush({ ...examRoundFixture, status: 'availability_requested' });
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

  it('should expose the versioned exam protocol workflow', () => {
    service.getExamProtocol(7, 11).subscribe();
    const protocol = http.expectOne('/api/confirmed-plan-days/7/slots/11/protocol');
    expect(protocol.request.method).toBe('GET');
    protocol.flush({});

    service
      .updateExamProtocol(
        41,
        2,
        'with_special_occurrences',
        [
          {
            category: 'interruption',
            statement: 'Zwei Minuten unterbrochen.',
            occurred_from: '2026-11-16T09:20:00.000Z',
            occurred_to: '2026-11-16T09:22:00.000Z',
          },
        ],
        '  Sachverhalt ergänzt  ',
      )
      .subscribe();
    const update = http.expectOne('/api/exam-protocols/41');
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({
      version: 2,
      declaration: 'with_special_occurrences',
      entries: [
        {
          category: 'interruption',
          statement: 'Zwei Minuten unterbrochen.',
          occurred_from: '2026-11-16T09:20:00.000Z',
          occurred_to: '2026-11-16T09:22:00.000Z',
        },
      ],
      change_reason: 'Sachverhalt ergänzt',
    });
    update.flush({});

    service.submitExamProtocol(41, 3).subscribe();
    const submit = http.expectOne('/api/exam-protocols/41/submit');
    expect(submit.request.method).toBe('POST');
    expect(submit.request.body).toEqual({ version: 3 });
    submit.flush({});

    service.respondToExamProtocol(41, 3, 'reservation', 72, '  Zeitangabe prüfen  ').subscribe();
    const response = http.expectOne('/api/exam-protocols/41/responses');
    expect(response.request.method).toBe('POST');
    expect(response.request.body).toEqual({
      version: 3,
      response: 'reservation',
      entry_id: 72,
      statement: 'Zeitangabe prüfen',
    });
    response.flush({});

    service.requestExamProtocolCorrection(41, 3, '  Eintrag ergänzen  ').subscribe();
    const correctionRequest = http.expectOne('/api/exam-protocols/41/correction-requests');
    expect(correctionRequest.request.method).toBe('POST');
    expect(correctionRequest.request.body).toEqual({ version: 3, reason: 'Eintrag ergänzen' });
    correctionRequest.flush({});

    service
      .openExamProtocolCorrection(41, 3, 9, '  Korrektur koordinieren  ', '  REOPEN-36  ')
      .subscribe();
    const openCorrection = http.expectOne('/api/exam-protocols/41/open-correction');
    expect(openCorrection.request.method).toBe('POST');
    expect(openCorrection.request.body).toEqual({
      version: 3,
      correction_request_id: 9,
      reason: 'Korrektur koordinieren',
      reopening_reference: 'REOPEN-36',
    });
    openCorrection.flush({});
  });
});
