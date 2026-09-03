import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { vi } from 'vitest';

import { ConfirmedPlanDayView, ExecutionStatus } from '../api/api.models';
import { AuthService } from '../auth/auth.service';
import { ExamDayComponent } from './exam-day.component';

describe('ExamDayComponent', () => {
  let fixture: ComponentFixture<ExamDayComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ExamDayComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ExamDayComponent);
    fixture.componentRef.setInput('roundId', 1);
    fixture.componentRef.setInput('dayId', 7);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.restoreAllMocks();
  });

  it('renders the selected confirmed day with attendance and start controls', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(dayView());
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Montag, 16. November 2026');
    expect(element.textContent).toContain('Prüfungsausschuss Plan Alpha');
    expect(element.textContent).toContain('Winter Testrunde Alpha');
    expect(element.textContent).toContain('Prüfungszentrum Plan (Test)');
    expect(element.textContent).toContain('Testraum P-01');
    expect(element.textContent).toContain('IHK-PLAN-7');
    expect(element.textContent).toContain('Ersatzprüfer/in');
    expect(element.textContent).toContain('Bestätigt');
    expect(element.textContent).toContain('Zusammenfassung der Durchführung');
    expect(element.textContent).toContain('Offen');
    expect(element.textContent).toContain('Anwesenheit speichern');
    expect(element.textContent).toContain('Prüfung starten');
    expect(element.querySelector('a[href="/confirmed-plans/1"]')).not.toBeNull();
    expect(element.querySelectorAll('button')).toHaveLength(8);
    expect(
      element
        .querySelector<HTMLButtonElement>('.app-exam-day-actions button')
        ?.getAttribute('aria-label'),
    ).toBe('Prüfling Plan-Day: Anwesenheit speichern');
    expect(
      element
        .querySelectorAll<HTMLButtonElement>('.app-exam-day-actions button')[3]
        .getAttribute('aria-label'),
    ).toBe('Testperson Prüfung: Anwesenheit speichern');
  });

  it('does not present a day when the API returns not found or another round', () => {
    fixture.detectChanges();
    http
      .expectOne('/api/confirmed-plan-days/7')
      .flush({ error: 'Confirmed exam day not found' }, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Prüfungstag nicht verfügbar',
    );

    fixture = TestBed.createComponent(ExamDayComponent);
    fixture.componentRef.setInput('roundId', 2);
    fixture.componentRef.setInput('dayId', 7);
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(dayView());
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Prüfungstag nicht verfügbar',
    );
  });

  it('persists candidate attendance and presents a server start error', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(dayView());
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const status = element.querySelector<HTMLSelectElement>('#candidate-status-7')!;
    status.value = 'late';
    status.dispatchEvent(new Event('change'));
    const arrival = element.querySelector<HTMLInputElement>('#candidate-arrival-7')!;
    arrival.value = '2026-11-16T08:24';
    arrival.dispatchEvent(new Event('input'));
    element.querySelectorAll<HTMLButtonElement>('.app-exam-day-actions button')[0].click();

    const attendanceRequest = http.expectOne('/api/confirmed-plan-days/7/slots/7/attendance');
    expect(attendanceRequest.request.body).toEqual({
      status: 'late',
      arrived_at: new Date('2026-11-16T08:24:00').toISOString(),
      day_revision: 1,
    });
    attendanceRequest.flush(dayView());
    fixture.detectChanges();
    expect(element.textContent).toContain('Änderung gespeichert.');

    element.querySelectorAll<HTMLButtonElement>('.app-exam-day-actions button')[1].click();
    const startRequest = http.expectOne('/api/confirmed-plan-days/7/slots/7/start');
    expect(startRequest.request.body).toHaveProperty('actual_started_at');
    startRequest.flush(
      { error: 'Mindestens drei anwesende reguläre Prüfer sind erforderlich' },
      { status: 400, statusText: 'Bad Request' },
    );
    fixture.detectChanges();
    expect(element.textContent).toContain('Mindestens drei anwesende reguläre Prüfer');
  });

  it('creates an absence report from a visible assignment', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(dayView());
    fixture.detectChanges();

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((item) => item.textContent?.includes('Ausfall melden'));
    expect(button).toBeTruthy();
    button?.click();

    const request = http.expectOne('/api/absence-reports');
    expect(request.request.body).toEqual({
      exam_day_id: 7,
      exam_day_assignment_id: 7,
      day_revision: 1,
    });
    request.flush({ id: 1 });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Ausfallmeldung gespeichert.',
    );
  });

  it('returns the demo examiner to derived scenario guidance after reporting an absence', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 2,
      person_id: 3,
      committee_member_id: 1,
      is_operator: false,
      demo_role: 'examiner',
      capabilities: ['absence:write-own'],
    });
    fixture.componentRef.setInput('canCoordinateAttendance', false);
    fixture.componentRef.setInput('canWriteOwnAttendance', false);
    fixture.componentRef.setInput('canReportOwnAbsence', true);
    fixture.componentRef.setInput('ownMemberId', 1);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(dayView());
    fixture.detectChanges();

    const report = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((button) => button.textContent?.includes('Ausfall melden'));
    expect(report).toBeDefined();
    report?.click();
    http.expectOne('/api/absence-reports').flush({ id: 1 });

    expect(navigate).toHaveBeenCalledWith('/demo-scenarios');
  });

  it('shows only capability-backed own actions in the demo', () => {
    fixture.componentRef.setInput('canCoordinateAttendance', false);
    fixture.componentRef.setInput('canWriteOwnAttendance', true);
    fixture.componentRef.setInput('canReportOwnAbsence', false);
    fixture.componentRef.setInput('ownMemberId', 1);
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(dayView());
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Testperson Prüfung');
    expect(element.textContent).not.toContain('Testperson Fallback');
    expect(element.textContent).toContain('Anwesenheit speichern');
    expect(element.textContent).not.toContain('Prüfung starten');
    expect(element.textContent).not.toContain('Status speichern');
    expect(element.textContent).not.toContain('Ausfall melden');

    const component = fixture.componentInstance as unknown as {
      reportAbsence(assignmentId: number): void;
    };
    component.reportAbsence(7);
    http.expectNone('/api/absence-reports');
  });

  it('allows present without arrival and resets feedback when changing days', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(dayView());
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const status = element.querySelector<HTMLSelectElement>('#candidate-status-7')!;
    status.value = 'present';
    status.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(element.querySelector<HTMLInputElement>('#candidate-arrival-7')!.required).toBe(false);

    element.querySelectorAll<HTMLButtonElement>('.app-exam-day-actions button')[0].click();
    const attendanceRequest = http.expectOne('/api/confirmed-plan-days/7/slots/7/attendance');
    expect(attendanceRequest.request.body).toEqual({
      status: 'present',
      arrived_at: null,
      day_revision: 1,
    });
    fixture.detectChanges();
    expect(
      [...element.querySelectorAll<HTMLButtonElement>('.app-exam-day-actions button')].every(
        (button) => button.disabled,
      ),
    ).toBe(true);
    attendanceRequest.flush(dayView());
    fixture.detectChanges();

    element.querySelectorAll<HTMLButtonElement>('.app-exam-day-actions button')[1].click();
    const startRequest = http.expectOne('/api/confirmed-plan-days/7/slots/7/start');
    startRequest.flush({ error: 'Start blockiert' }, { status: 400, statusText: 'Bad Request' });
    fixture.detectChanges();
    expect(element.textContent).toContain('Start blockiert');

    fixture.componentRef.setInput('dayId', 8);
    fixture.detectChanges();
    expect(element.textContent).not.toContain('Start blockiert');
    http.expectOne('/api/confirmed-plan-days/8').flush(dayView(8));
  });

  it('offers a retryable error state', () => {
    fixture.detectChanges();
    http
      .expectOne('/api/confirmed-plan-days/7')
      .flush({}, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Tagesansicht nicht verfügbar',
    );
    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button')?.click();
    http.expectOne('/api/confirmed-plan-days/7').flush(dayView());
  });

  it('persists a required reason for a status transition', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(dayView());
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const status = element.querySelector<HTMLSelectElement>('#execution-status-7')!;
    status.value = 'cancelled';
    status.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    element.querySelector<HTMLTextAreaElement>('#execution-reason-7')!.value =
      'Prüfling kurzfristig erkrankt';
    element
      .querySelector<HTMLTextAreaElement>('#execution-reason-7')!
      .dispatchEvent(new Event('input'));
    element.querySelectorAll<HTMLButtonElement>('.app-exam-day-actions button')[2].click();

    const request = http.expectOne('/api/confirmed-plan-days/7/slots/7/status');
    expect(request.request.body).toEqual({
      status: 'cancelled',
      reason: 'Prüfling kurzfristig erkrankt',
      day_revision: 1,
    });
    request.flush(dayView(7, 'cancelled', 'Prüfling kurzfristig erkrankt'));
    fixture.detectChanges();
    expect(element.textContent).toContain('Ausgefallen');
    expect(element.textContent).toContain('Prüfling kurzfristig erkrankt');
  });

  it('ignores a response for a previous day after the route changes', () => {
    fixture.detectChanges();
    const firstRequest = http.expectOne('/api/confirmed-plan-days/7');

    fixture.componentRef.setInput('dayId', 8);
    fixture.detectChanges();
    const secondRequest = http.expectOne('/api/confirmed-plan-days/8');

    firstRequest.flush(dayView(7));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Tagesansicht wird geladen',
    );

    secondRequest.flush(dayView(8));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('IHK-PLAN-8');
  });

  it('keeps modified back-link clicks as native navigation', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(dayView());
    fixture.detectChanges();

    const link = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>(
      'a[href="/confirmed-plans/1"]',
    );
    expect(link).not.toBeNull();
    const event = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      button: 0,
      ctrlKey: true,
    });
    link?.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it('confirms the current revision and hides direct mutations after closure', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      is_operator: false,
      capabilities: ['exam-day-closure:read', 'exam-day-closure:close'],
    });
    const open = dayView();
    open.day.closure.permissions.close = true;
    open.day.closure.evaluation.regular_close_ready = true;

    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(open);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const closeButton = Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(
      (item) => item.textContent?.includes('Voraussetzungen bestätigen'),
    );
    expect(closeButton).toBeTruthy();
    closeButton?.click();

    const request = http.expectOne('/api/confirmed-plan-days/7/closure');
    expect(request.request.body).toEqual({
      revision: 1,
      closure_type: 'regular',
      confirmed: true,
    });
    const closed = structuredClone(open.day.closure);
    closed.revision = 2;
    closed.status = 'closed';
    closed.permissions.close = false;
    request.flush(closed);
    fixture.detectChanges();

    expect(element.textContent).toContain('Prüfungstag formal abgeschlossen.');
    expect(element.textContent).toContain('Geschlossen');
    expect(element.textContent).not.toContain('Anwesenheit speichern');
    expect(element.textContent).not.toContain('Status speichern');
  });

  it('previews and performs a targeted reopening with the current revision', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      is_operator: false,
      capabilities: [
        'exam-day-closure:read',
        'exam-day-closure:preview-reopening',
        'exam-day-closure:reopen',
        'exam-day-closure:export',
      ],
    });
    const closed = dayView();
    closed.day.closure_status = 'closed';
    closed.day.closure.status = 'closed';
    closed.day.closure.permissions = { close: false, reopen: true, export: true };
    closed.day.closure.evaluation.protocol_references = [{ exam_protocol_id: 41 }];
    closed.day.closure.evaluation.result_references = [{ exam_result_id: 51 }];

    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(closed);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Prüfungsprotokoll 41');
    expect(element.textContent).toContain('Bewertung und Ergebnis 51');
    expect(element.textContent).toContain('Maschinenlesbaren Nachweis exportieren');

    const reopeningForm = Array.from(element.querySelectorAll('fieldset')).find((item) =>
      item.textContent?.includes('Zielgerichtete Wiederöffnung'),
    )!;
    const scope = reopeningForm.querySelector('select')!;
    scope.value = 'exam_protocol:41';
    scope.dispatchEvent(new Event('change'));
    const inputs = reopeningForm.querySelectorAll<HTMLInputElement>('input');
    inputs[0].value = 'Nachträglicher Widerspruch';
    inputs[0].dispatchEvent(new Event('input'));
    inputs[1].value = 'IHK-Schreiben 2026-11-20';
    inputs[1].dispatchEvent(new Event('input'));
    const reason = reopeningForm.querySelector<HTMLTextAreaElement>('textarea')!;
    reason.value = 'Protokollangabe muss korrigiert werden';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    reopeningForm.querySelector<HTMLButtonElement>('button')!.click();

    const impactRequest = http.expectOne('/api/confirmed-plan-days/7/reopening-impact');
    expect(impactRequest.request.body).toEqual({
      scope: [{ kind: 'exam_protocol', entity_id: 41 }],
    });
    impactRequest.flush({
      exam_day_id: 7,
      revision: 1,
      requested_scope: ['exam_protocol:41'],
      expanded_scope: ['exam_protocol:41', 'exam_result:51'],
      impacts: { exam_protocol: [41], exam_result: [51] },
    });
    fixture.detectChanges();
    expect(element.textContent).toContain('Betroffen: exam_protocol:41, exam_result:51');

    const reopenButton = Array.from(
      reopeningForm.querySelectorAll<HTMLButtonElement>('button'),
    ).find((item) => item.textContent?.includes('Zielgerichtet wieder öffnen'))!;
    reopenButton.click();
    const reopenRequest = http.expectOne('/api/confirmed-plan-days/7/reopenings');
    expect(reopenRequest.request.body).toEqual({
      revision: 1,
      occasion: 'Nachträglicher Widerspruch',
      source: 'IHK-Schreiben 2026-11-20',
      reason: 'Protokollangabe muss korrigiert werden',
      scope: [{ kind: 'exam_protocol', entity_id: 41 }],
    });
    const reopening = structuredClone(closed.day.closure);
    reopening.revision = 2;
    reopening.status = 'reopening';
    reopening.active_reopening = { expanded_scope: ['exam_protocol:41', 'exam_result:51'] };
    reopening.permissions.reopen = false;
    reopenRequest.flush(reopening);
    fixture.detectChanges();

    expect(element.textContent).toContain('Prüfungstag zielgerichtet wieder geöffnet.');
    expect(element.textContent).toContain('Wiederöffnung läuft');
  });

  it('validates exception evidence and presents a structured closure error', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      is_operator: false,
      capabilities: ['exam-day-closure:read', 'exam-day-closure:close'],
    });
    const open = dayView();
    open.day.closure.permissions.close = true;
    open.day.closure.evaluation.exception_close_ready = true;

    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7').flush(open);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const closeForm = Array.from(element.querySelectorAll('fieldset')).find((item) =>
      item.textContent?.includes('Abschlussentscheidung'),
    )!;
    const type = closeForm.querySelector('select')!;
    type.value = 'exception';
    type.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    const closeButton = closeForm.querySelector<HTMLButtonElement>('button')!;
    closeButton.click();
    fixture.detectChanges();
    expect(element.textContent).toContain(
      'Grund und bisherige Klärungsversuche sind erforderlich.',
    );

    const evidence = closeForm.querySelectorAll<HTMLTextAreaElement>('textarea');
    evidence[0].value = 'Eine Antwort fehlt unverändert';
    evidence[0].dispatchEvent(new Event('input'));
    evidence[1].value = 'Zweimal telefonisch und einmal schriftlich angefragt';
    evidence[1].dispatchEvent(new Event('input'));
    closeButton.click();

    const request = http.expectOne('/api/confirmed-plan-days/7/closure');
    expect(request.request.body).toEqual({
      revision: 1,
      closure_type: 'exception',
      confirmed: true,
      reason: 'Eine Antwort fehlt unverändert',
      clarification_attempts: 'Zweimal telefonisch und einmal schriftlich angefragt',
    });
    request.flush(
      { error: { code: 'exam_day_validation', message: 'Voraussetzungen geändert' } },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    fixture.detectChanges();
    expect(element.textContent).toContain('Voraussetzungen geändert');
  });
});

