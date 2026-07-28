import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideTaiga } from '@taiga-ui/core';

import { ConfirmedPlansComponent } from './confirmed-plans.component';

describe('ConfirmedPlansComponent', () => {
  let fixture: ComponentFixture<ConfirmedPlansComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmedPlansComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ConfirmedPlansComponent);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('groups confirmed plans in committee tabs and shows a day with slots and fallback', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plans').flush({ items: plans(), _links: {} });
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('PA Nord');
    expect(element.textContent).toContain('Montag, 16. November 2026');
    expect(element.textContent).toContain('MEP-Prüfung');
    expect(element.textContent).toContain('Fallback');
    click(element, 'PA Süd');
    fixture.detectChanges();
    expect(element.textContent).toContain('PA Süd');
    expect(element.textContent).toContain('Erika Muster');
    expect(element.textContent).not.toContain('Max Beispiel');
  });

  it('renders empty and retryable error states', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plans').flush({ items: [], _links: {} });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Keine bestätigten Prüfungspläne',
    );

    fixture = TestBed.createComponent(ConfirmedPlansComponent);
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plans').flush({}, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    click(fixture.nativeElement as HTMLElement, 'Erneut versuchen');
    http.expectOne('/api/confirmed-plans').flush({ items: [], _links: {} });
  });
});

function click(element: HTMLElement, label: string): void {
  const button = Array.from(element.querySelectorAll('button')).find((item) =>
    item.textContent?.includes(label),
  );
  expect(button).toBeTruthy();
  button?.click();
}

function plans() {
  const day = (
    candidate: { first_name: string; last_name: string; ihk_exam_number: string },
    slot_type = 'regular',
  ) => ({
    id: candidate.ihk_exam_number === 'FI-1' ? 1 : 2,
    date: '2026-11-16',
    location: { id: 1, name: 'Bildungszentrum', room: 'A 12', city: 'Hamburg' },
    slots: [
      {
        id: 1,
        starts_at: '09:00',
        ends_at: '09:30',
        sequence_number: 1,
        slot_type,
        candidate: { id: 1, ...candidate },
      },
    ],
    assignments: [
      {
        id: 1,
        assignment_role: 'fallback',
        day_part: 'morning',
        fallback_status: 'confirmed',
        member: { id: 1, first_name: 'Max', last_name: 'Prüfer', representing_side: 'employee' },
      },
    ],
  });
  return [
    {
      id: 1,
      name: 'Winter Nord',
      committee: { id: 1, name: 'PA Nord' },
      exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
      days: [day({ first_name: 'Max', last_name: 'Beispiel', ihk_exam_number: 'FI-1' }, 'mep')],
    },
    {
      id: 2,
      name: 'Winter Süd',
      committee: { id: 2, name: 'PA Süd' },
      exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
      days: [day({ first_name: 'Erika', last_name: 'Muster', ihk_exam_number: 'FI-2' })],
    },
  ];
}
