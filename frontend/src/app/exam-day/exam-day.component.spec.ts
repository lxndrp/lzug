import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';

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

  afterEach(() => http.verify());

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
    expect(element.textContent).toContain('Anwesenheit speichern');
    expect(element.textContent).toContain('Prüfung starten');
    expect(element.querySelector('a[href="/confirmed-plans/1"]')).not.toBeNull();
    expect(element.querySelectorAll('button')).toHaveLength(4);
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
      arrived_at: '2026-11-16T07:24:00.000Z',
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
});

function dayView(dayId = 7) {
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
    },
    _links: {},
  };
}
