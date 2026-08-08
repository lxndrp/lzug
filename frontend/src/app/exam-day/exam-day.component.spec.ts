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

  it('renders the selected confirmed day without write controls', () => {
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
    expect(element.querySelector('a[href="/confirmed-plans/1"]')).not.toBeNull();
    expect(element.querySelectorAll('button')).toHaveLength(0);
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
});

function dayView() {
  return {
    plan: {
      id: 1,
      name: 'Winter Testrunde Alpha',
      committee: { id: 1, name: 'Prüfungsausschuss Plan Alpha' },
      exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
    },
    day: {
      id: 7,
      date: '2026-11-16',
      location: {
        id: 1,
        name: 'Prüfungszentrum Plan (Test)',
        room: 'Testraum P-01',
        city: 'Teststadt',
      },
      slots: [
        {
          id: 7,
          starts_at: '2026-11-16 08:30:00',
          ends_at: '2026-11-16 09:30:00',
          sequence_number: 1,
          slot_type: 'regular',
          candidate: {
            id: 7,
            first_name: 'Prüfling',
            last_name: 'Plan-Day',
            ihk_exam_number: 'IHK-PLAN-7',
          },
        },
      ],
      assignments: [
        {
          id: 7,
          assignment_role: 'examiner',
          day_part: 'full_day',
          fallback_status: null,
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
