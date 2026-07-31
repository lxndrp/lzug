import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideTaiga } from '@taiga-ui/core';

import { SchedulingOverviewComponent } from './scheduling-overview.component';

describe('SchedulingOverviewComponent', () => {
  let fixture: ComponentFixture<SchedulingOverviewComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SchedulingOverviewComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(SchedulingOverviewComponent);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('groups entries and exposes exactly the status-specific primary action', () => {
    const component = fixture.componentInstance;
    const openSpy = vi.spyOn(component.openRound, 'emit');
    fixture.detectChanges();
    http.expectOne('/api/scheduling-overview').flush({ items: overviewItems(), _links: {} });
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Entwurf');
    expect(element.textContent).toContain('In Abstimmung');
    expect(element.textContent).toContain('Bestätigt');
    expect(element.textContent).toContain('Winter 2026');
    expect(element.textContent).toContain('Planung');
    expect(element.textContent).toContain('Neue Terminorganisation');
    expect(element.textContent).toContain('Rückmeldungen ansehen');
    expect(element.textContent).toContain('Vorschlag prüfen');
    expect(element.textContent).toContain('Prüfungsplan anzeigen');
    click(element, 'Neue Terminorganisation');
    expect(openSpy).toHaveBeenCalledWith({ id: 1, target: 'workflow' });
    click(element, 'Prüfungsplan anzeigen');
    expect(openSpy).toHaveBeenCalledWith({ id: 4, target: 'confirmed-plan' });
  });

  it('renders a readable empty state', () => {
    fixture.detectChanges();
    http.expectOne('/api/scheduling-overview').flush({ items: [], _links: {} });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Keine laufenden Terminorganisationen',
    );
  });

  it('renders a retryable error state', () => {
    fixture.detectChanges();
    http
      .expectOne('/api/scheduling-overview')
      .flush({}, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Übersicht nicht verfügbar');
    click(element, 'Erneut versuchen');
    http.expectOne('/api/scheduling-overview').flush({ items: [], _links: {} });
  });
});

function click(element: HTMLElement, label: string): void {
  const button = Array.from(element.querySelectorAll('button')).find((item) =>
    item.textContent?.includes(label),
  );
  expect(button).toBeTruthy();
  button?.click();
}

function overviewItems() {
  const shared = {
    committee_name: 'Prüfungsausschuss Teststadt 1',
    exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
    calendar_week_from: '2026-W47',
    calendar_week_to: '2026-W49',
    _links: {},
  };
  return [
    {
      ...shared,
      id: 1,
      name: 'Offene Runde',
      status: 'draft',
      status_group: 'draft',
      can_continue: true,
    },
    {
      ...shared,
      id: 2,
      name: 'Abstimmung',
      status: 'availability_requested',
      status_group: 'coordination',
      can_continue: true,
    },
    {
      ...shared,
      id: 3,
      name: 'Vorschlag',
      status: 'plan_proposed',
      status_group: 'planning',
      can_continue: true,
    },
    {
      ...shared,
      id: 4,
      name: 'Bestätigt',
      status: 'plan_confirmed',
      status_group: 'confirmed',
      can_continue: false,
    },
  ];
}
