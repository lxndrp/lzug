import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';

import { ConfirmedPlansComponent } from './confirmed-plans.component';

describe('ConfirmedPlansComponent', () => {
  let fixture: ComponentFixture<ConfirmedPlansComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmedPlansComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ConfirmedPlansComponent);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('shows robust local times and German labels in committee tabs', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plans').flush({ items: plans(), _links: {} });
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Prüfungsausschuss Plan Alpha');
    expect(element.textContent).toContain('Montag, 16. November 2026');
    expect(element.querySelector('.app-confirmed-plan .app-muted')?.textContent?.trim()).toBe(
      'Winter 2026',
    );
    expect(element.textContent).toContain('08:30–09:30');
    expect(element.textContent).toContain('MEP-Prüfung');
    expect(element.textContent).toContain('Ersatzprüfer/in');
    expect(element.textContent).toContain('Arbeitgeber');
    expect(element.textContent).toContain('Arbeitnehmer');
    expect(element.textContent).toContain('Schule');
    expect(element.textContent).toContain('ganztägig');
    expect(
      element.querySelector<HTMLAnchorElement>('a[href="/confirmed-plans/1/days/1"]'),
    ).not.toBeNull();
    expect(
      element
        .querySelector<HTMLAnchorElement>('a[href="/confirmed-plans/1/days/1"]')
        ?.getAttribute('aria-label'),
    ).toBe('Montag, 16. November 2026: Tagesansicht öffnen');
    expect(element.textContent).not.toContain('employer');
    expect(element.textContent).not.toContain('employee');
    expect(element.textContent).not.toContain('school');
    const slotTable = element.querySelector('[aria-label="Prüfungsslots"]');
    expect(slotTable?.getAttribute('role')).toBe('region');
    expect(slotTable?.getAttribute('tabindex')).toBe('0');
    click(element, 'Prüfungsausschuss Plan Beta');
    fixture.detectChanges();
    expect(element.textContent).toContain('Prüfungsausschuss Plan Beta');
    expect(element.textContent).toContain('Prüfling Plan-Beta');
    expect(element.textContent).not.toContain('Prüfling Plan-Alpha');
  });

  it('links tabs to their panel and supports arrow-key selection', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plans').flush({ items: plans(), _links: {} });
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const tabs = element.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    expect(tabs[0].getAttribute('aria-controls')).toBe('confirmed-plans-panel-1');
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
    expect(element.querySelector('[role="tabpanel"]')?.getAttribute('aria-labelledby')).toBe(
      'confirmed-plans-tab-1',
    );

    tabs[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    fixture.detectChanges();

    expect(tabs[1].getAttribute('aria-selected')).toBe('true');
    expect(element.querySelector('[role="tabpanel"]')?.getAttribute('aria-labelledby')).toBe(
      'confirmed-plans-tab-2',
    );
    expect(element.textContent).toContain('Prüfling Plan-Beta');
  });

  it('opens a round-specific confirmed plan without exposing other rounds', () => {
    fixture.componentRef.setInput('roundId', 2);
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plans').flush({ items: plans(), _links: {} });
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Prüfling Plan-Beta');
    expect(text).not.toContain('Prüfling Plan-Alpha');
    expect((fixture.nativeElement as HTMLElement).querySelectorAll('[role="tab"]')).toHaveLength(1);
  });

  it('keeps the edit route read-only without the confirmed-plan capability', () => {
    fixture.componentRef.setInput('roundId', 1);
    fixture.componentRef.setInput('editRoundId', 1);
    fixture.componentRef.setInput('canEdit', false);
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plans').flush({ items: plans(), _links: {} });
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('app-confirmed-plan-editor')).toBeNull();
    expect(element.textContent).toContain('Prüfling Plan-Alpha');
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

  it('keeps modified day-link clicks as native navigation', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plans').flush({ items: plans(), _links: {} });
    fixture.detectChanges();

    const link = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>(
      'a[href="/confirmed-plans/1/days/1"]',
    );
    expect(link).not.toBeNull();
    const event = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      button: 0,
      metaKey: true,
    });
    link?.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
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
    id: candidate.ihk_exam_number === 'TEST-PLAN-1' ? 1 : 2,
    date: '2026-11-16',
    location: {
      id: 1,
      name: 'Prüfungszentrum Plan (Test)',
      room: 'Testraum P-01',
      city: 'Teststadt',
    },
    slots: [
      {
        id: 1,
        starts_at: '2026-11-16 08:30:00',
        ends_at: '2026-11-16 09:30:00',
        sequence_number: 1,
        slot_type,
        candidate: { id: 1, ...candidate },
      },
    ],
    assignments: [
      {
        id: 1,
        assignment_role: 'examiner',
        day_part: 'full_day',
        fallback_status: null,
        member: {
          id: 1,
          first_name: 'Testperson',
          last_name: 'Plan-Alpha',
          representing_side: 'employer',
        },
      },
      {
        id: 2,
        assignment_role: 'fallback',
        day_part: 'morning',
        fallback_status: 'confirmed',
        member: {
          id: 2,
          first_name: 'Testperson',
          last_name: 'Plan-Beta',
          representing_side: 'employee',
        },
      },
      {
        id: 3,
        assignment_role: 'examiner',
        day_part: 'afternoon',
        fallback_status: null,
        member: {
          id: 3,
          first_name: 'Testperson',
          last_name: 'Plan-Gamma',
          representing_side: 'school',
        },
      },
    ],
  });
  return [
    {
      id: 1,
      name: 'Winter Testrunde Alpha',
      committee: { id: 1, name: 'Prüfungsausschuss Plan Alpha' },
      exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
      days: [
        day(
          {
            first_name: 'Prüfling',
            last_name: 'Plan-Alpha',
            ihk_exam_number: 'TEST-PLAN-1',
          },
          'mep',
        ),
      ],
    },
    {
      id: 2,
      name: 'Winter Testrunde Beta',
      committee: { id: 2, name: 'Prüfungsausschuss Plan Beta' },
      exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
      days: [
        day({
          first_name: 'Prüfling',
          last_name: 'Plan-Beta',
          ihk_exam_number: 'TEST-PLAN-2',
        }),
      ],
    },
  ];
}