function dayView(
  dayId = 7,
  executionStatus: ExecutionStatus = 'open',
  statusReason: string | null = null,
): ConfirmedPlanDayView {
  return {
    plan: {
      id: 1,
      name: 'Winter Testrunde Alpha',
      committee: { id: 1, name: 'Prüfungsausschuss Plan Alpha' },
      exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
    },
    day: {
      id: dayId,
      date: '2026-11-16',
      revision: 1,
      closure_status: 'open',
      closure: {
        exam_day_id: dayId,
        revision: 1,
        status: 'open',
        legacy_status: null,
        evaluation: {
          items: [],
          warnings: [],
          regular_close_ready: false,
          exception_close_ready: false,
          exception_candidate: null,
          protocol_references: [],
          result_references: [],
        },
        active_reopening: null,
        history: [],
        tasks: [],
        permissions: { close: false, reopen: false, export: true },
        _links: {
          machine_export: {
            href: `/api/confirmed-plan-days/${dayId}/closure/export.json`,
          },
          human_export: {
            href: `/api/confirmed-plan-days/${dayId}/closure/export.txt`,
          },
        },
      },
      location: {
        id: 1,
        name: 'Prüfungszentrum Plan (Test)',
        room: 'Testraum P-01',
        city: 'Teststadt',
      },
      slots: [
        {
          id: dayId,
          starts_at: '2026-11-16 08:30:00',
          ends_at: '2026-11-16 09:30:00',
          sequence_number: 1,
          slot_type: 'regular',
          actual_started_at: null,
          execution_status: executionStatus,
          status_changed_at: '2026-11-16T08:00:00+01:00',
          actual_completed_at: null,
          status_reason: statusReason,
          candidate_attendance: { status: 'open', arrived_at: null },
          candidate: {
            id: dayId,
            first_name: 'Prüfling',
            last_name: 'Plan-Day',
            ihk_exam_number: `IHK-PLAN-${dayId}`,
          },
        },
      ],
      assignments: [
        {
          id: dayId,
          assignment_role: 'examiner',
          day_part: 'full_day',
          fallback_status: null,
          attendance: { status: 'open', arrived_at: null },
          member: {
            id: 1,
            first_name: 'Testperson',
            last_name: 'Prüfung',
            representing_side: 'employer',
          },
        },
        {
          id: 8,
          assignment_role: 'fallback',
          day_part: 'morning',
          fallback_status: 'confirmed',
          attendance: { status: 'open', arrived_at: null },
          member: {
            id: 2,
            first_name: 'Testperson',
            last_name: 'Fallback',
            representing_side: 'employee',
          },
        },
      ],
      status_summary: {
        open: executionStatus === 'open' ? 1 : 0,
        running: executionStatus === 'running' ? 1 : 0,
        completed: executionStatus === 'completed' ? 1 : 0,
        cancelled: executionStatus === 'cancelled' ? 1 : 0,
        needs_follow_up: executionStatus === 'needs_follow_up' ? 1 : 0,
      },
    },
    _links: {},
  };
}
